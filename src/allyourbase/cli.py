"""The Phase 0 command surface; unimplemented actions fail without side effects."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from allyourbase import ALGO_VERSION, __version__
from allyourbase.catalogue.validation import Catalogue, check_catalogue
from allyourbase.loading import InputError
from allyourbase.project import Project
from allyourbase.schemas import generate_schemas, stale_schemas
from allyourbase.weeks import ISOWeek, week_range

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="AllYourBase · local Sentinel monitoring (Phase 0)",
)
catalogue_app = typer.Typer(no_args_is_help=True, help="Check human-curated catalogue records.")
config_app = typer.Typer(
    no_args_is_help=True, help="Validate settings without accessing providers."
)
schemas_app = typer.Typer(no_args_is_help=True, help="Generate or check catalogue JSON Schemas.")
app.add_typer(catalogue_app, name="catalogue")
app.add_typer(config_app, name="config")
app.add_typer(schemas_app, name="schemas")


@dataclass(frozen=True)
class Options:
    root: Path
    settings_path: Path


@app.callback()
def main(
    ctx: typer.Context,
    root: Annotated[Path, typer.Option(help="Project root directory.")] = Path("."),
    settings: Annotated[
        Path, typer.Option(help="Settings file, relative to root or absolute.")
    ] = Path("config/settings.yaml"),
    version: Annotated[bool, typer.Option("--version", is_eager=True)] = False,
) -> None:
    if version:
        typer.echo(f"AllYourBase {__version__} · algo_version {ALGO_VERSION} (not implemented)")
        raise typer.Exit()
    ctx.obj = Options(root, settings)


def _options(ctx: typer.Context) -> Options:
    options = ctx.obj
    if not isinstance(options, Options):
        raise typer.BadParameter("missing project context")
    return options


def _project(ctx: typer.Context) -> Project:
    options = _options(ctx)
    try:
        return Project.load(options.root, options.settings_path)
    except (InputError, ValueError) as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _catalogue(project: Project) -> Catalogue:
    report = check_catalogue(project.root / "catalogue", project.settings)
    if not report.ok or report.catalogue is None:
        for error in report.errors:
            typer.echo(f"Catalogue error: {error}", err=True)
        raise typer.Exit(1)
    return report.catalogue


@config_app.command("check")
def config_check(ctx: typer.Context) -> None:
    project = _project(ctx)
    typer.echo(f"Settings valid. Runtime: {project.settings.runtime.profile}.")
    typer.echo("Workspace is outside the code repository; no directories were created.")


@catalogue_app.command("check")
def catalogue_check(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Machine-readable report.")] = False,
) -> None:
    project = _project(ctx)
    report = check_catalogue(project.root / "catalogue", project.settings)
    summary = report.summary()
    if json_output:
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"Catalogue {'valid' if report.ok else 'invalid'}: {summary['counts']}")
        for error in report.errors:
            typer.echo(f"Error: {error}", err=True)
        for warning in report.warnings:
            typer.echo(f"Warning: {warning}")
    if not report.ok:
        raise typer.Exit(1)


@schemas_app.command("generate")
def schemas_generate(ctx: typer.Context) -> None:
    directory = _options(ctx).root.expanduser().resolve() / "schemas"
    generate_schemas(directory)
    typer.echo("Generated six configuration and catalogue JSON Schemas.")


@schemas_app.command("check")
def schemas_check(ctx: typer.Context) -> None:
    directory = _options(ctx).root.expanduser().resolve() / "schemas"
    stale = stale_schemas(directory)
    if stale:
        typer.echo(f"Missing or stale schemas: {', '.join(stale)}", err=True)
        raise typer.Exit(1)
    typer.echo("All six JSON Schemas match their models.")


def _week(value: str) -> ISOWeek:
    try:
        return ISOWeek.parse(value)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid ISO week {value}: {exc}") from exc


def _last_completed_week() -> ISOWeek:
    return ISOWeek.containing(datetime.now(UTC).date()).shift(-1)


def _work_plan(project: Project, site: str | None, weeks: list[ISOWeek]) -> None:
    catalogue = _catalogue(project)
    site_ids = sorted(catalogue.sites)
    if site is not None:
        if site not in catalogue.sites:
            raise typer.BadParameter(f"site {site} is not in the approved catalogue")
        site_ids = [site]
    if not site_ids:
        raise typer.BadParameter("no approved sites; add reviewed, cited catalogue records first")
    output = {
        "project": project.settings.project_name,
        "mode": "planning_only",
        "algo_version": ALGO_VERSION,
        "analysis_implemented": False,
        "providers": {
            "optical": project.settings.providers.optical.primary,
            "radar": project.settings.providers.radar.primary,
        },
        "site_weeks": [
            {
                "site_id": site_id,
                "week": str(week),
                "start": week.start.isoformat(),
                "end_exclusive": week.end.isoformat(),
            }
            for site_id in site_ids
            for week in weeks
        ],
    }
    typer.echo(json.dumps(output, ensure_ascii=False, indent=2))


def _unimplemented(action: str, phase: str) -> None:
    typer.echo(f"{action} is not implemented in Phase 0; scheduled for {phase}.", err=True)
    raise typer.Exit(2)


@app.command()
def run(
    ctx: typer.Context,
    site: Annotated[str | None, typer.Option(help="Approved site id; omit for all sites.")] = None,
    week: Annotated[
        str | None, typer.Option(help="YYYY-Www; default last complete UTC week.")
    ] = None,
    plan: Annotated[bool, typer.Option(help="Validate and print work only; no downloads.")] = False,
) -> None:
    """Weekly processing (reserved). Phase 0 supports only --plan."""
    if not plan:
        _unimplemented("Imagery processing", "Phases 1–5")
    _work_plan(_project(ctx), site, [_week(week) if week else _last_completed_week()])


@app.command()
def backfill(
    ctx: typer.Context,
    from_week: Annotated[str | None, typer.Option("--from", help="First ISO week.")] = None,
    to_week: Annotated[str | None, typer.Option("--to", help="Last ISO week, inclusive.")] = None,
    site: Annotated[str | None, typer.Option(help="Approved site id.")] = None,
    plan: Annotated[
        bool, typer.Option(help="Print work without processing or recording state.")
    ] = False,
) -> None:
    """Historical processing (reserved). Phase 0 supports only --plan."""
    if not plan:
        _unimplemented("Backfill", "Phase 4")
    project = _project(ctx)
    start = _week(from_week or project.settings.schedule.default_start_week)
    end = _week(to_week) if to_week else _last_completed_week()
    try:
        weeks = week_range(start, end)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _work_plan(project, site, weeks)


@app.command()
def review() -> None:
    """Local review UI (reserved for Phases 2 and 5; no server launched)."""
    _unimplemented("Local review app", "Phases 2 and 5")


@app.command()
def publish() -> None:
    """Export and publish (reserved for Phase 7; no remote writes)."""
    _unimplemented("Publishing", "Phase 7")


@app.command()
def status() -> None:
    """Show implementation status; no configuration or credentials are read."""
    typer.echo("Phase 0: settings, catalogue validation, JSON Schemas and work planning.")
    typer.echo("Live imagery, scoring, review, website and publishing are not implemented.")
