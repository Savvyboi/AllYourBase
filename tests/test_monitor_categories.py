import json
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from allyourbase.cli import app
from allyourbase.loading import InputError
from allyourbase.monitor.config import Grid, Location, Locations, MonitorConfig, freeze_grid
from allyourbase.monitor.main import SyntheticImagery, check_location
from allyourbase.monitor.report import build_site, write_json
from allyourbase.monitor.sites import SitesChanged, SiteStore
from allyourbase.providers.contracts import Acquisition
from allyourbase.review.monitor_app import create_app


def sites_file(path: Path) -> Path:
    path.write_text(
        "# retained coordinate provenance\n"
        "sites:\n- id: first\n  name: First\n  latitude: 0\n  longitude: 0 # keep this\n"
        "- id: second\n  name: Second\n  latitude: 1\n  longitude: 1\n"
        "  category: Research # keep category note\n",
        encoding="utf-8",
    )
    return path


def test_category_edits_preserve_yaml_coordinates_and_frozen_grid(tmp_path: Path) -> None:
    path = sites_file(tmp_path / "sites.yaml")
    store = SiteStore(path)
    before = store.snapshot()
    grid_path = tmp_path / "grid.json"
    grid = freeze_grid(Location.model_validate(before["sites"][0]), grid_path)
    after = store.categorize({"first": " Airfields ", "second": "Airfields"}, before["revision"])
    assert after["categories"] == ["Airfields"]
    assert "# retained coordinate provenance" in path.read_text()
    assert "longitude: 0 # keep this" in path.read_text()
    assert "# keep category note" in path.read_text()
    assert freeze_grid(Location.model_validate(after["sites"][0]), grid_path) == grid
    with pytest.raises(SitesChanged):
        store.categorize({"first": "Other"}, before["revision"])
    saved = path.read_bytes()
    with pytest.raises(InputError):
        store.categorize({"absent": "Other"}, after["revision"])
    assert path.read_bytes() == saved


def test_flow_yaml_unicode_and_category_validation(tmp_path: Path) -> None:
    path = tmp_path / "sites.yaml"
    path.write_text("sites: [{id: first, name: First, latitude: 0, longitude: 0}] # keep\n")
    store = SiteStore(path)
    result = store.categorize({"first": "Tutkimus & testit"}, store.snapshot()["revision"])
    assert result["sites"][0]["category"] == "Tutkimus & testit"
    assert path.read_text().endswith("# keep\n")
    result = store.categorize({"first": "  "}, result["revision"])
    assert result["categories"] == ["Uncategorized"]
    saved = path.read_bytes()
    with pytest.raises(ValidationError):
        store.categorize({"first": "x" * 81}, result["revision"])
    assert path.read_bytes() == saved


def test_local_category_api_enforces_session_origin_validation_and_revision(tmp_path: Path) -> None:
    path = sites_file(tmp_path / "sites.yaml")
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/monitor/sites").status_code == 403
        token = client.get("/").text.split("const token='")[1].split("'")[0]
        headers = {"X-Review-Token": token}
        before = client.get("/api/monitor/sites", headers=headers).json()
        body = {"revision": before["revision"], "assignments": {"first": "Airfields"}}
        assert (
            client.post(
                "/api/monitor/categories",
                json=body,
                headers=headers | {"Origin": "https://example.invalid"},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/monitor/sites", headers=headers | {"Host": "example.invalid"}
            ).status_code
            == 403
        )
        assert client.post("/api/monitor/categories", json=body, headers=headers).status_code == 200
        assert client.post("/api/monitor/categories", json=body, headers=headers).status_code == 409
        body["assignments"] = {"first": "x" * 81}
        body["revision"] = client.get("/api/monitor/sites", headers=headers).json()["revision"]
        assert client.post("/api/monitor/categories", json=body, headers=headers).status_code == 400


