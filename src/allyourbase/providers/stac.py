"""STAC discovery with pagination, deduplication and half-open time filtering."""

import json
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

from pydantic import ValidationError

from allyourbase.models.geometry import Geometry
from allyourbase.models.settings import Provider
from allyourbase.providers.auth import TokenProvider
from allyourbase.providers.contracts import Acquisition, Asset, ProviderError
from allyourbase.providers.http import Transport
from allyourbase.providers.spatial import query_parts


def acquisition_from_item(
    item: dict[str, Any], provider_id: str, provider: Provider
) -> Acquisition:
    properties = item.get("properties", {})
    if not isinstance(properties, dict) or not isinstance(item.get("assets", {}), dict):
        raise ValueError("invalid scene structure")
    polarisations = properties.get("sar:polarizations", [])
    if not polarisations:
        code = properties.get("s1:polarization")
        polarisations = {"DV": ["VV", "VH"], "DH": ["HH", "HV"], "SV": ["VV"], "SH": ["HH"]}.get(
            str(code), []
        )
    assets = tuple(
        Asset(
            key=key,
            href=value["href"],
            media_type=value.get("type"),
            roles=tuple(value.get("roles", [])),
        )
        for key, value in item.get("assets", {}).items()
        if isinstance(value, dict) and isinstance(value.get("href"), str)
    )
    return Acquisition.model_validate(
        {
            "provider": provider_id,
            "collection": item.get("collection", provider.collection),
            "scene_id": item["id"],
            "sensor": provider.sensor,
            "acquired_at": properties.get("datetime") or properties.get("start_datetime"),
            "acquisition_end": properties.get("end_datetime"),
            "platform": properties.get("platform"),
            "orbit_direction": properties.get("sat:orbit_state"),
            "relative_orbit": properties.get("sat:relative_orbit"),
            "instrument_mode": properties.get("sar:instrument_mode"),
            "polarisations": tuple(str(p).upper() for p in polarisations),
            "cloud_cover": properties.get("eo:cloud_cover"),
            "assets": assets,
        }
    )


class STACProvider:
    def __init__(self, provider_id: str, config: Provider, transport: Transport) -> None:
        self.provider_id = provider_id
        self.config = config
        self.transport = transport
        self.auth = (
            TokenProvider(provider_id, config, transport) if config.kind == "sentinelhub" else None
        )

    def discover(self, geometry: Geometry, start: datetime, end: datetime) -> list[Acquisition]:
        if start.utcoffset() is None or end.utcoffset() is None or end <= start:
            raise ValueError("discovery needs an increasing timezone-aware interval")
        acquisitions: dict[str, Acquisition] = {}
        for part in query_parts(geometry):
            for item in self._items(part, start, end):
                try:
                    acquisition = acquisition_from_item(item, self.provider_id, self.config)
                except (ValidationError, KeyError, TypeError, ValueError):
                    raise ProviderError("invalid_scene_metadata", self.provider_id) from None
                if start <= acquisition.acquired_at < end:
                    previous = acquisitions.get(acquisition.scene_id)
                    if previous is not None and previous.model_dump(
                        mode="json"
                    ) != acquisition.model_dump(mode="json"):
                        raise ProviderError("conflicting_duplicate_scene", self.provider_id)
                    acquisitions[acquisition.scene_id] = acquisition
        return sorted(acquisitions.values(), key=lambda a: (a.acquired_at, a.scene_id))

    def _items(
        self, geometry: dict[str, Any], start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        search_url = str(self.config.catalogue_url).rstrip("/") + "/search"
        method, url = "POST", search_url
        original: dict[str, Any] = {
            "collections": [self.config.collection],
            "intersects": geometry,
            "datetime": f"{start.isoformat()}/{end.isoformat()}",
            "limit": self.transport.settings.stac_page_size,
        }
        body: dict[str, Any] | None = original.copy()
        seen_pages: set[str] = set()
        items: list[dict[str, Any]] = []
        for _ in range(self.transport.settings.stac_max_pages):
            fingerprint = json.dumps([method, url, body], sort_keys=True)
            if fingerprint in seen_pages:
                raise ProviderError("pagination_cycle", self.provider_id)
            seen_pages.add(fingerprint)
            headers = self.auth.headers() if self.auth else None
            page = self.transport.json(
                method,
                url,
                provider=self.provider_id,
                operation="discovery",
                json_body=body,
                headers=headers,
            )
            features = page.get("features")
            if not isinstance(features, list) or not all(isinstance(i, dict) for i in features):
                raise ProviderError("invalid_stac_page", self.provider_id)
            items.extend(features)
            links = page.get("links", [])
            context = page.get("context", {})
            if (
                not isinstance(links, list)
                or not all(isinstance(link, dict) for link in links)
                or not isinstance(context, dict)
            ):
                raise ProviderError("invalid_stac_page", self.provider_id)
            next_link = next((link for link in links if link.get("rel") == "next"), None)
            if next_link:
                if not isinstance(next_link.get("href"), str):
                    raise ProviderError("invalid_pagination_link", self.provider_id)
                next_url = urljoin(url, next_link["href"])
                if (urlsplit(next_url).netloc, urlsplit(next_url).scheme) != (
                    urlsplit(search_url).netloc,
                    urlsplit(search_url).scheme,
                ):
                    raise ProviderError("cross_origin_pagination", self.provider_id)
                url = next_url
                next_method = next_link.get("method", "GET")
                if not isinstance(next_method, str):
                    raise ProviderError("invalid_pagination_method", self.provider_id)
                method = next_method.upper()
                if method not in {"GET", "POST"}:
                    raise ProviderError("invalid_pagination_method", self.provider_id)
                next_body = next_link.get("body", {})
                if not isinstance(next_body, dict):
                    raise ProviderError("invalid_pagination_body", self.provider_id)
                body = (
                    (original | next_body if next_link.get("merge") else next_body)
                    if method == "POST"
                    else None
                )
            elif context.get("next") is not None:
                method, url = "POST", search_url
                body = original | {"next": context["next"]}
            else:
                return items
        raise ProviderError("pagination_limit", self.provider_id)
