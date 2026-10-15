"""Bounded CDSE discovery and scene-verified numerical cutouts on one frozen grid."""

import hashlib
import io
import json
import math
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import numpy as np
from numpy.typing import NDArray
from pydantic import HttpUrl

from allyourbase.monitor.config import Grid, MonitorConfig
from allyourbase.providers.auth import TokenProvider
from allyourbase.providers.contracts import Acquisition, ProviderError
from allyourbase.providers.http import Transport
from allyourbase.providers.stac import STACProvider, acquisition_from_item


@dataclass
class Cutout:
    acquisition: Acquisition
    pixels: NDArray[np.float32]
    grid: Grid


def radar_group(scene: Acquisition) -> tuple[int, str, str, tuple[str, ...]]:
    if (
        scene.sensor != "s1"
        or scene.relative_orbit is None
        or scene.orbit_direction is None
        or scene.instrument_mode != "IW"
        or set(scene.polarisations) != {"VV", "VH"}
    ):
        raise ProviderError("radar_geometry_unverified", scene.provider)
    return (
        scene.relative_orbit,
        scene.orbit_direction,
        scene.instrument_mode,
        tuple(sorted(scene.polarisations)),
    )


def same_observation(left: Acquisition, right: Acquisition) -> bool:
    """Adjacent/reprocessed products from one pass are not independent observations.

    Sentinel-2 documentation bounds separate same-platform acquisitions by >50 min.
    Keep a conservative separation for the small-AOI MVP, within radar orbit groups.
    """
    if left.sensor != right.sensor or left.platform != right.platform:
        return False
    if left.sensor == "s1" and radar_group(left) != radar_group(right):
        return False
    return abs((left.acquired_at - right.acquired_at).total_seconds()) < 50 * 60


class LimitedTransport(Transport):
    def __init__(self, client: httpx.Client, config: MonitorConfig) -> None:
        super().__init__(client, config.http, config.retry_attempts)
        self.remaining = config.max_requests

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self.remaining <= 0:
            raise ProviderError("request_cap_reached", str(kwargs.get("provider", "cdse")))
        attempts = self.attempts
        self.attempts = min(attempts, self.remaining)
        count = len(self.observations)
        try:
            return super().request(method, url, **kwargs)
        finally:
            self.remaining -= len(self.observations) - count
            self.attempts = attempts


def process_request(scene: Acquisition, grid: Grid, config: MonitorConfig) -> dict[str, Any]:
    if scene.sensor == "s1":
        radar_group(scene)
        assert scene.orbit_direction is not None
        bands, units = (
            ["VV", "VH", "dataMask", "shadowMask"],
            ["LINEAR_POWER", "LINEAR_POWER", "DN", "DN"],
        )
        product = "sentinel1ProductId"
        filters = {
            "acquisitionMode": "IW",
            "orbitDirection": scene.orbit_direction.upper(),
            "polarization": "DV",
            "resolution": "HIGH",
        }
        processing = {
            "backCoeff": "GAMMA0_TERRAIN",
            "orthorectify": True,
            "demInstance": "COPERNICUS_30",
            "speckleFilter": {
                "type": "LEE",
                "windowSizeX": config.lee_window,
                "windowSizeY": config.lee_window,
            },
            "upsampling": "NEAREST",
        }
    else:
        bands, units = (
            ["B02", "B03", "B04", "B08", "SCL", "dataMask"],
            ["REFLECTANCE"] * 4 + ["DN", "DN"],
        )
        product, filters = "sentinel2ProductId", {}
        processing = {"upsampling": "NEAREST", "downsampling": "NEAREST", "harmonizeValues": True}
    script = (
        "//VERSION=3\nfunction setup(){return {input:[{bands:"
        + json.dumps(bands)
        + ",units:"
        + json.dumps(units)
        + '}],mosaicking:"ORBIT",output:{id:"data",bands:'
        + str(len(bands))
        + ',sampleType:"FLOAT32"}};}\n'
        + "function evaluatePixel(samples){if(samples.length!==1){return "
        + json.dumps([0] * len(bands))
        + ";}var s=samples[0];return ["
        + ",".join("s." + b for b in bands)
        + "];}\n"
        + "function updateOutputMetadata(scenes,inputMetadata,outputMetadata){"
        "outputMetadata.userData={scene_ids:scenes.orbits.reduce(function(ids,o){"
        "return ids.concat(o.tiles.map(function(t){return t." + product + ";}));},[])};}"
    )
    margin = timedelta(seconds=1)
    return {
        "input": {
            "bounds": {
                "bbox": list(grid.bbox),
                "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{grid.epsg}"},
            },
            "data": [
                {
                    "type": scene.collection,
                    "dataFilter": {
                        "timeRange": {
                            "from": (scene.acquired_at - margin).isoformat(),
                            "to": (
                                (scene.acquisition_end or scene.acquired_at) + margin
                            ).isoformat(),
                        },
                        **filters,
                    },
                    "processing": processing,
                }
            ],
        },
        "output": {
            "width": 100,
            "height": 100,
            "responses": [
                {"identifier": "data", "format": {"type": "image/tiff"}},
                {"identifier": "userdata", "format": {"type": "application/json"}},
            ],
        },
        "evalscript": script,
    }


