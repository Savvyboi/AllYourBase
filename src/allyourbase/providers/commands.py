"""Provider diagnostics and access-spike commands; nothing is scored or published."""

import json
import os
from pathlib import Path
from typing import Annotated

import httpx
import typer

from allyourbase.loading import load_model
from allyourbase.project import Project
from allyourbase.providers.auth import TokenProvider, load_credentials
from allyourbase.providers.contracts import ProviderError
from allyourbase.providers.http import Transport
from allyourbase.providers.proposals import ProbeAOIs
from allyourbase.providers.spike import AccessArea, access_spike

providers_app = typer.Typer(no_args_is_help=True, help="Check providers and measure data access.")


def _project_from_context(ctx: typer.Context) -> Project:
    # Shared CLI options are attached by the application's root callback.
    from allyourbase.cli import _project

    return _project(ctx)


@providers_app.command()
def doctor(
    ctx: typer.Context,
    online: Annotated[
        bool, typer.Option(help="Check collections and OAuth online; no pixel request.")
    ] = False,
) -> None:
    """Show connection readiness without displaying any credential value."""
    project = _project_from_context(ctx)
    rows = []
    with httpx.Client() as client:
        transport = Transport(
            client, project.settings.access, project.settings.schedule.retry_attempts
        )
        for identifier, provider in project.settings.providers.definitions.items():
            credential_state = "not_required"
            if provider.kind == "sentinelhub":
                credential_state = (
                    "configured"
                    if load_credentials(provider, project.settings.access.keyring_service)
                    else "missing"
                )
            row = {
                "provider": identifier,
                "enabled": provider.enabled,
                "sensor": provider.sensor,
                "credentials": credential_state,
                "pixel_credentials": (
                    "configured"
                    if all(
                        os.environ.get(name or "")
                        for name in (provider.s3_access_key_env, provider.s3_secret_key_env)
                    )
                    else "missing"
                )
                if provider.s3_endpoint
                else credential_state,
                "status": "not_checked",
            }
            if online:
                try:
                    headers = (
                        TokenProvider(identifier, provider, transport).headers()
                        if provider.kind == "sentinelhub"
                        else None
                    )
                    collection = transport.json(
                        "GET",
                        str(provider.catalogue_url).rstrip("/")
                        + "/collections/"
                        + provider.collection,
                        provider=identifier,
                        operation="collection_check",
                        headers=headers,
                    )
                    row["status"] = (
                        "reachable"
                        if collection.get("id") == provider.collection
                        else "collection_id_mismatch"
                    )
                except ProviderError as exc:
                    row["status"] = exc.code
            rows.append(row)
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))


def _areas(project: Project, aoi_file: Path | None, planning: bool) -> list[AccessArea]:
    if aoi_file is not None:
        path = aoi_file if aoi_file.is_absolute() else project.root / aoi_file
        proposals = load_model(path, ProbeAOIs)
        if not planning and any(not feature.properties.approved for feature in proposals.features):
            raise typer.BadParameter(
                "test AOIs need human review; set approved to true only after "
                "reviewing their sources and geometry"
            )
        return [
            AccessArea(
                feature.properties.id, feature.geometry, feature.properties.model_dump(mode="json")
            )
            for feature in proposals.features
        ]
    from allyourbase.cli import _catalogue

    catalogue = _catalogue(project)
    return [
        AccessArea(
            site.properties.id, site.geometry, {"catalogue_sources": site.properties.sources}
        )
        for site in catalogue.sites.values()
    ]


@providers_app.command()
def spike(
    ctx: typer.Context,
    aoi_file: Annotated[
        Path | None, typer.Option(help="Source-backed test AOIs, separate from the catalogue.")
    ] = None,
    site: Annotated[str | None, typer.Option(help="Restrict to one approved area id.")] = None,
    provider: Annotated[
        list[str] | None,
        typer.Option(help="Repeat to select providers; default enabled providers."),
    ] = None,
    weeks: Annotated[
        int | None, typer.Option(min=1, help="Complete ISO weeks; default from settings.")
    ] = None,
    end_week: Annotated[
        str | None, typer.Option(help="Last ISO week, inclusive; default last complete week.")
    ] = None,
    pixels: Annotated[
        bool, typer.Option(help="Read one eligible optical acquisition per area/provider.")
    ] = False,
    radar: Annotated[
        bool, typer.Option(help="Request one radar chip per area; requires CDSE OAuth.")
    ] = False,
    plan: Annotated[
        bool, typer.Option(help="Inspect areas and request choices without network or file writes.")
    ] = False,
) -> None:
    """Generate acquisition, usage and chip reports in the external local workspace."""
    from allyourbase.cli import _last_completed_week, _week

    project = _project_from_context(ctx)
    try:
        areas = _areas(project, aoi_file, plan)
        if site is not None:
            areas = [area for area in areas if area.site_id == site]
        if not areas:
            raise typer.BadParameter("no test areas selected")
        ids = provider or [
            identifier
            for identifier, definition in project.settings.providers.definitions.items()
            if definition.enabled
        ]
        if len(set(ids)) != len(ids):
            raise typer.BadParameter("provider ids must be distinct")
        for identifier in ids:
            if identifier not in project.settings.providers.definitions:
                raise typer.BadParameter(f"unknown provider {identifier}")
        end = _week(end_week) if end_week else _last_completed_week()
        count = weeks or project.settings.access.lookback_weeks
        if not plan and end > _last_completed_week():
            raise typer.BadParameter("end-week must be a fully completed UTC ISO week")
        if plan:
            typer.echo(
                json.dumps(
                    {
                        "mode": "planning_only",
                        "providers": ids,
                        "first_week": str(end.shift(1 - count)),
                        "last_week": str(end),
                        "optical_pixels": pixels,
                        "radar_pixels": radar,
                        "areas": [
                            {
                                "site_id": area.site_id,
                                "geometry": area.geometry.model_dump(mode="json"),
                                "provenance": area.provenance,
                            }
                            for area in areas
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        output = access_spike(
            areas,
            project.settings,
            project.workspace,
            end,
            count,
            ids,
            optical_pixels=pixels,
            radar_pixels=radar,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Access report: {output}")
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    if report["failures"]:
        typer.echo(
            "Some access checks failed; see the saved report for explicit statuses.", err=True
        )
        raise typer.Exit(1)


@providers_app.command("validate-optical")
def validate_optical(
    ctx: typer.Context,
    report_dir: Annotated[Path, typer.Option(help="Existing external spike report directory.")],
    aoi_file: Annotated[Path, typer.Option(help="The approved AOIs used for this spike.")],
    provider: Annotated[str, typer.Option(help="Optical provider to verify.")] = "cdse_stac",
) -> None:
    """Verify saved optical pixels and provenance without making network requests."""
    from allyourbase.providers.validation import validate_optical_report

    project = _project_from_context(ctx)
    if report_dir.resolve().is_relative_to(project.root):
        raise typer.BadParameter("report directory must be outside the code repository")
    try:
        summary = validate_optical_report(
            report_dir, _areas(project, aoi_file, False), project.settings, provider
        )
    except (ValueError, OSError):
        raise typer.BadParameter(
            "optical validation failed; check completeness, provenance, grids and hashes"
        ) from None
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
