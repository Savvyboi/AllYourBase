import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from allyourbase.cli import app
from allyourbase.monitor.config import Location, Locations, MonitorConfig
from allyourbase.monitor.fetch import Cutout
from allyourbase.monitor.main import SyntheticImagery, check_location, run_monitor
from allyourbase.monitor.report import build_site
from allyourbase.providers.contracts import Acquisition, ProviderError
from allyourbase.providers.http import RequestObservation


def location(identifier: str = "synthetic-change") -> Location:
    return Location(
        id=identifier, name="Fictional <script>alert(1)</script>", latitude=0, longitude=0
    )


def test_optical_report_history_is_idempotent(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    history = tmp_path / "history"
    source = SyntheticImagery(date(2020, 10, 12), True)
    first = check_location(location(), monitor_config, source, history, date(2020, 10, 12))
    assert first["status"] == "possible_change" and first["usable_sensors"] == ["s2"]
    reports = list((history / "detections").glob("*.json"))
    assert len(reports) == 1
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["changed_area_m2"] == 50000
        assert set(report["supported_by_sensors"]) == {"s2"}
        assert report["baseline_preview"].startswith("pixelwise median composite")
        assert "assets" not in report["current"] and report["patches"]
    again = check_location(location(), monitor_config, source, history, date(2020, 10, 12))
    assert again["detection_ids"] == first["detection_ids"]
    assert len(list((history / "detections").glob("*.json"))) == 1
    output = tmp_path / "site"
    assert build_site(history, output) == {"locations": 1, "detections": 1}
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and "median composite" in html
    assert not list(output.rglob("*.tif"))
    (output / "private.env").write_text("fixture-secret", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected files"):
        build_site(history, output)


def test_failed_sensor_preserves_prior_detections_and_error_status(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    history = tmp_path / "history"
    check_location(
        location(),
        monitor_config,
        SyntheticImagery(date(2020, 10, 12), True),
        history,
        date(2020, 10, 12),
    )

    class Failed(SyntheticImagery):
        def discover(self, *args: Any, **kwargs: Any) -> list[Acquisition]:
            raise ProviderError("fixture_outage", "test")

    check = check_location(
        location(), monitor_config, Failed(date(2020, 10, 19), True), history, date(2020, 10, 19)
    )
    assert check["status"] == "error" and not check["detection_ids"]
    assert len(list((history / "detections").glob("*.json"))) == 1
    output = tmp_path / "site"
    build_site(history, output)
    html = (output / "locations/synthetic-change.html").read_text(encoding="utf-8")
    assert "fixture_outage" in html and "Detection history" in html


def test_cloudy_and_quiet_runs_do_not_create_news(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    class Cloudy(SyntheticImagery):
        def cutout(self, scene: Acquisition, grid: Any) -> Cutout:
            result = super().cutout(scene, grid)
            result.pixels[5] = 0
            return result

    for identifier, source, status in [
        ("quiet", SyntheticImagery(date(2020, 10, 12), False), "no_change_detected"),
        ("cloudy", Cloudy(date(2020, 10, 12), True), "insufficient_data"),
    ]:
        check = check_location(
            location(identifier), monitor_config, source, tmp_path / "history", date(2020, 10, 12)
        )
        assert check["status"] == status and check["detection_ids"] == []
    assert not list((tmp_path / "history/detections").glob("*.json"))


def test_duplicate_tile_products_never_supply_two_baseline_observations(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    class DuplicateTiles(SyntheticImagery):
        def discover(self, grid: Any, sensor: str, start: Any, end: Any) -> list[Acquisition]:
            original = super().discover(grid, sensor, start, end)
            baseline = original[0]
            duplicate = baseline.model_copy(
                update={
                    "scene_id": baseline.scene_id + "-other-tile",
                    "acquired_at": baseline.acquired_at + timedelta(seconds=12),
                }
            )
            return [baseline, duplicate, original[-1]]

    check = check_location(
        location(),
        monitor_config,
        DuplicateTiles(date(2020, 10, 12), True),
        tmp_path / "history",
        date(2020, 10, 12),
    )
    assert check["status"] == "insufficient_data"
    assert all(
        s["skipped"][0]["reason"] == "same_acquisition_alternative_product"
        for s in check["sensors"]
    )


def test_relocated_id_does_not_stop_other_locations_or_hide_error(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    locations = Locations(sites=[location("synthetic-change"), location("synthetic-quiet")])
    paths = [tmp_path / "data", tmp_path / "history", tmp_path / "site"]
    first = run_monitor(
        monitor_config, locations, paths[0], paths[1], paths[2], date(2020, 10, 12), live=False
    )
    assert first["site"]["detections"] == 1
    locations.sites[0] = locations.sites[0].model_copy(update={"longitude": 10})
    again = run_monitor(
        monitor_config, locations, paths[0], paths[1], paths[2], date(2020, 10, 19), live=False
    )
    assert again["statuses"] == {
        "synthetic-change": "error",
        "synthetic-quiet": "no_change_detected",
    }
    assert again["site"]["detections"] == 1
    html = (paths[2] / "locations/synthetic-change.html").read_text(encoding="utf-8")
    assert "location_configuration_or_processing_error" in html


def test_cli_plan_requires_no_credentials_or_state_and_workflow_contract(
    root: Path, tmp_path: Path
) -> None:
    result = CliRunner().invoke(
        app, ["--root", str(root), "monitor", "run", "--plan", "--end-date", "2026-10-15"]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.stdout)
    assert parsed["windows"]["target_start"] == "2026-10-08T00:00:00+00:00"
    assert parsed["locations"][0]["grid"]["width"] == 100
    blocked = CliRunner().invoke(
        app,
        [
            "--root",
            str(root),
            "monitor",
            "build",
            str(tmp_path / "history"),
            str(root / "untracked-generated-site"),
        ],
    )
    assert blocked.exit_code == 1 and "outside the code" in blocked.output
    assert not (root / "untracked-generated-site").exists()

    workflow = yaml.load(
        (root / ".github/workflows/monitor.yml").read_text(encoding="utf-8-sig"),
        Loader=yaml.BaseLoader,
    )
    assert workflow["on"]["schedule"][0]["cron"] == "23 6 * * 1"
    assert workflow["on"]["workflow_dispatch"]["inputs"]["rebuild_only"]["default"] == "false"
    steps = {step.get("name"): step for step in workflow["jobs"]["analyse"]["steps"]}
    assert steps["Analyse latest seven complete UTC days"]["if"] == "${{ !inputs.rebuild_only }}"
    assert steps["Rebuild viewer from retained history"]["if"] == "${{ inputs.rebuild_only }}"
    assert "--live" not in steps["Rebuild viewer from retained history"]["run"]

    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["jobs"]["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}
    assert workflow["jobs"]["deploy"]["needs"] == "analyse"
    assert (
        sum(s.get("uses") == "actions/deploy-pages@v4" for s in workflow["jobs"]["deploy"]["steps"])
        == 3
    )


def test_fresh_git_runners_restore_history_without_duplicate_reports(
    tmp_path: Path, monitor_config: MonitorConfig
) -> None:
    import subprocess

    def git(directory: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(directory), *args], check=True, capture_output=True, text=True
        )

    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    first = tmp_path / "first-runner"
    first.mkdir()
    git(first, "init", "--initial-branch=main")
    git(first, "config", "user.name", "Fictional test")
    git(first, "config", "user.email", "fixture@example.invalid")
    (first / "README.md").write_text("Code checkout fixture\n", encoding="utf-8")
    git(first, "add", "README.md")
    git(first, "commit", "-m", "Code fixture")
    git(first, "remote", "add", "origin", str(remote))
    git(first, "push", "origin", "main")
    history = tmp_path / "first-history"
    git(first, "worktree", "add", "--detach", str(history), "HEAD")
    git(history, "switch", "--orphan", "monitor-results")
    assert not (history / "README.md").exists()
    check = check_location(
        location(),
        monitor_config,
        SyntheticImagery(date(2020, 10, 12), True),
        history,
        date(2020, 10, 12),
    )
    git(history, "add", "--all")
    git(history, "commit", "-m", "Fixture report history")
    git(history, "push", "origin", "HEAD:refs/heads/monitor-results")
    second = tmp_path / "second-runner"
    subprocess.run(["git", "clone", str(remote), str(second)], check=True, capture_output=True)
    restored = tmp_path / "restored-history"
    git(second, "fetch", "origin", "monitor-results")
    git(second, "worktree", "add", "--detach", str(restored), "FETCH_HEAD")
    repeated = check_location(
        location(),
        monitor_config,
        SyntheticImagery(date(2020, 10, 12), True),
        restored,
        date(2020, 10, 12),
    )
    assert repeated["detection_ids"] == check["detection_ids"]
    assert len(list((restored / "detections").glob("*.json"))) == 1
    assert not list(restored.rglob("*.tif"))
    assert build_site(restored, tmp_path / "fresh-site")["detections"] == 1


def test_run_summary_retains_measured_and_unknown_usage_without_request_payloads(
    tmp_path: Path, monitor_config: MonitorConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    class MeteredImagery(SyntheticImagery):
        def __init__(self, *args: Any) -> None:
            super().__init__(date(2020, 10, 12), False)
            self.transport = SimpleNamespace(
                remaining=monitor_config.max_requests - 4,
                observations=[
                    RequestObservation("cdse", "token", 200, 0.1, None),
                    RequestObservation("cdse", "catalogue", 200, 0.2, 0.04),
                    RequestObservation("cdse", "process", 200, 0.3, 1.25),
                    RequestObservation("cdse", "process", None, 0.4, None),
                ],
            )

    monkeypatch.setattr("allyourbase.monitor.main.Fetcher", MeteredImagery)
    workspace = tmp_path / "data"
    result = run_monitor(
        monitor_config,
        Locations(sites=[location("quiet")]),
        workspace,
        tmp_path / "history",
        tmp_path / "site",
        date(2020, 10, 12),
        live=True,
    )
    journal = json.loads(next((workspace / "runs").glob("*.json")).read_text())
    assert result["requests_used"] == 4
    assert result["request_cap"] == monitor_config.max_requests
    assert result["reported_processing_units"] == pytest.approx(1.29)
    assert result["unknown_process_charges"] == 1
    for key in (
        "requests_used",
        "request_cap",
        "reported_processing_units",
        "unknown_process_charges",
    ):
        assert result[key] == journal[key]
    assert "observations" not in result
    assert not any(k in json.dumps(result) for k in ("access_token", "client_secret", "headers"))
