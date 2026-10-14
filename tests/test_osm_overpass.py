import json
from pathlib import Path

import httpx
import pytest
from pydantic import HttpUrl

from allyourbase.loading import InputError
from allyourbase.sources.connectors import parse_records
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.osm import overpass_features
from allyourbase.sources.snapshots import fetch_snapshot, save_snapshot, verify_snapshot


def points(values: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"lon": x, "lat": y} for x, y in values]


def test_centres_remain_points() -> None:
    data = {
        "elements": [
            {"type": "way", "id": 1, "tags": {"military": "base"}, "center": {"lon": 20, "lat": 60}}
        ]
    }
    feature = overpass_features(data)["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["geometry_role"] == "bbox_center"
    assert feature["properties"]["geometry_issue"] == "footprint_not_requested"


def test_fragmented_relation_keeps_hole() -> None:
    data = {
        "elements": [
            {
                "type": "relation",
                "id": 1,
                "tags": {"landuse": "military", "type": "multipolygon"},
                "members": [
                    {"type": "way", "role": "outer", "geometry": points([(0, 0), (2, 0), (2, 2)])},
                    {"type": "way", "role": "outer", "geometry": points([(2, 2), (0, 2), (0, 0)])},
                    {
                        "type": "way",
                        "role": "inner",
                        "geometry": points([(0.5, 0.5), (1, 0.5), (1, 1), (0.5, 1), (0.5, 0.5)]),
                    },
                ],
            }
        ]
    }
    feature = overpass_features(data)["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert len(feature["geometry"]["coordinates"]) == 2
    assert feature["properties"]["geometry_role"] == "source_polygon"


@pytest.mark.parametrize(
    "geometry", [points([(0, 0), (1, 0), (1, 1)]), points([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])]
)
def test_incomplete_or_invalid_way_never_becomes_a_footprint(
    geometry: list[dict[str, float]],
) -> None:
    feature = overpass_features(
        {
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "tags": {"military": "base"},
                    "geometry": geometry,
                    "center": {"lon": 0.5, "lat": 0.5},
                }
            ]
        }
    )["features"][0]
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["geometry_issue"] == "incomplete_or_invalid_source_area"


def test_relation_crossing_antimeridian() -> None:
    feature = overpass_features(
        {
            "elements": [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"landuse": "military", "type": "multipolygon"},
                    "members": [
                        {
                            "type": "way",
                            "role": "outer",
                            "geometry": points(
                                [(179, 0), (-179, 0), (-179, 1), (179, 1), (179, 0)]
                            ),
                        }
                    ],
                }
            ]
        }
    )["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"]["geometry_role"] == "source_polygon"


def test_partial_results_fail_closed() -> None:
    with pytest.raises(InputError, match="partial/error"):
        overpass_features({"elements": [], "remark": "runtime error: timeout"})


def test_missing_geometry_is_not_silently_dropped() -> None:
    with pytest.raises(InputError, match="lacks usable geometry"):
        overpass_features({"elements": [{"type": "way", "id": 1, "tags": {"military": "base"}}]})


def test_zone_records_and_source_notes(tmp_path: Path, spec: SourceSpec) -> None:
    spec = spec.model_copy(update={"connector": "osm"})
    data = {
        "elements": [
            {
                "type": "way",
                "id": i,
                "tags": tags,
                "geometry": points([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
            }
            for i, tags in enumerate(
                [
                    {"man_made": "pier", "note": "Estimated outline"},
                    {"amenity": "parking"},
                    {"natural": "water"},
                ],
                1,
            )
        ]
    }
    path = tmp_path / "overpass.json"
    path.write_text(json.dumps(data))
    manifest, payload = verify_snapshot(save_snapshot(tmp_path / "data", spec, path))
    rows = list(parse_records(manifest, payload))
    assert [row.kind for row in rows] == ["zone", "zone", "mask"]
    assert rows[0].attributes["note"] == "Estimated outline"
    assert all(row.geometry is not None for row in rows)


def test_osm_query_transport_and_exact_query_retained(
    tmp_path: Path, spec: SourceSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    received = []

    def respond(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json={"elements": []})

    client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs)
    )
    spec = spec.model_copy(
        update={"connector": "osm", "download_url": HttpUrl("https://example.invalid/interpreter")}
    )
    query = "[out:json][timeout:5];node(1);out;"
    manifest, payload = verify_snapshot(fetch_snapshot(tmp_path, spec, query=query))
    assert received[0].url.params["data"] == query
    assert "query" not in received[0].url.params
    assert received[0].headers["accept"] == "application/json"
    assert json.loads(payload.read_text())["allyourbase_query"] == query
    assert manifest.spec.connector == "osm"


def test_outer_island_inside_hole_is_preserved() -> None:
    from shapely.geometry import shape

    rings: list[tuple[str, list[tuple[float, float]]]] = [
        ("outer", [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]),
        ("inner", [(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)]),
        ("outer", [(1.5, 1.5), (2.5, 1.5), (2.5, 2.5), (1.5, 2.5), (1.5, 1.5)]),
    ]
    data = {
        "elements": [
            {
                "type": "relation",
                "id": 1,
                "tags": {"landuse": "military", "type": "multipolygon"},
                "members": [
                    {"type": "way", "role": role, "geometry": points(ring)} for role, ring in rings
                ],
            }
        ]
    }
    feature = overpass_features(data)["features"][0]
    assert shape(feature["geometry"]).area == 13