def test_category_cli_updates_and_lists_groups(tmp_path: Path) -> None:
    path = sites_file(tmp_path / "sites.yaml")
    runner = CliRunner()
    result = runner.invoke(
        app, ["monitor", "categorize", "first", "--category", "Airfields", "--sites", str(path)]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app, ["monitor", "sites", "--sites", str(path), "--category", "Airfields"]
    )
    assert result.exit_code == 0, result.output
    assert list(json.loads(result.stdout)["categories"]) == ["Airfields"]


def test_current_categories_apply_to_old_history_without_reanalysis(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    history, output = tmp_path / "history", tmp_path / "site"
    loc = Location(id="first", name="First", latitude=0, longitude=0)
    check_location(
        loc, monitor_config, SyntheticImagery(date(2020, 10, 12), True), history, date(2020, 10, 12)
    )
    before = {p: p.read_bytes() for p in history.rglob("*") if p.is_file()}
    category = 'Research "><script>alert(1)</script>'
    build_site(history, output, Locations(sites=[loc.model_copy(update={"category": category})]))
    html = (output / "index.html").read_text()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    reports = json.loads((output / "reports.json").read_text())
    assert reports["checks"][0]["location"]["category"] == category
    assert reports["detections"][0]["location"]["category"] == category
    assert before == {p: p.read_bytes() for p in before}


def test_old_radar_is_archived_but_excluded_from_viewer_and_status(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    history, output = tmp_path / "history", tmp_path / "site"
    loc = Location(id="first", name="First", latitude=0, longitude=0)
    check = check_location(
        loc, monitor_config, SyntheticImagery(date(2020, 10, 12), True), history, date(2020, 10, 12)
    )
    original = next((history / "detections").glob("*.json"))
    radar = json.loads(original.read_text())
    old_id = radar["id"]
    radar["id"] = "0" * 24
    radar["sensor"] = "s1"
    radar["current"]["sensor"] = "s1"
    for kind in radar["previews"]:
        old = radar["previews"][kind]
        radar["previews"][kind] = old.replace(old_id, radar["id"])
        (history / radar["previews"][kind]).write_bytes((history / old).read_bytes())
    original.unlink()
    radar_path = history / "detections" / (radar["id"] + ".json")
    write_json(radar_path, radar)
    check["detection_ids"] = [radar["id"]]
    check["usable_sensors"] = ["s2", "s1"]
    check["sensors"][0]["comparisons"][0]["status"] = "no_change_detected"
    check["sensors"][0]["comparisons"][0]["changed_area_m2"] = 0
    check["sensors"].append({"sensor": "s1", "status": "usable", "comparisons": []})
    check_path = next((history / "checks").glob("*/*.json"))
    write_json(check_path, check)
    saved = radar_path.read_bytes()
    # Simulate an existing generated output containing known old radar previews.
    for name in radar["previews"].values():
        (output / name).parent.mkdir(parents=True, exist_ok=True)
        (output / name).write_bytes((history / name).read_bytes())
    assert build_site(history, output) == {"locations": 1, "detections": 0}
    published = json.loads((output / "reports.json").read_text())
    assert published["checks"][0]["status"] == "no_change_detected"
    assert published["checks"][0]["usable_sensors"] == ["s2"]
    assert not published["detections"] and not list((output / "previews").glob("*.png"))
    assert radar_path.read_bytes() == saved
    assert all((history / name).exists() for name in radar["previews"].values())


def test_monitor_never_discovers_radar(monitor_config: MonitorConfig, tmp_path: Path) -> None:
    class OnlyOptical(SyntheticImagery):
        def discover(
            self, grid: Grid, sensor: str, start: datetime, end: datetime
        ) -> list[Acquisition]:
            assert sensor == "s2"
            return super().discover(grid, sensor, start, end)

    loc = Location(id="first", name="First", latitude=0, longitude=0)
    check = check_location(
        loc, monitor_config, OnlyOptical(date(2020, 10, 12), False), tmp_path, date(2020, 10, 12)
    )
    assert check["usable_sensors"] == ["s2"] and not check["errors"]
