"""Reproducible eight-week access reports, with failures explicitly represented."""

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from allyourbase import ALGO_VERSION, __version__
from allyourbase.models.geometry import Geometry
from allyourbase.models.settings import Settings
from allyourbase.providers.budget import BudgetLedger
from allyourbase.providers.client import ProviderClient
from allyourbase.providers.contracts import AccessProvider, Acquisition, ProviderError
from allyourbase.providers.http import Transport
from allyourbase.weeks import ISOWeek, week_range


@dataclass(frozen=True)
class AccessArea:
    site_id: str
    geometry: Geometry
    provenance: dict[str, Any]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", self.site_id):
            raise ValueError("test area id must be a safe lowercase slug")


def write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def access_spike(
    areas: list[AccessArea],
    settings: Settings,
    workspace: Path,
    end_week: ISOWeek,
    weeks: int,
    provider_ids: list[str],
    *,
    optical_pixels: bool = False,
    radar_pixels: bool = False,
    client: httpx.Client | None = None,
) -> Path:
    if not areas or weeks < 1 or not provider_ids:
        raise ValueError("spike needs areas, providers and a positive week count")
    if len({area.site_id for area in areas}) != len(areas):
        raise ValueError("duplicate test area id")
    for identifier in provider_ids:
        if identifier not in settings.providers.definitions:
            raise ValueError(f"unknown provider {identifier}")
    interval = week_range(end_week.shift(1 - weeks), end_week)
    processed = datetime.now(UTC)
    output = workspace / "spikes" / f"{processed.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex}"
    output.mkdir(parents=True)
    owned_client = client is None
    client = client or httpx.Client()
    transport = Transport(client, settings.access, settings.schedule.retry_attempts)
    ledger = BudgetLedger(workspace, settings)
    rows: list[dict[str, Any]] = []
    acquisitions: list[dict[str, Any]] = []
    downloads: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    finished = False
    try:
        for area in areas:
            for identifier in provider_ids:
                provider = settings.providers.definitions[identifier]
                connector: AccessProvider = ProviderClient(identifier, settings, transport, ledger)
                status = "ok"
                scenes: list[Acquisition] = []
                try:
                    scenes = connector.discover(
                        area.geometry,
                        interval[0].start,
                        interval[-1].end,
                    )
                except ProviderError as exc:
                    status = exc.code
                    failures.append(
                        {"site_id": area.site_id, "provider": identifier, "status": status}
                    )
                for week in interval:
                    weekly = [
                        scene for scene in scenes if week.start <= scene.acquired_at < week.end
                    ]
                    rows.append(
                        {
                            "site_id": area.site_id,
                            "provider": identifier,
                            "sensor": provider.sensor,
                            "week": str(week),
                            "status": status
                            if status != "ok"
                            else ("ok" if weekly else "no_acquisitions"),
                            "looks": len(weekly),
                            "eligible_optical_looks": sum(
                                scene.cloud_cover is None
                                or scene.cloud_cover
                                <= settings.access.optical_max_scene_cloud_percent
                                for scene in weekly
                            )
                            if provider.sensor == "s2"
                            else None,
                            "latest_acquired_at": max(
                                (scene.acquired_at for scene in weekly), default=None
                            ),
                        }
                    )
                acquisitions.extend(
                    {"site_id": area.site_id, **scene.model_dump(mode="json")} for scene in scenes
                )
                candidates = [
                    scene
                    for scene in reversed(scenes)
                    if scene.sensor == "s1"
                    or scene.cloud_cover is None
                    or scene.cloud_cover <= settings.access.optical_max_scene_cloud_percent
                ]
                requested_pixels = (provider.sensor == "s2" and optical_pixels) or (
                    provider.sensor == "s1" and radar_pixels
                )
                if not candidates:
                    if requested_pixels and status == "ok":
                        downloads.append(
                            {
                                "site_id": area.site_id,
                                "provider": identifier,
                                "status": "no_eligible_acquisitions",
                            }
                        )
                    continue
                scene = candidates[0]
                directory = output / "chips" / area.site_id / identifier
                if requested_pixels:
                    try:
                        result = connector.read_window(scene, area.geometry, directory)
                        downloads.append(
                            {
                                "site_id": area.site_id,
                                "provider": identifier,
                                "status": "ok",
                                **result,
                            }
                        )
                    except ProviderError as exc:
                        downloads.append(
                            {
                                "site_id": area.site_id,
                                "provider": identifier,
                                "status": exc.code,
                            }
                        )
        finished = True
    finally:
        # Persist completed measurements even when a later operation is interrupted.
        with (output / "acquisitions-by-week.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "site_id",
                    "provider",
                    "sensor",
                    "week",
                    "status",
                    "looks",
                    "eligible_optical_looks",
                    "latest_acquired_at",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        observations = [asdict(observation) for observation in transport.observations]
        write_json(
            output / "acquisitions.json",
            {
                "algo_version": ALGO_VERSION,
                "processed_at": processed.isoformat(),
                "acquisitions": acquisitions,
            },
        )
        write_json(
            output / "usage.json",
            {
                "requests": observations,
                "request_count": len(observations),
                "known_processing_units": sum(
                    o.processing_units or 0 for o in transport.observations
                ),
                "process_requests_with_unknown_cost": sum(
                    o.operation == "radar_process" and o.processing_units is None
                    for o in transport.observations
                ),
                "optical_window_http_counts": None,
                "optical_window_http_counts_note": (
                    "GDAL range-request counts and bytes are not instrumented in this spike."
                ),
            },
        )
        write_json(
            output / "report.json",
            {
                "report_version": 1,
                "package_version": __version__,
                "algo_version": ALGO_VERSION,
                "processed_at": processed.isoformat(),
                "first_week": str(interval[0]),
                "last_week": str(interval[-1]),
                "providers": provider_ids,
                "areas": [
                    {
                        "site_id": area.site_id,
                        "geometry": area.geometry.model_dump(mode="json"),
                        "provenance": area.provenance,
                    }
                    for area in areas
                ],
                "downloads": downloads,
                "analysis_implemented": False,
                "run_finished": finished,
                "failures": failures
                + [
                    {"site_id": d["site_id"], "provider": d["provider"], "status": d["status"]}
                    for d in downloads
                    if d["status"] != "ok"
                ],
                "pixel_requests": {"optical": optical_pixels, "radar": radar_pixels},
                "provider_selection": "not_decided",
            },
        )
        if owned_client:
            client.close()
    return output
