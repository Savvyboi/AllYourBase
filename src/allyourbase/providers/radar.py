"""One-acquisition FLOAT32 radar requests, with source IDs and charge accounting."""

import hashlib
import io
import json
import math
import tarfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from allyourbase import ALGO_VERSION
from allyourbase.models.geometry import Geometry, anchor_of, shape_on_anchor
from allyourbase.models.settings import Provider, Settings
from allyourbase.providers.auth import TokenProvider
from allyourbase.providers.budget import BudgetLedger
from allyourbase.providers.contracts import Acquisition, ProviderError
from allyourbase.providers.http import Transport


def site_grid(geometry: Geometry, settings: Settings) -> dict[str, Any]:
    try:
        from pyproj import Transformer
        from shapely import transform
    except ImportError:
        raise ProviderError("access_extra_required", "radar") from None
    aoi = shape_on_anchor(geometry, anchor_of(geometry))
    centroid = aoi.centroid
    longitude = (centroid.x + 180) % 360 - 180
    latitude = centroid.y
    if latitude > settings.preprocessing.north_polar_above:
        epsg = 3413
    elif latitude < settings.preprocessing.south_polar_below:
        epsg = 3031
    else:
        zone = min(60, math.floor((longitude + 180) / 6) + 1)
        epsg = (32600 if latitude >= 0 else 32700) + zone
    projected = transform(
        aoi,
        Transformer.from_crs(4326, epsg, always_xy=True, force_over=True).transform,
        interleaved=False,
    )
    resolution = settings.preprocessing.resolution_m
    min_x, min_y, max_x, max_y = projected.bounds
    if not all(math.isfinite(v) for v in projected.bounds):
        raise ProviderError("invalid_projected_grid", "radar")
    bbox = [
        math.floor(min_x / resolution) * resolution,
        math.floor(min_y / resolution) * resolution,
        math.ceil(max_x / resolution) * resolution,
        math.ceil(max_y / resolution) * resolution,
    ]
    width, height = int((bbox[2] - bbox[0]) / resolution), int((bbox[3] - bbox[1]) / resolution)
    if (
        width < 1
        or height < 1
        or width * height > settings.access.max_window_pixels
        or max(width, height) > settings.access.max_process_dimension_px
    ):
        raise ProviderError("radar_grid_limit", "radar")
    return {
        "epsg": epsg,
        "bbox": bbox,
        "width": width,
        "height": height,
        "resolution_m": resolution,
    }


def radar_request(
    acquisition: Acquisition, geometry: Geometry, provider: Provider, settings: Settings
) -> dict[str, Any]:
    if (
        acquisition.sensor != "s1"
        or acquisition.instrument_mode is None
        or acquisition.orbit_direction is None
    ):
        raise ProviderError("radar_geometry_metadata_missing", acquisition.provider)
    processing = settings.preprocessing.radar
    pair = next(
        (
            pair
            for pair in processing.polarisation_pairs
            if set(pair).issubset(acquisition.polarisations)
        ),
        None,
    )
    if pair is None:
        raise ProviderError("dual_polarisation_missing", acquisition.provider)
    grid = site_grid(geometry, settings)
    co, cross = pair
    bands = [co, cross, *processing.auxiliary_bands]
    evalscript = (
        "//VERSION=3\n"
        "function setup(){return {input:"
        + json.dumps(bands)
        + ",mosaicking:'ORBIT',output:{id:'radar',bands:"
        + str(len(bands))
        + ",sampleType:'FLOAT32'}};}\n"
        "function evaluatePixel(samples){if(samples.length!==1){return "
        + json.dumps([0] * len(bands))
        + ";}var s=samples[0];return ["
        + ",".join("s." + band for band in bands)
        + "];}\n"
        "function updateOutputMetadata(scenes,inputMetadata,outputMetadata){"
        "outputMetadata.userData={scene_ids:scenes.orbits.reduce(function(ids,orbit){"
        "return ids.concat(orbit.tiles.map(function(t){return t.sentinel1ProductId;}));},[])};}"
    )
    margin = timedelta(seconds=settings.access.radar_time_margin_seconds)
    start = acquisition.acquired_at - margin
    end = (acquisition.acquisition_end or acquisition.acquired_at) + margin
    return {
        "input": {
            "bounds": {
                "bbox": grid["bbox"],
                "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{grid['epsg']}"},
            },
            "data": [
                {
                    "type": provider.collection,
                    "dataFilter": {
                        "timeRange": {"from": start.isoformat(), "to": end.isoformat()},
                        "acquisitionMode": acquisition.instrument_mode,
                        "orbitDirection": acquisition.orbit_direction.upper(),
                        "polarization": "DV" if co == "VV" else "DH",
                        "resolution": processing.resolution,
                    },
                    "processing": {
                        "backCoeff": processing.backscatter_coefficient,
                        "orthorectify": processing.orthorectify,
                        "demInstance": processing.dem,
                    },
                }
            ],
        },
        "output": {
            "width": grid["width"],
            "height": grid["height"],
            "responses": [
                {"identifier": "radar", "format": {"type": "image/tiff"}},
                {"identifier": "userdata", "format": {"type": "application/json"}},
            ],
        },
        "evalscript": evalscript,
    }