def read_pixels(image: bytes, grid: Grid, sensor: str) -> NDArray[np.float32]:
    from rasterio.io import MemoryFile

    with MemoryFile(image) as memory, memory.open() as dataset:
        if (
            dataset.crs is None
            or dataset.crs.to_epsg() != grid.epsg
            or dataset.width != 100
            or dataset.height != 100
            or dataset.count != (6 if sensor == "s2" else 4)
            or set(dataset.dtypes) != {"float32"}
        ):
            raise ValueError("cutout grid/band contract mismatch")
        if not all(
            math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
            for a, b in zip(tuple(dataset.transform)[:6], tuple(grid.transform)[:6], strict=True)
        ):
            raise ValueError("cutout transform mismatch")
        pixels = dataset.read().astype(np.float32)
    categorical = pixels[4:] if sensor == "s2" else pixels[2:]
    if not np.isfinite(categorical).all() or not np.isin(categorical[-1], [0, 1]).all():
        raise ValueError("invalid categorical mask")
    if sensor == "s2":
        if not np.isin(pixels[4], np.arange(12)).all():
            raise ValueError("SCL must use nearest-neighbour classes")
    elif not np.isin(categorical, [0, 1]).all():
        raise ValueError("invalid radar masks")
    return cast(NDArray[np.float32], pixels)


