"""Lightweight CLI registration; numerical extras are loaded only on execution."""

from datetime import date
from pathlib import Path
from typing import Annotated

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
def build_command(
    ctx: typer.Context, history: Path, output: Path, sites: Path = Path("sites.yaml")
) -> None:
    """Build the complete static site from retained small JSON/PNG history."""
    from allyourbase.cli import _options
    from allyourbase.monitor.report import build_site

    root = _options(ctx).root.expanduser().resolve()
    history = (history if history.is_absolute() else root / history).expanduser().resolve()
    output = (output if output.is_absolute() else root / output).expanduser().resolve()
    if output.is_relative_to(root):
        raise InputError("generated site must stay outside the code repository")
    locations = load_model((sites if sites.is_absolute() else root / sites).resolve(), Locations)
    echo(build_site(history, output, locations))


def _sites_path(ctx: typer.Context, sites: Path) -> Path:
    from allyourbase.cli import _options

    root = _options(ctx).root.expanduser().resolve()
    return (sites if sites.is_absolute() else root / sites).expanduser().resolve()


@monitor_app.command("sites")
@guarded
def list_sites(
    ctx: typer.Context, sites: Path = Path("sites.yaml"), category: str | None = None
) -> None:
    """List monitor sites grouped by category; optionally select one category."""
    from allyourbase.monitor.sites import SiteStore

    snapshot = SiteStore(_sites_path(ctx, sites)).snapshot()
    selected = [s for s in snapshot["sites"] if category is None or s["category"] == category]
    echo(
        {
            "categories": {
                label: [s for s in selected if s["category"] == label]
                for label in snapshot["categories"]
                if any(s["category"] == label for s in selected)
            }
        }
    )


@monitor_app.command("categorize")
@guarded
def categorize_sites(
    ctx: typer.Context,
    identifiers: Annotated[list[str], typer.Argument()],
    category: Annotated[
        str, typer.Option(help="Existing or new category; blank means Uncategorized.")
    ],
    sites: Path = Path("sites.yaml"),
) -> None:
    """Assign a category to existing site IDs without changing their grids."""
    from allyourbase.monitor.sites import SiteStore

    store = SiteStore(_sites_path(ctx, sites))
    echo(store.categorize(dict.fromkeys(identifiers, category), store.snapshot()["revision"]))


@monitor_app.command("review")
@guarded
def review_sites(
    ctx: typer.Context,
    sites: Path = Path("sites.yaml"),
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8766,
) -> None:
    """Open the local monitor site/category editor."""
    import uvicorn

    from allyourbase.review.monitor_app import create_app

    path = _sites_path(ctx, sites)
    load_model(path, Locations)
    typer.echo(f"Monitor sites: http://127.0.0.1:{port}")
    uvicorn.run(create_app(path), host="127.0.0.1", port=port, log_level="warning")