def fetch_radar_window(
    acquisition: Acquisition,
    geometry: Geometry,
    provider: Provider,
    settings: Settings,
    transport: Transport,
    ledger: BudgetLedger,
    directory: Path,
    auth: TokenProvider | None = None,
) -> dict[str, Any]:
    try:
        import numpy as np
        from rasterio.io import MemoryFile
    except ImportError:
        raise ProviderError("access_extra_required", acquisition.provider) from None
    request = radar_request(acquisition, geometry, provider, settings)
    headers = (auth or TokenProvider(acquisition.provider, provider, transport)).headers()
    headers["Accept"] = "application/tar"
    reservation = ledger.reserve(acquisition.provider, acquisition.scene_id)
    try:
        response = transport.request(
            "POST",
            str(provider.process_url),
            provider=acquisition.provider,
            operation="radar_process",
            json_body=request,
            headers=headers,
            retry=False,
            max_bytes=settings.access.max_process_response_bytes,
        )
    except ProviderError as exc:
        observation = transport.observations[-1] if transport.observations else None
        units = (
            observation.processing_units
            if observation and observation.operation == "radar_process"
            else None
        )
        ledger.finish(reservation, units, exc.code)
        raise
    ledger.finish(reservation, transport.observations[-1].processing_units, "response_received")
    try:
        with tarfile.open(fileobj=io.BytesIO(response.content)) as archive:
            members = {member.name: member for member in archive.getmembers() if member.isfile()}
            image_stream = archive.extractfile(members["radar.tif"])
            metadata_stream = archive.extractfile(members["userdata.json"])
            if image_stream is None or metadata_stream is None:
                raise ValueError
            image = image_stream.read(settings.access.max_process_response_bytes + 1)
            metadata_bytes = metadata_stream.read(settings.access.max_metadata_response_bytes + 1)
            if (
                len(image) > settings.access.max_process_response_bytes
                or len(metadata_bytes) > settings.access.max_metadata_response_bytes
            ):
                raise ProviderError("response_size_limit", acquisition.provider)
            metadata = json.loads(metadata_bytes)
        if not isinstance(metadata, dict):
            raise ProviderError("invalid_radar_response", acquisition.provider)
        expected = acquisition.scene_id.removesuffix(".SAFE")
        scene_ids = metadata.get("scene_ids", [])
        if (
            not isinstance(scene_ids, list)
            or not scene_ids
            or not all(isinstance(scene_id, str) for scene_id in scene_ids)
            or {scene_id.removesuffix(".SAFE") for scene_id in scene_ids} != {expected}
        ):
            raise ProviderError("radar_scene_selection_mismatch", acquisition.provider)
        grid = site_grid(geometry, settings)
        with MemoryFile(image) as memory, memory.open() as dataset:
            if dataset.count != 4 or set(dataset.dtypes) != {"float32"}:
                raise ProviderError("radar_band_contract_mismatch", acquisition.provider)
            if (
                dataset.crs is None
                or dataset.crs.to_epsg() != grid["epsg"]
                or dataset.width != grid["width"]
                or dataset.height != grid["height"]
            ):
                raise ProviderError("radar_grid_mismatch", acquisition.provider)
            expected_transform = [
                grid["resolution_m"],
                0,
                grid["bbox"][0],
                0,
                -grid["resolution_m"],
                grid["bbox"][3],
            ]
            if not all(
                math.isclose(actual, expected)
                for actual, expected in zip(
                    tuple(dataset.transform)[:6], expected_transform, strict=True
                )
            ):
                raise ProviderError("radar_transform_mismatch", acquisition.provider)
            pixels = dataset.read()
            if not np.isfinite(pixels).all():
                raise ProviderError("radar_nonfinite_pixels", acquisition.provider)
            if not np.isin(pixels[2:], [0, 1]).all():
                raise ProviderError("radar_mask_contract_mismatch", acquisition.provider)
            valid = int(((pixels[3] == 1) & (pixels[2] == 0)).sum())
            if valid == 0:
                raise ProviderError("radar_no_valid_pixels", acquisition.provider)
        directory.mkdir(parents=True, exist_ok=True)
        filename = hashlib.sha256(acquisition.scene_id.encode()).hexdigest() + ".tif"
        path = directory / filename
        temporary = directory / ("." + filename + ".tmp")
        temporary.write_bytes(image)
        temporary.replace(path)
        return {
            "provider": acquisition.provider,
            "scene_ids": scene_ids,
            "requested_scene_id": acquisition.scene_id,
            "algo_version": ALGO_VERSION,
            "file": filename,
            "sha256": hashlib.sha256(image).hexdigest(),
            "grid": grid,
            "bands": [
                *next(
                    pair
                    for pair in settings.preprocessing.radar.polarisation_pairs
                    if set(pair).issubset(acquisition.polarisations)
                ),
                *settings.preprocessing.radar.auxiliary_bands,
            ],
            "valid_pixels": valid,
            "native_spacing_m": provider.native_spacing_by_mode.get(
                acquisition.instrument_mode or ""
            ),
            "processing_units": transport.observations[-1].processing_units,
        }
    except ProviderError:
        raise
    except (tarfile.TarError, KeyError, ValueError, TypeError, OSError):
        raise ProviderError("invalid_radar_response", acquisition.provider) from None
