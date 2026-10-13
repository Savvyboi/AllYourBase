import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from allyourbase.cli import app

runner = CliRunner()


def test_help_lists_required_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["run", "review", "publish", "backfill", "catalogue"]:
        assert command in result.stdout


def test_catalogue_json(root: Path) -> None:
    result = runner.invoke(app, ["--root", str(root), "catalogue", "check", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["counts"]["sites"] == 0


@pytest.mark.parametrize("command", ["run", "backfill", "review", "publish"])
def test_reserved_commands_fail_honestly(command: str, tmp_path: Path) -> None:
    before = list(tmp_path.iterdir())
    result = runner.invoke(app, ["--root", str(tmp_path), command])
    assert result.exit_code == 2
    assert "not implemented" in result.output
    assert list(tmp_path.iterdir()) == before


def test_plan_does_not_create_workspace(project: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "private-workspace"
    result = runner.invoke(
        app,
        ["--root", str(project), "run", "--plan", "--week", "2020-W53"],
        env={"ALLYOURBASE_HOME": str(workspace)},
    )
    assert result.exit_code == 0, result.output
    plan = json.loads(result.stdout)
    assert plan["mode"] == "planning_only"
    assert plan["analysis_implemented"] is False
    assert plan["site_weeks"][0]["start"] == "2020-12-28T00:00:00+00:00"
    assert not workspace.exists()


def test_backfill_plan_crosses_year_boundary(project: Path) -> None:
    result = runner.invoke(
        app,
        ["--root", str(project), "backfill", "--from", "2020-W53", "--to", "2021-W02", "--plan"],
    )
    assert result.exit_code == 0, result.output
    assert [work["week"] for work in json.loads(result.stdout)["site_weeks"]] == [
        "2020-W53",
        "2021-W01",
        "2021-W02",
    ]


def test_no_unapproved_site_can_be_planned(project: Path) -> None:
    result = runner.invoke(app, ["--root", str(project), "run", "--site", "xxx-unknown", "--plan"])
    assert result.exit_code == 2
    assert "not in the approved catalogue" in result.output


def test_empty_catalogue_refuses_plan(root: Path) -> None:
    result = runner.invoke(app, ["--root", str(root), "run", "--plan"])
    assert result.exit_code == 2
    assert "no approved sites" in result.output


def test_cli_configuration_error_redacts_inputs(root: Path, tmp_path: Path) -> None:
    settings = tmp_path / "bad.yaml"
    settings.write_text((root / "config/settings.yaml").read_text() + "secret: never-print-this\n")
    result = runner.invoke(
        app, ["--root", str(root), "--settings", str(settings), "config", "check"]
    )
    assert result.exit_code == 1
    assert "never-print-this" not in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0, result.output
    assert "0.1.0" in result.stdout
