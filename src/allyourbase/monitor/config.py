"""Small, strict coordinate/configuration and frozen-grid contracts."""

import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from allyourbase.models.common import Contract, NonEmpty, Slug
from allyourbase.models.geometry import Geometry, Polygon
from allyourbase.models.settings import AccessSettings, Provider
from allyourbase.monitor import ANALYSIS_VERSION


class Location(Contract):
    id: Slug
    name: NonEmpty
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    size_m: Literal[1000] = 1000


class Locations(Contract):
    sites: Annotated[list[Location], Field(min_length=1)]

    @model_validator(mode="after")
    def distinct(self) -> "Locations":
        if len({s.id for s in self.sites}) != len(self.sites):
            raise ValueError("location IDs must be distinct")
        return self


class MonitorConfig(Contract):
    schema_version: Literal[1] = 1
    optical_threshold: Annotated[float, Field(gt=0)] = 0.10
    radar_threshold_db: Annotated[float, Field(gt=0)] = 3.0
    minimum_patch_cells: Annotated[int, Field(ge=1)] = 9
    minimum_baseline_observations: Annotated[int, Field(ge=2)] = 2
    minimum_common_coverage: Annotated[float, Field(ge=0.7, le=1)] = 0.7
    cloud_buffer_cells: Annotated[int, Field(ge=0, le=5)] = 1
    lee_window: Literal[3, 5, 7] = 3
    max_requests: Annotated[int, Field(ge=1, le=500)] = 100
    retry_attempts: Annotated[int, Field(ge=1, le=5)] = 3
    optical_preview_max: Annotated[float, Field(gt=0)] = 0.4
    radar_preview_db: tuple[float, float] = (-25.0, 0.0)
    provider: Provider
    http: AccessSettings

    @model_validator(mode="after")
    def bounded(self) -> "MonitorConfig":
        if self.radar_preview_db[0] >= self.radar_preview_db[1]:
            raise ValueError("radar preview stretch must increase")
        if self.provider.kind != "sentinelhub":
            raise ValueError("the MVP uses CDSE Sentinel Hub")
        return self

    def analysis_version(self) -> str:
        content = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return ANALYSIS_VERSION + "+" + hashlib.sha256(content.encode()).hexdigest()[:12]

    def thresholds(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"provider", "http"})


class Grid(Contract):
    epsg: int
    bbox: tuple[float, float, float, float]
    width: Literal[100] = 100
    height: Literal[100] = 100
    resolution_m: Literal[10] = 10

    @property
    def transform(self) -> Any:
        from rasterio.transform import from_origin

        return from_origin(self.bbox[0], self.bbox[3], 10, 10)

    def geographic(self) -> Geometry:
        from pyproj import Transformer

        transform = Transformer.from_crs(self.epsg, 4326, always_xy=True)
        x0, y0, x1, y1 = self.bbox
        ring = []
        # Sample edges to retain curved projected footprints for catalogue discovery.
        for start, end in [
            ((x0, y0), (x1, y0)),
            ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)),
            ((x0, y1), (x0, y0)),
        ]:
            for i in range(10):
                x, y = (
                    start[0] + (end[0] - start[0]) * i / 10,
                    start[1] + (end[1] - start[1]) * i / 10,
                )
                longitude, latitude = transform.transform(x, y)
                ring.append(((longitude + 180) % 360 - 180, latitude))
        ring.append(ring[0])
        return Polygon(type="Polygon", coordinates=[ring])


def make_grid(location: Location) -> Grid:
    from pyproj import Transformer

    lon, lat = location.longitude, location.latitude
    if lat >= 84:
        epsg = 32661  # UPS north uses metres, including the pole.
    elif lat <= -80:
        epsg = 32761
    else:
        zone = min(60, math.floor((lon + 180) / 6) + 1)
        epsg = (32600 if lat >= 0 else 32700) + zone
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    if not all(math.isfinite(v) for v in (x, y)):
        raise ValueError("location cannot be projected")
    return Grid(epsg=epsg, bbox=(x - 500, y - 500, x + 500, y + 500))


def windows(end_date: date | None = None) -> tuple[datetime, datetime, datetime]:
    """End date is exclusive UTC midnight; default excludes today's incomplete day."""
    end = datetime.combine(end_date or datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
    start = end - timedelta(days=7)
    return start - timedelta(days=28), start, end


def freeze_grid(location: Location, path: Path) -> Grid:
    grid = make_grid(location)
    content = {"location": location.model_dump(mode="json"), "grid": grid.model_dump(mode="json")}
    if path.exists():
        retained = json.loads(path.read_text(encoding="utf-8"))
        # Renaming a display label is allowed; coordinate/size/CRS changes need a new ID.
        expected = {k: v for k, v in content["location"].items() if k != "name"}
        actual = {k: v for k, v in retained["location"].items() if k != "name"}
        if actual != expected or retained["grid"] != content["grid"]:
            raise ValueError("location grid changed; use a new stable location ID")
        return Grid.model_validate(retained["grid"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    return grid
