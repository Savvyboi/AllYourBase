"""Explicit snapshot, staging and matching commands for the catalogue workflow."""

import json
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated

import typer

from allyourbase.loading import InputError, load_model
from allyourbase.project import Project
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.matching import MatchSettings
from allyourbase.sources.snapshots import fetch_snapshot, save_snapshot, verify_snapshot
from allyourbase.sources.store import Store

sources_app = typer.Typer(
    no_args_is_help=True, help="Snapshot permitted sources and stage unapproved claims."
)


def guarded[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except InputError as exc:
            typer.echo(f"Catalogue input error: {exc}", err=True)
            raise typer.Exit(1) from None
        except (OSError, ValueError, KeyError, ImportError):
            typer.echo(
                "Source operation failed; check input format, dependencies and file access.",
                err=True,
            )
            raise typer.Exit(1) from None

    return invoke


def project_from_context(ctx: typer.Context) -> Project:
    from allyourbase.cli import _project

    return _project(ctx)


def match_settings(project: Project) -> MatchSettings:
    return load_model(project.root / "config/ingestion.yaml", MatchSettings)


def echo(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


@sources_app.command("snapshot")
@guarded
def snapshot_command(ctx: typer.Context, spec: Path, input_file: Path) -> None:
    """Copy a local permitted source or human-authored facts into an immutable snapshot."""
    project = project_from_context(ctx)
    echo({"manifest": save_snapshot(project.workspace, load_model(spec, SourceSpec), input_file)})


@sources_app.command("fetch")
@guarded
def fetch_command(
    ctx: typer.Context,
    spec: Path,
    query_file: Annotated[Path | None, typer.Option(help="Explicit SPARQL query file.")] = None,
    max_bytes: Annotated[int, typer.Option(min=1)] = 256_000_000,
) -> None:
    """Download import-class data only, with a byte limit; no redirects or credentials."""
    project = project_from_context(ctx)
    query = query_file.read_text(encoding="utf-8") if query_file else None
    echo(
        {
            "manifest": fetch_snapshot(
                project.workspace, load_model(spec, SourceSpec), max_bytes, query
            )
        }
    )


@sources_app.command("stage")
@guarded
def stage_command(ctx: typer.Context, manifest: Path) -> None:
    """Verify a retained snapshot and transactionally stage its unapproved records."""
    project = project_from_context(ctx)
    echo(Store(project.workspace).stage(manifest, match_settings(project)))


@sources_app.command("verify")
@guarded
def verify_command(manifest: Path) -> None:
    snapshot, _ = verify_snapshot(manifest)
    echo({"valid": True, "snapshot_id": snapshot.id, "sha256": snapshot.sha256})


@sources_app.command("match")
@guarded
def match_command(ctx: typer.Context) -> None:
    """Rank site/unit matches and garrison alternatives without selecting them."""
    project = project_from_context(ctx)
    echo({"new_proposals": Store(project.workspace).match(match_settings(project))})


def register_catalogue_commands(app: typer.Typer) -> None:
    @app.command("queue")
    @guarded
    def queue(ctx: typer.Context, state: str = "pending") -> None:
        if state not in {"pending", "accepted", "rejected", "superseded"}:
            raise InputError("unknown queue state")
        echo(Store(project_from_context(ctx).workspace).proposals(state))

    @app.command("show")
    @guarded
    def show(ctx: typer.Context, proposal: str) -> None:
        echo(Store(project_from_context(ctx).workspace).proposal(proposal))

    @app.command("reject")
    @guarded
    def reject(ctx: typer.Context, proposal: str, reviewer: str, note: str = "") -> None:
        Store(project_from_context(ctx).workspace).decide(proposal, "rejected", reviewer, note)
        echo({"proposal_id": proposal, "state": "rejected"})

    @app.command("accept")
    @guarded
    def accept_command(
        ctx: typer.Context,
        proposal: str,
        bundle: Path,
        reviewer: str,
        note: str = "",
        dry_run: bool = False,
    ) -> None:
        from allyourbase.catalogue.review import ReviewBundle, accept

        project = project_from_context(ctx)
        echo(
            accept(
                project, proposal, load_model(bundle, ReviewBundle), reviewer, note, dry_run=dry_run
            )
        )

    @app.command("recover")
    @guarded
    def recover_command(ctx: typer.Context) -> None:
        from allyourbase.catalogue.review import recover

        recover(project_from_context(ctx))
        echo({"recovered": True})

    @app.command("review")
    @guarded
    def review_command(
        ctx: typer.Context, port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765
    ) -> None:
        launch_review(project_from_context(ctx), port)


def launch_review(project: Project, port: int) -> None:
    try:
        import uvicorn

        from allyourbase.review.catalogue_app import create_app
    except ImportError:
        raise InputError(
            "install the ingestion and review extras to launch catalogue review"
        ) from None
    typer.echo(f"Catalogue review: http://127.0.0.1:{port}")
    uvicorn.run(create_app(project), host="127.0.0.1", port=port, log_level="warning")
