import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import HttpUrl

from allyourbase.models.geometry import Polygon
from allyourbase.models.settings import Settings
from allyourbase.providers.contracts import ProviderError
from allyourbase.providers.http import Transport
from allyourbase.providers.spatial import query_parts
from allyourbase.providers.stac import STACProvider, acquisition_from_item


def item(
    identifier: str = "synthetic-scene", timestamp: str = "2020-12-30T12:00:00Z"
) -> dict[str, Any]:
    return {
        "id": identifier,
        "properties": {"datetime": timestamp, "eo:cloud_cover": 95},
        "assets": {"blue": {"href": "https://example.invalid/blue.tif", "type": "image/tiff"}},
    }


def polygon() -> Polygon:
    return Polygon.model_validate(
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    )


def provider(settings: Settings, handler: Any) -> STACProvider:
    config = settings.providers.definitions["earth_search"].model_copy(
        update={"catalogue_url": HttpUrl("https://provider.invalid")}
    )
    return STACProvider(
        "test",
        config,
        Transport(httpx.Client(transport=httpx.MockTransport(handler)), settings.access, 1),
    )


def test_pagination_and_exclusive_week_end(settings: Settings) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "features": [item()],
                    "links": [
                        {"rel": "next", "href": "https://provider.invalid/page2", "method": "GET"}
                    ],
                },
            )
        return httpx.Response(
            200, json={"features": [item(), item("next-week", "2021-01-04T00:00:00Z")]}
        )

    scenes = provider(settings, handler).discover(
        polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC)
    )
    assert [scene.scene_id for scene in scenes] == ["synthetic-scene"]
    assert (
        scenes[0].cloud_cover == 95
    )  # Discovery measures coverage; it does not hide cloudy looks.
    assert [request.method for request in requests] == ["POST", "GET"]
    assert json.loads(requests[0].content)["collections"] == [
        settings.providers.definitions["earth_search"].collection
    ]


def test_catalog_cursor_pagination(settings: Settings) -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"features": [], "context": {"next": 5}} if len(bodies) == 1 else {"features": []},
        )

    assert (
        provider(settings, handler).discover(
            polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC)
        )
        == []
    )
    assert bodies[1]["next"] == 5
    assert bodies[1]["intersects"] == bodies[0]["intersects"]


def test_cross_origin_pagination_rejected(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [],
                "links": [{"rel": "next", "href": "https://other.invalid/search"}],
            },
        )

    with pytest.raises(ProviderError, match="cross_origin_pagination"):
        provider(settings, handler).discover(
            polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC)
        )


def test_repeated_page_rejected(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [],
                "links": [
                    {
                        "rel": "next",
                        "href": "https://provider.invalid/search",
                        "method": "POST",
                        "body": {},
                        "merge": True,
                    }
                ],
            },
        )

    with pytest.raises(ProviderError, match="pagination_cycle"):
        provider(settings, handler).discover(
            polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC)
        )


def test_antimeridian_discovery_queries_two_small_parts(settings: Settings) -> None:
    geometry = Polygon.model_validate(
        {"type": "Polygon", "coordinates": [[[179, 0], [-179, 0], [-179, 1], [179, 1], [179, 0]]]}
    )
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"features": [item()]})

    scenes = provider(settings, handler).discover(
        geometry, datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC)
    )
    assert len(requests) == 2
    assert len(scenes) == 1
    assert len(query_parts(geometry)) == 2


def test_radar_metadata_normalization(settings: Settings) -> None:
    raw = item()
    raw["properties"].update(
        {
            "s1:polarization": "DH",
            "sat:orbit_state": "descending",
            "sat:relative_orbit": 17,
            "sar:instrument_mode": "EW",
        }
    )
    acquired = acquisition_from_item(
        raw, "cdse", settings.providers.definitions["cdse_sentinelhub"]
    )
    assert acquired.polarisations == ("HH", "HV")
    assert acquired.relative_orbit == 17


def test_invalid_scene_metadata_is_a_gap(settings: Settings) -> None:
    raw = item(timestamp="2020-12-30T12:00:00")
    with pytest.raises(ProviderError, match="invalid_scene_metadata"):
        provider(settings, lambda _: httpx.Response(200, json={"features": [raw]})).discover(
            polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC)
        )


def test_https_pagination_cannot_downgrade(settings: Settings) -> None:
    with pytest.raises(ProviderError, match="cross_origin_pagination"):
        provider(
            settings,
            lambda _: httpx.Response(
                200,
                json={
                    "features": [],
                    "links": [{"rel": "next", "href": "http://provider.invalid/search"}],
                },
            ),
        ).discover(polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC))


@pytest.mark.parametrize("method", [12, None, [], "DELETE"])
def test_invalid_pagination_method_is_a_provider_error(settings: Settings, method: Any) -> None:
    with pytest.raises(ProviderError, match="invalid_pagination_method"):
        provider(
            settings,
            lambda _: httpx.Response(
                200,
                json={
                    "features": [],
                    "links": [
                        {"rel": "next", "href": "https://provider.invalid/page2", "method": method}
                    ],
                },
            ),
        ).discover(polygon(), datetime(2020, 12, 28, tzinfo=UTC), datetime(2021, 1, 4, tzinfo=UTC))
