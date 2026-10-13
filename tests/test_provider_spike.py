import csv
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from allyourbase.cli import app
from allyourbase.loading import load_model
from allyourbase.models.catalogue import SitesFile
from allyourbase.models.settings import Settings
from allyourbase.providers.proposals import ProbeAOIs
from allyourbase.providers.spike import AccessArea, access_spike
from allyourbase.weeks import ISOWeek

runner = CliRunner()


def area(catalogue: Path) -> AccessArea:
    feature = load_model(catalogue / "countries/XXX/sites.geojson", SitesFile).features[0]
    return AccessArea(
        feature.properties.id, feature.geometry, {"sources": feature.properties.sources}
    )


def test_eight_week_report_includes_gaps_and_redacts_signatures(
    catalogue: Path, settings: Settings, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "id": "synthetic-optical-scene",
                        "properties": {"datetime": "2021-01-06T12:00:00Z", "eo:cloud_cover": 95},
                        "assets": {
                            "blue": {
                                "href": "https://example.invalid/blue.tif?signature=private-value"
                            }
                        },
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        output = access_spike(
            [area(catalogue)],
            settings,
            tmp_path / "workspace",
            ISOWeek.parse("2021-W02"),
            8,
            ["earth_search"],
            client=client,
        )
    with (output / "acquisitions-by-week.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    assert sum(int(row["looks"]) for row in rows) == 1
    assert sum(int(row["eligible_optical_looks"]) for row in rows) == 0
    assert {row["status"] for row in rows} == {"ok", "no_acquisitions"}
    assert "private-value" not in (output / "acquisitions.json").read_text()
    report = json.loads((output / "report.json").read_text())
    assert report["analysis_implemented"] is False
    assert report["provider_selection"] == "not_decided"
    assert not (output / "chips").exists()


def test_missing_credentials_recorded_for_every_week(
    catalogue: Path, settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("allyourbase.providers.auth.load_credentials", lambda *args: None)

    def no_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be called without credentials")

    with httpx.Client(transport=httpx.MockTransport(no_request)) as client:
        output = access_spike(
            [area(catalogue)],
            settings,
            tmp_path / "workspace",
            ISOWeek.parse("2021-W02"),
            8,
            ["cdse_sentinelhub"],
            client=client,
        )
    with (output / "acquisitions-by-week.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert {row["status"] for row in rows} == {"credentials_missing"}
    assert all(row["looks"] == "0" for row in rows)
    assert json.loads((output / "usage.json").read_text())["request_count"] == 0


def test_provider_failure_does_not_erase_other_provider_results(
    catalogue: Path, settings: Settings, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404)
            if "copernicus" in request.url.host
            else httpx.Response(200, json={"features": []})
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        output = access_spike(
            [area(catalogue)],
            settings,
            tmp_path / "workspace",
            ISOWeek.parse("2021-W02"),
            1,
            ["earth_search", "cdse_stac"],
            client=client,
        )
    with (output / "acquisitions-by-week.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert [row["status"] for row in rows] == ["no_acquisitions", "http_404"]


def test_duplicate_areas_refused_before_workspace_write(
    catalogue: Path, settings: Settings, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    with pytest.raises(ValueError, match="duplicate"):
        access_spike(
            [area(catalogue), area(catalogue)],
            settings,
            workspace,
            ISOWeek.parse("2021-W02"),
            1,
            ["earth_search"],
        )
    assert not workspace.exists()


def test_proposed_areas_require_human_approval(root: Path, tmp_path: Path) -> None:
    path = root / "docs/proposals/phase-1-aois.geojson"
    proposals = load_model(path, ProbeAOIs)
    assert len(proposals.features) == 3
    for feature in proposals.features:
        feature.properties.approved = False
    path = tmp_path / "unapproved-aois.geojson"
    path.write_text(proposals.model_dump_json(), encoding="utf-8")
    workspace = tmp_path / "workspace"
    result = runner.invoke(
        app,
        ["--root", str(root), "providers", "spike", "--aoi-file", str(path)],
        env={"ALLYOURBASE_HOME": str(workspace)},
    )
    assert result.exit_code == 2
    assert "human review" in result.output
    assert not workspace.exists()


def test_proposal_plan_has_no_side_effects(root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    result = runner.invoke(
        app,
        [
            "--root",
            str(root),
            "providers",
            "spike",
            "--aoi-file",
            "docs/proposals/phase-1-aois.geojson",
            "--plan",
        ],
        env={"ALLYOURBASE_HOME": str(workspace)},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["mode"] == "planning_only"
    assert len(json.loads(result.stdout)["areas"]) == 3
    assert not workspace.exists()


def test_doctor_never_prints_credentials(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from allyourbase.providers.auth import Credentials

    monkeypatch.setattr(
        "allyourbase.providers.commands.load_credentials",
        lambda *args: Credentials("private-client", "private-secret"),
    )
    result = runner.invoke(app, ["--root", str(root), "providers", "doctor"])
    assert result.exit_code == 0
    assert "private-client" not in result.stdout
    assert "private-secret" not in result.stdout
    assert any(row["credentials"] == "configured" for row in json.loads(result.stdout))


def test_safe_area_id_required(catalogue: Path) -> None:
    with pytest.raises(ValueError, match="safe lowercase slug"):
        AccessArea("../../elsewhere", area(catalogue).geometry, {})


def test_requested_pixels_with_no_acquisitions_are_an_explicit_failure(
    catalogue: Path, settings: Settings, tmp_path: Path
) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"features": []}))
    ) as client:
        output = access_spike(
            [area(catalogue)],
            settings,
            tmp_path / "workspace",
            ISOWeek.parse("2021-W02"),
            1,
            ["earth_search"],
            optical_pixels=True,
            client=client,
        )
    report = json.loads((output / "report.json").read_text())
    assert report["failures"][0]["status"] == "no_eligible_acquisitions"


@pytest.mark.parametrize("configured", [False, True])
def test_doctor_reports_s3_pixel_readiness_without_values(
    root: Path, monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    for name in ("CDSE_S3_ACCESS_KEY_ID", "CDSE_S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
        if configured:
            monkeypatch.setenv(name, "synthetic-private-value")
    result = runner.invoke(app, ["--root", str(root), "providers", "doctor"])
    assert result.exit_code == 0
    row = next(row for row in json.loads(result.stdout) if row["provider"] == "cdse_stac")
    assert row["credentials"] == "not_required"
    assert row["pixel_credentials"] == ("configured" if configured else "missing")
    assert "synthetic-private-value" not in result.stdout
