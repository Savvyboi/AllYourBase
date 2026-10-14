"""Offline acceptance checks for bounded optical access-spike evidence."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from shapely.geometry import box, shape

from allyourbase.models.settings import Settings
from allyourbase.providers.contracts import Acquisition, public_url
from allyourbase.providers.spatial import query_parts
from allyourbase.providers.spike import AccessArea, write_json


def _validate_optical_report(
    directory: Path, areas: list[AccessArea], settings: Settings, provider_id: str
) -> dict[str, Any]:
    """Require complete bands, source identity, bounded valid grids and file hashes.

    This checks saved evidence; it does not re-fetch sources, establish clear-sky
    observations, measure network transfer or prove runtime resume/locking.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds

    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    provider = settings.providers.definitions.get(provider_id)
    if (
        provider is None
        or provider.sensor != "s2"
        or not areas
        or not report["run_finished"]
        or any(failure["provider"] == provider_id for failure in report["failures"])
        or not report["pixel_requests"]["optical"]
        or provider_id not in report["providers"]
    ):
        raise ValueError("incomplete optical spike")
    expected_areas = {area.site_id: area.geometry.model_dump(mode="json") for area in areas}
    actual_areas = {area["site_id"]: area["geometry"] for area in report["areas"]}
    if actual_areas != expected_areas or len(report["areas"]) != len(areas):
        raise ValueError("area provenance mismatch")
    payload = json.loads((directory / "acquisitions.json").read_text(encoding="utf-8"))
    scenes = {
        (record["site_id"], record["scene_id"]): Acquisition.model_validate(
            {key: value for key, value in record.items() if key != "site_id"}
        )
        for record in payload["acquisitions"]
        if record["provider"] == provider_id
    }
    downloads = [d for d in report["downloads"] if d["provider"] == provider_id]
    if Counter(d["site_id"] for d in downloads) != Counter(expected_areas.keys()):
        raise ValueError("expected one optical acquisition per area")
    checked = []
    for area in areas:
        download = next(d for d in downloads if d["site_id"] == area.site_id)
        files = download.get("files", [])
        parts = query_parts(area.geometry)
        expected = Counter(
            (band, part)
            for band in settings.preprocessing.optical_bands
            for part in range(len(parts))
        )
        if download["status"] != "ok" or Counter((f["band"], f["part"]) for f in files) != expected:
            raise ValueError("incomplete optical bands")
        scene_ids = {f["scene_id"] for f in files}
        if len(scene_ids) != 1:
            raise ValueError("mixed optical acquisitions")
        scene = scenes.get((area.site_id, next(iter(scene_ids))))
        if scene is None or scene.sensor != "s2" or scene.collection != provider.collection:
            raise ValueError("scene provenance mismatch")
        assets = {asset.key: asset for asset in scene.assets}
        chip_directory = (directory / "chips" / area.site_id / provider_id).resolve()
        for record in files:
            if record["provider"] != provider_id:
                raise ValueError("file provider mismatch")
            band = record["band"]
            asset = next(
                (assets[key] for key in provider.band_assets[band.lower()] if key in assets), None
            )
            if asset is None or record["source"] != public_url(asset.href):
                raise ValueError("asset provenance mismatch")
            filename = record["file"]
            if Path(filename).name != filename:
                raise ValueError("invalid chip path")
            chip_path = (chip_directory / filename).resolve()
            if not chip_path.is_relative_to(chip_directory):
                raise ValueError("chip path outside report")
            with chip_path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != record["sha256"]:
                raise ValueError("chip hash mismatch")
            with rasterio.open(chip_path) as chip:
                if (
                    chip.crs is None
                    or chip.count != 1
                    or chip.width != record["width"]
                    or chip.height != record["height"]
                    or str(chip.crs) != record["crs"]
                    or chip.width * chip.height > settings.access.max_window_pixels
                    or chip.descriptions != (band,)
                ):
                    raise ValueError("chip metadata mismatch")
                transform = chip.transform
                if (
                    not all(math.isfinite(value) for value in transform)
                    or transform.a <= 0
                    or transform.e >= 0
                    or transform.b != 0
                    or transform.d != 0
                    or not np.allclose(
                        [transform.a, -transform.e], record["pixel_size"], rtol=0, atol=1e-8
                    )
                ):
                    raise ValueError("invalid chip grid")
                bounds = transform_bounds(
                    "EPSG:4326", chip.crs, *shape(parts[record["part"]]).bounds
                )
                if (
                    not box(*chip.bounds).intersects(box(*bounds))
                    or chip.width > math.ceil((bounds[2] - bounds[0]) / transform.a) + 2
                    or chip.height > math.ceil((bounds[3] - bounds[1]) / -transform.e) + 2
                ):
                    raise ValueError("chip outside bounded area")
                pixels = chip.read(1, masked=True).compressed()
                if not pixels.size or not np.isfinite(pixels).all():
                    raise ValueError("chip has no finite valid pixels")
                if band == "SCL" and (
                    not np.isin(pixels, range(12)).all() or not np.any(pixels > 0)
                ):
                    raise ValueError("invalid classification pixels")
                checked.append(
                    {
                        "site_id": area.site_id,
                        "scene_id": scene.scene_id,
                        "band": band,
                        "part": record["part"],
                        "file": filename,
                        "sha256": digest,
                        "crs": str(chip.crs),
                        "width": chip.width,
                        "height": chip.height,
                        "transform": list(transform)[:6],
                        "bounds": list(chip.bounds),
                        "valid_pixels": int(pixels.size),
                    }
                )
    summary = {
        "validation_version": 1,
        "status": "pass",
        "run_id": directory.name,
        "provider": provider_id,
        "site_count": len(areas),
        "file_count": len(checked),
        "files": checked,
    }
    write_json(directory / "optical-validation.json", summary)
    return summary


def validate_optical_report(
    directory: Path, areas: list[AccessArea], settings: Settings, provider_id: str
) -> dict[str, Any]:
    """Fail closed with a redacted error for malformed reports or unreadable chips."""
    try:
        return _validate_optical_report(directory, areas, settings, provider_id)
    except Exception:
        raise ValueError("optical_report_invalid") from None
