import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from allyourbase.models.geometry import Polygon
from allyourbase.models.settings import Settings
from allyourbase.providers.contracts import Acquisition, Asset
from allyourbase.providers.pixels import read_optical_windows
from allyourbase.providers.spike import AccessArea, write_json
from allyourbase.providers.validation import validate_optical_report

rasterio = pytest.importorskip("rasterio")


@pytest.fixture
def evidence(tmp_path: Path, settings: Settings) -> tuple[Path, list[AccessArea]]:
    geometry = Polygon.model_validate(
        {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]],
        }
    )
    area = AccessArea("synthetic-area", geometry, {})
    provider = settings.providers.definitions["cdse_stac"]
    assets = []
    for band in settings.preprocessing.optical_bands:
        source = tmp_path / f"source-{band}.tif"
        with rasterio.open(
            source,
            "w",
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="uint16",
            crs="EPSG:4326",
            nodata=0,
            transform=rasterio.transform.from_origin(0, 0.001, 0.0001, 0.0001),
        ) as dst:
            dst.write(np.full((10, 10), 4, dtype="uint16"), 1)
        assets.append(Asset(key=provider.band_assets[band.lower()][0], href=str(source)))
    scene = Acquisition(
        provider="cdse_stac",
        collection=provider.collection,
        scene_id="synthetic-scene",
        sensor="s2",
        acquired_at="2020-12-30T12:00:00Z",
        assets=tuple(assets),
    )
    directory = tmp_path / "evidence"
    files = read_optical_windows(
        scene, geometry, provider, settings, directory / "chips" / area.site_id / "cdse_stac"
    )
    write_json(
        directory / "report.json",
        {
            "run_finished": True,
            "failures": [],
            "providers": ["cdse_stac"],
            "pixel_requests": {"optical": True, "radar": False},
            "areas": [{"site_id": area.site_id, "geometry": geometry.model_dump(mode="json")}],
            "downloads": [
                {"site_id": area.site_id, "provider": "cdse_stac", "status": "ok", "files": files}
            ],
        },
    )
    write_json(
        directory / "acquisitions.json",
        {
            "acquisitions": [{"site_id": area.site_id, **scene.model_dump(mode="json")}],
        },
    )
    return directory, [area]


def test_valid_seven_band_evidence(
    evidence: tuple[Path, list[AccessArea]], settings: Settings
) -> None:
    directory, areas = evidence
    summary = validate_optical_report(directory, areas, settings, "cdse_stac")
    assert summary["status"] == "pass"
    assert summary["file_count"] == 7
    assert {f["band"] for f in summary["files"]} == set(settings.preprocessing.optical_bands)
    assert all(f["valid_pixels"] > 0 and len(f["transform"]) == 6 for f in summary["files"])
    assert json.loads((directory / "optical-validation.json").read_text()) == summary


@pytest.mark.parametrize(
    "damage",
    [
        "missing_band",
        "duplicate_band",
        "hash",
        "scene",
        "source",
        "path",
        "area",
        "incomplete_run",
        "failure",
        "missing_site",
    ],
)
def test_invalid_evidence_is_rejected(
    evidence: tuple[Path, list[AccessArea]], settings: Settings, damage: str
) -> None:
    directory, areas = evidence
    report = json.loads((directory / "report.json").read_text())
    files = report["downloads"][0]["files"]
    if damage == "missing_band":
        files.pop()
    elif damage == "duplicate_band":
        files[-1] = files[0]
    elif damage == "hash":
        files[0]["sha256"] = "0" * 64
    elif damage == "scene":
        files[0]["scene_id"] = "other-scene"
    elif damage == "source":
        files[0]["source"] = "https://example.invalid/other.tif"
    elif damage == "path":
        files[0]["file"] = "../../outside.tif"
    elif damage == "area":
        report["areas"][0]["geometry"]["coordinates"][0][0][0] = 45
    elif damage == "incomplete_run":
        report["run_finished"] = False
    elif damage == "failure":
        report["failures"] = [{"provider": "cdse_stac", "status": "window_read_failed"}]
    else:
        areas = [*areas, AccessArea("missing-area", areas[0].geometry, {})]
    write_json(directory / "report.json", report)
    with pytest.raises(ValueError, match="optical_report_invalid"):
        validate_optical_report(directory, areas, settings, "cdse_stac")
    assert not (directory / "optical-validation.json").exists()


@pytest.mark.parametrize("damage", ["shifted_grid", "empty_pixels", "invalid_scl"])
def test_invalid_pixels_or_georeferencing_with_updated_hash_are_rejected(
    evidence: tuple[Path, list[AccessArea]], settings: Settings, damage: str
) -> None:
    directory, areas = evidence
    report = json.loads((directory / "report.json").read_text())
    record = report["downloads"][0]["files"][-1 if damage == "invalid_scl" else 0]
    chip_path = directory / "chips" / areas[0].site_id / "cdse_stac" / record["file"]
    with rasterio.open(chip_path, "r+") as chip:
        if damage == "shifted_grid":
            chip.transform = rasterio.transform.from_origin(45, 45, 0.0001, 0.0001)
        else:
            chip.write(
                np.full(
                    (chip.height, chip.width), 99 if damage == "invalid_scl" else 0, dtype="uint16"
                ),
                1,
            )
    record["sha256"] = hashlib.sha256(chip_path.read_bytes()).hexdigest()
    write_json(directory / "report.json", report)
    with pytest.raises(ValueError, match="optical_report_invalid"):
        validate_optical_report(directory, areas, settings, "cdse_stac")