class Fetcher:
    def __init__(self, config: MonitorConfig, cache: Path, client: httpx.Client) -> None:
        self.config, self.cache = config, cache
        self.transport = LimitedTransport(client, config)
        self.auth = TokenProvider("cdse_monitor", config.provider, self.transport)

    def discover(
        self, grid: Grid, sensor: str, start: datetime, end: datetime
    ) -> list[Acquisition]:
        provider = self.config.provider.model_copy(
            update={
                "sensor": sensor,
                "collection": "sentinel-2-l2a" if sensor == "s2" else "sentinel-1-grd",
            }
        )
        discovery = STACProvider("cdse_monitor", provider, self.transport)
        discovery.auth = self.auth
        scenes = discovery.discover(grid.geographic(), start, end)
        if sensor == "s1":
            scenes = [self._orbit_metadata(s) for s in scenes]
        return scenes

    def _orbit_metadata(self, scene: Acquisition) -> Acquisition:
        if scene.relative_orbit is not None:
            return scene
        # Some Sentinel Hub Catalog responses omit relative orbit. Query the public
        # CDSE STAC by exact product ID; never infer it from direction or date.
        try:
            page = self.transport.json(
                "POST",
                "https://stac.dataspace.copernicus.eu/v1/search",
                provider="cdse_monitor",
                operation="orbit_metadata",
                json_body={
                    "collections": ["sentinel-1-grd"],
                    "ids": [scene.scene_id, scene.scene_id.removesuffix(".SAFE") + ".SAFE"],
                    "limit": 5,
                },
            )
            candidates = []
            provider = self.config.provider.model_copy(
                update={"catalogue_url": HttpUrl("https://stac.dataspace.copernicus.eu/v1")}
            )
            for raw in page.get("features", []):
                other = acquisition_from_item(raw, "cdse_monitor", provider)
                if (
                    other.scene_id.removesuffix(".SAFE") == scene.scene_id.removesuffix(".SAFE")
                    and other.acquired_at == scene.acquired_at
                    and other.relative_orbit is not None
                    and other.orbit_direction == scene.orbit_direction
                    and other.instrument_mode == scene.instrument_mode
                    and set(other.polarisations) == set(scene.polarisations)
                ):
                    candidates.append(other)
            if len({s.relative_orbit for s in candidates}) == 1:
                return scene.model_copy(update={"relative_orbit": candidates[0].relative_orbit})
        except (ProviderError, ValueError, KeyError, TypeError):
            pass
        return scene

    def cutout(self, scene: Acquisition, grid: Grid) -> Cutout:
        request = process_request(scene, grid, self.config)
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        directory = self.cache / key
        image_path, meta_path = directory / "data.tif", directory / "metadata.json"
        if (directory / "rejected-selection.json").exists():
            raise ProviderError("scene_selection_mismatch", "cdse_monitor")
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            image = image_path.read_bytes()
            if (
                metadata["request_sha256"] != key
                or hashlib.sha256(image).hexdigest() != metadata["sha256"]
            ):
                raise ProviderError("cache_integrity_failed", "cdse_monitor")
        else:
            headers = self.auth.headers() | {"Accept": "application/tar"}
            for attempt in range(self.config.retry_attempts):
                try:
                    response = self.transport.request(
                        "POST",
                        str(self.config.provider.process_url),
                        provider="cdse_monitor",
                        operation="process",
                        json_body=request,
                        headers=headers,
                        retry=False,
                        max_bytes=self.config.http.max_process_response_bytes,
                    )
                    break
                except ProviderError as exc:
                    # Only an explicit rate-limit rejection is safe to repeat here.
                    # Ambiguous charged POST failures stay visible; no blind retries.
                    if exc.code != "http_429" or attempt + 1 == self.config.retry_attempts:
                        raise
                    self.transport.sleep(
                        min(
                            self.config.http.max_retry_delay_seconds,
                            self.config.http.retry_base_seconds * 2**attempt,
                        )
                    )
            try:
                with tarfile.open(fileobj=io.BytesIO(response.content)) as archive:
                    parts = {}
                    for name, limit in [
                        ("data.tif", self.config.http.max_process_response_bytes),
                        ("userdata.json", self.config.http.max_metadata_response_bytes),
                    ]:
                        stream = archive.extractfile(name)
                        if stream is None:
                            raise ValueError("missing response part")
                        parts[name] = stream.read(limit + 1)
                        if len(parts[name]) > limit:
                            raise ValueError("response part too large")
            except (tarfile.TarError, KeyError):
                raise ValueError("invalid numerical response archive") from None
            image = parts["data.tif"]
            metadata = {
                "request_sha256": key,
                "sha256": hashlib.sha256(image).hexdigest(),
                "scene_ids": json.loads(parts["userdata.json"])["scene_ids"],
                "acquisition": scene.model_dump(mode="json"),
                "grid": grid.model_dump(mode="json"),
            }
        expected = scene.scene_id.removesuffix(".SAFE")
        if not metadata["scene_ids"] or {
            s.removesuffix(".SAFE") for s in metadata["scene_ids"]
        } != {expected}:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "rejected-selection.json").write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
            )
            raise ProviderError("scene_selection_mismatch", "cdse_monitor")
        pixels = read_pixels(image, grid, scene.sensor)
        if not meta_path.exists():
            directory.mkdir(parents=True, exist_ok=True)
            image_path.with_suffix(".tmp").write_bytes(image)
            image_path.with_suffix(".tmp").replace(image_path)
            temporary = meta_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            temporary.replace(meta_path)
        return Cutout(scene, pixels, grid)
