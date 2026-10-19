"""One Python entry point for a bounded local/Actions run and complete static build."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
import numpy as np

from allyourbase.monitor.config import (
    Grid,
    Location,
    Locations,
    MonitorConfig,
    freeze_grid,
    windows,
)
from allyourbase.monitor.detect import detect
from allyourbase.monitor.fetch import Cutout, Fetcher, require_optical, same_observation
from allyourbase.monitor.prepare import Comparison, compare
from allyourbase.monitor.report import build_site, save_detection, write_json
from allyourbase.providers.contracts import Acquisition, ProviderError


class Imagery(Protocol):
    def discover(
        self, grid: Grid, sensor: str, start: datetime, end: datetime
    ) -> list[Acquisition]: ...
    def cutout(self, scene: Acquisition, grid: Grid) -> Cutout: ...


def check_location(
    location: Location,
    config: MonitorConfig,
    imagery: Imagery,
    history: Path,
    end_date: date | None = None,
) -> dict[str, Any]:
    baseline_start, target_start, end = windows(end_date)
    dates = {
        "baseline_start": baseline_start.isoformat(),
        "target_start": target_start.isoformat(),
        "end_exclusive": end.isoformat(),
    }
    grid = freeze_grid(location, history / "grids" / f"{location.id}.json")
    details = []
    errors = []
    results: list[tuple[Comparison, Any]] = []
    usable = set()
    for sensor in ("s2",):
        try:
            scenes = imagery.discover(grid, sensor, baseline_start, end)
        except (ProviderError, ValueError, OSError, KeyError, TypeError) as exc:
            code = exc.code if isinstance(exc, ProviderError) else "invalid_discovery"
            errors.append({"sensor": sensor, "code": code})
            continue
        cutouts = []
        skipped = []
        seen_observations: list[Acquisition] = []
        for scene in sorted(scenes, key=lambda s: (s.acquired_at, s.scene_id)):
            if not baseline_start <= scene.acquired_at < end:
                continue
            if scene.sensor != "s2":
                errors.append({"sensor": sensor, "code": "unsupported_sensor"})
                continue
            if any(same_observation(scene, previous) for previous in seen_observations):
                skipped.append(
                    {"scene_id": scene.scene_id, "reason": "same_acquisition_alternative_product"}
                )
                continue
            try:
                cutouts.append(imagery.cutout(scene, grid))
                seen_observations.append(scene)
            except (ProviderError, ValueError, OSError, KeyError, TypeError) as exc:
                code = exc.code if isinstance(exc, ProviderError) else "invalid_cutout"
                errors.append({"sensor": sensor, "scene_id": scene.scene_id, "code": code})
        baselines = [c for c in cutouts if c.acquisition.acquired_at < target_start]
        targets = [c for c in cutouts if target_start <= c.acquisition.acquired_at < end]
        comparisons = []
        for current in targets:
            matching = [c for c in baselines]
            comparison = compare(current, matching, config)
            mask = detect(comparison, config)
            sufficient = comparison.coverage >= config.minimum_common_coverage
            if sufficient:
                usable.add(sensor)
            comparisons.append(
                {
                    "scene_id": current.acquisition.scene_id,
                    "acquired_at": current.acquisition.acquired_at.isoformat(),
                    "baseline_scene_ids": [c.acquisition.scene_id for c in matching],
                    "valid_common_fraction": comparison.coverage,
                    "status": "possible_change"
                    if mask.any()
                    else "no_change_detected"
                    if sufficient
                    else "insufficient_data",
                    "changed_area_m2": int(mask.sum()) * 100,
                }
            )
            if mask.any():
                results.append((comparison, mask))
        details.append(
            {
                "sensor": sensor,
                "discovered_acquisitions": len(scenes),
                "skipped": skipped,
                "comparisons": comparisons,
                "status": "usable"
                if any(c["status"] != "insufficient_data" for c in comparisons)
                else "insufficient_data",
            }
        )
    ids = []
    for comparison, mask in results:
        ids.append(save_detection(history, location, comparison, mask, config, dates)["id"])
    check = {
        "schema_version": 1,
        "location": location.model_dump(mode="json"),
        "dates": dates,
        "checked_at": datetime.now(UTC).isoformat(),
        "analysis_version": config.analysis_version(),
        "thresholds": config.thresholds(),
        "status": "possible_change"
        if ids
        else "error"
        if errors
        else "no_change_detected"
        if usable
        else "insufficient_data",
        "usable_sensors": sorted(usable),
        "sensors": details,
        "errors": errors,
        "detection_ids": sorted(ids),
    }
    suffix = hashlib.sha256(config.analysis_version().encode()).hexdigest()[:12]
    write_json(history / "checks" / location.id / f"{end.date()}-{suffix}.json", check)
    return check


class SyntheticImagery:
    """Labelled fictional examples for offline acceptance and browser QA."""

    def __init__(self, end_date: date, changed: bool) -> None:
        self.end = windows(end_date)[2]
        self.changed = changed

    def discover(
        self, grid: Grid, sensor: str, start: datetime, end: datetime
    ) -> list[Acquisition]:
        if sensor != "s2":
            raise ValueError("synthetic monitor observations are Sentinel-2 only")
        return [
            Acquisition(
                provider="synthetic",
                collection="synthetic",
                scene_id=f"synthetic-{sensor}-{day}",
                sensor=sensor,
                acquired_at=self.end - timedelta(days=day),
            )
            for day in (32, 20, 10, 2)
        ]

    def cutout(self, scene: Acquisition, grid: Grid) -> Cutout:
        require_optical(scene)
        data = np.zeros((6, 100, 100), dtype=np.float32)
        data[:4] = 0.15
        data[4] = 4
        data[5] = 1
        if self.changed and scene.acquired_at == self.end - timedelta(days=2):
            data[:4, 35:55, 40:65] = 0.45
        return Cutout(scene, data, grid)


def run_monitor(
    config: MonitorConfig,
    locations: Locations,
    workspace: Path,
    history: Path,
    output: Path,
    end_date: date | None,
    *,
    live: bool,
) -> dict[str, Any]:
    from filelock import FileLock

    workspace.mkdir(parents=True, exist_ok=True)
    statuses = {}
    with (
        FileLock(str(workspace / "monitor.lock"), timeout=0),
        FileLock(str(history.resolve()) + ".lock", timeout=0),
        httpx.Client() as client,
    ):
        imagery = Fetcher(config, workspace / "cache", client)
        for location in locations.sites:
            if live:
                source: Imagery = imagery
            else:
                source = SyntheticImagery(
                    end_date or date(2020, 10, 12), changed=location.id.endswith("change")
                )
            try:
                check = check_location(
                    location,
                    config,
                    source,
                    history,
                    end_date if live else end_date or date(2020, 10, 12),
                )
                statuses[location.id] = check["status"]
            except (ValueError, OSError, KeyError, TypeError):
                statuses[location.id] = "error"
                retained = history / "grids" / f"{location.id}.json"
                displayed = (
                    json.loads(retained.read_text(encoding="utf-8"))["location"]
                    if retained.exists()
                    else location.model_dump(mode="json")
                )
                baseline, start, end = windows(end_date)
                failure = {
                    "schema_version": 1,
                    "location": displayed,
                    "dates": {
                        "baseline_start": baseline.isoformat(),
                        "target_start": start.isoformat(),
                        "end_exclusive": end.isoformat(),
                    },
                    "checked_at": datetime.now(UTC).isoformat(),
                    "analysis_version": config.analysis_version(),
                    "thresholds": config.thresholds(),
                    "status": "error",
                    "usable_sensors": [],
                    "sensors": [],
                    "detection_ids": [],
                    "errors": [{"code": "location_configuration_or_processing_error"}],
                }
                write_json(history / "checks" / location.id / f"{end.date()}-error.json", failure)
        usage = {
            "request_cap": config.max_requests,
            "requests_used": config.max_requests - imagery.transport.remaining,
            "reported_processing_units": sum(
                o.processing_units or 0 for o in imagery.transport.observations
            ),
            "unknown_process_charges": sum(
                o.operation == "process" and o.processing_units is None
                for o in imagery.transport.observations
            ),
        }
        write_json(
            workspace / "runs" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json"),
            {
                "statuses": statuses,
                **usage,
                "observations": [asdict(o) for o in imagery.transport.observations],
            },
        )
        built = build_site(history, output, locations)
    return {
        "statuses": statuses,
        "site": built,
        "output": str(output),
        "live": live,
        **usage,
        "analysis_version": config.analysis_version(),
    }
