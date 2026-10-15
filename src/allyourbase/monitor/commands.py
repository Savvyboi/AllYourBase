"""Lightweight CLI registration; numerical extras are loaded only on execution."""

from datetime import date
from pathlib import Path

import typer

from allyourbase.loading import InputError, load_model
from allyourbase.monitor.config import Location, Locations, MonitorConfig, make_grid, windows
from allyourbase.sources.commands import echo, guarded

monitor_app = typer.Typer(
    no_args_is_help=True, help="Monitor possible ground change in coordinate-defined 1 km squares."
)


@monitor_app.command("run")
@guarded
def run_command(
    ctx: typer.Context,
    sites: Path = Path("sites.yaml"),
    config: Path = Path("config/monitor.yaml"),
    workspace: Path = Path("../monitor-data"),
    history: Path = Path("../monitor-results"),
    output: Path = Path("../monitor-site"),
    end_date: str | None = None,
    live: bool = False,
    demo: bool = False,
    plan: bool = False,
) -> None:
    """Use --plan, --demo or explicit --live; end date is exclusive UTC midnight."""
    from allyourbase.cli import _options
    from allyourbase.monitor.main import run_monitor

    root = _options(ctx).root.expanduser().resolve()

    def resolve(path: Path) -> Path:
        return (path if path.is_absolute() else root / path).expanduser().resolve()

    settings = load_model(resolve(config), MonitorConfig)
    locations = load_model(resolve(sites), Locations)
    end = date.fromisoformat(end_date) if end_date else None
    if sum((live, demo, plan)) != 1:
        raise InputError("choose exactly one of --plan, --demo or --live")
    if plan:
        baseline, start, finish = windows(end)
        echo(
            {
                "windows": {
                    "baseline_start": baseline.isoformat(),
                    "target_start": start.isoformat(),
                    "end_exclusive": finish.isoformat(),
                },
                "locations": [
                    {
                        "location": s.model_dump(mode="json"),
                        "grid": make_grid(s).model_dump(mode="json"),
                    }
                    for s in locations.sites
                ],
                "max_requests": settings.max_requests,
                "analysis_version": settings.analysis_version(),
            }
        )
        return
    paths = [resolve(workspace), resolve(history), resolve(output)]
    if any(p.is_relative_to(root) for p in paths):
        raise InputError("cache, history and generated site must stay outside the code repository")
    if any(
        a == b or a in b.parents or b in a.parents
        for i, a in enumerate(paths)
        for b in paths[i + 1 :]
    ):
        raise InputError("cache, history and site output must use separate directories")
    if demo:
        locations = Locations(
            sites=[
                Location(
                    id="synthetic-change", name="Synthetic changed example", latitude=0, longitude=0
                ),
                Location(
                    id="synthetic-quiet", name="Synthetic quiet example", latitude=0, longitude=0
                ),
            ]
        )
    echo(run_monitor(settings, locations, paths[0], paths[1], paths[2], end, live=live))


@monitor_app.command("build")
@guarded
def build_command(ctx: typer.Context, history: Path, output: Path) -> None:
    """Build the complete static site from retained small JSON/PNG history."""
    from allyourbase.cli import _options
    from allyourbase.monitor.report import build_site

    root = _options(ctx).root.expanduser().resolve()
    history = (history if history.is_absolute() else root / history).expanduser().resolve()
    output = (output if output.is_absolute() else root / output).expanduser().resolve()
    if output.is_relative_to(root):
        raise InputError("generated site must stay outside the code repository")
    echo(build_site(history, output))
