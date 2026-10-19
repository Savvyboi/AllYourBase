"""Small persistent JSON/PNG history and a buildless, escaped static report."""

import hashlib
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from allyourbase.monitor.config import Location, Locations, MonitorConfig
from allyourbase.monitor.fetch import require_optical
from allyourbase.monitor.prepare import Comparison

NOTICE = "Possible ground change only. Weather, moisture, vegetation, snow and image misalignment can produce changes. No cause, people/vehicle count or confidence percentage is inferred. A 10 m grid is not guaranteed 10 m resolving power. Thresholds are prototypes, not validated detection limits."  # noqa: E501
ATTRIBUTION = "Contains modified Copernicus Sentinel data. Processed through Copernicus Data Space Sentinel Hub."  # noqa: E501


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    if path.exists() and path.read_bytes() == data:
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def preview(
    data: NDArray[np.float32], valid: NDArray[np.bool_], sensor: str, config: MonitorConfig
) -> NDArray[np.uint8]:
    if sensor != "s2":
        raise ValueError("only Sentinel-2 previews are supported")
    rgb = np.moveaxis(data[[2, 1, 0]], 0, -1) / config.optical_preview_max
    result = (np.clip(np.nan_to_num(rgb), 0, 1) * 255).astype(np.uint8)
    result[~valid] = [38, 49, 61]
    return cast(NDArray[np.uint8], result)


def save_detection(
    history: Path,
    location: Location,
    comparison: Comparison,
    mask: NDArray[np.bool_],
    config: MonitorConfig,
    dates: dict[str, str],
) -> dict[str, Any]:
    from PIL import Image
    from rasterio.features import shapes

    scene = comparison.current.acquisition
    require_optical(scene)
    version = config.analysis_version()
    identifier = hashlib.sha256(
        json.dumps(
            [location.id, scene.sensor, scene.scene_id, version], separators=(",", ":")
        ).encode()
    ).hexdigest()[:24]
    images = {
        "before": preview(comparison.baseline, comparison.common, scene.sensor, config),
        "after": preview(comparison.current.pixels, comparison.common, scene.sensor, config),
    }
    images["change"] = images["after"].copy()
    images["change"][mask] = (
        images["change"][mask] * 0.35 + np.array([255, 104, 82]) * 0.65
    ).astype(np.uint8)
    for kind, array in images.items():
        path = history / "previews" / f"{identifier}-{kind}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(array).resize((400, 400), Image.Resampling.NEAREST).save(
            path, optimize=True
        )
    grid = comparison.current.grid
    record = {
        "schema_version": 1,
        "id": identifier,
        "label": "possible ground change",
        "location": location.model_dump(mode="json"),
        "sensor": scene.sensor,
        "supported_by_sensors": ["s2"],
        "current": scene.model_dump(mode="json", exclude={"assets"}),
        "baseline_scenes": [
            s.acquisition.model_dump(mode="json", exclude={"assets"})
            for s in comparison.baseline_scenes
        ],
        "dates": dates,
        "analysis_version": version,
        "thresholds": config.thresholds(),
        "valid_common_fraction": comparison.coverage,
        "changed_area_m2": int(mask.sum()) * 100,
        "grid": grid.model_dump(mode="json"),
        "patches": [
            geometry
            for geometry, value in shapes(
                mask.astype(np.uint8), mask=mask, transform=grid.transform, connectivity=8
            )
            if value == 1
        ],
        "patch_crs": f"EPSG:{grid.epsg}",
        "baseline_preview": "pixelwise median composite of valid baseline observations",
        "previews": {kind: f"previews/{identifier}-{kind}.png" for kind in images},
        "notice": NOTICE,
        "attribution": ATTRIBUTION,
    }
    write_json(history / "detections" / f"{identifier}.json", record)
    return record


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("report timestamps must be timezone-aware")
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _page(title: str, body: str, prefix: str = "") -> str:
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Small Sentinel ground-change checks with explicit data coverage and source provenance."><title>{html.escape(title)} · AllYourBase</title><link rel="stylesheet" href="{prefix}style.css"><script src="{prefix}app.js" defer></script></head><body><header><a class="eyebrow" href="{prefix}index.html">AllYourBase / Sentinel monitor</a><h1>{html.escape(title)}</h1><p class="intro">Sentinel-2 optical imagery. Seven complete UTC days. A 28-day earlier baseline. A fixed 1 km square.</p></header><main>{body}<p class="notice">{NOTICE}</p></main><footer>{ATTRIBUTION}</footer></body></html>'  # noqa: E501


def _detection_card(record: dict[str, Any], prefix: str) -> str:
    e = html.escape
    scene = record["current"]
    dates = record["dates"]
    figures = "".join(
        f'<figure><img src="{prefix}{e(record["previews"][kind], quote=True)}" alt="{label}" loading="lazy"><figcaption>{label}</figcaption></figure>'  # noqa: E501
        for kind, label in [
            ("before", "Before · baseline median composite"),
            ("after", "After · current acquisition"),
            ("change", "Possible-change patches highlighted"),
        ]
    )
    provenance = e(
        json.dumps(
            {
                k: record[k]
                for k in [
                    "current",
                    "baseline_scenes",
                    "grid",
                    "analysis_version",
                    "thresholds",
                    "patch_crs",
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return f'<article class="card detection-card" data-category="{e(record["location"].get("category", "Uncategorized"))}"><p class="eyebrow">Possible ground change</p><h3>{e(record["location"]["name"])}</h3><p>Sentinel-2 optical</p><p class="category-badge">{e(record["location"].get("category", "Uncategorized"))}</p><p class="muted">Observed {_utc(scene["acquired_at"])} · baseline {_utc(dates["baseline_start"])} to {_utc(dates["target_start"])} (exclusive)</p><div class="metrics"><span><strong>{record["changed_area_m2"]:,} m²</strong>changed area · this sensor</span><span><strong>{record["valid_common_fraction"]:.0%}</strong>valid common AOI</span></div><div class="images">{figures}</div><details><summary>Scenes, grid and prototype thresholds</summary><pre>{provenance}</pre></details></article>'  # noqa: E501


def build_site(history: Path, output: Path, locations: Locations | None = None) -> dict[str, int]:
    import re
    from urllib.parse import quote

    history, output = history.resolve(), output.resolve()
    if history == output or history in output.parents or output in history.parents:
        raise ValueError("history and published output must be separate directories")
    current_locations = {s.id: s for s in locations.sites} if locations else {}

    def displayed(raw: dict[str, Any]) -> dict[str, Any]:
        retained = Location.model_validate(raw)
        current = current_locations.get(retained.id)
        # Categories/names are display metadata; preserve the frozen coordinates.
        if current:
            retained = retained.model_copy(
                update={"name": current.name, "category": current.category}
            )
        return retained.model_dump(mode="json")

    all_detections = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((history / "detections").glob("*.json"))
    ]
    all_previews = set()
    for record in all_detections:
        record["location"] = displayed(record["location"])
        if not re.fullmatch(r"[0-9a-f]{24}", record["id"]):
            raise ValueError("invalid detection ID")
        for kind in ("before", "after", "change"):
            expected = f"previews/{record['id']}-{kind}.png"
            if record["previews"][kind] != expected:
                raise ValueError("invalid preview path")
            all_previews.add(expected)
    # Historical radar reports remain in the archive but never enter active Pages output.
    detections = [r for r in all_detections if r["sensor"] == "s2"]
    for record in detections:
        record["supported_by_sensors"] = ["s2"]
        record.pop("overlapping_other_sensor_scene_ids", None)
        record["thresholds"] = {
            k: v
            for k, v in record["thresholds"].items()
            if not k.startswith("radar_") and k != "lee_window"
        }
    optical_ids = {r["id"] for r in detections}
    latest: dict[str, dict[str, Any]] = {}
    for path in sorted((history / "checks").glob("*/*.json")):
        check = json.loads(path.read_text(encoding="utf-8"))
        location = Location.model_validate(displayed(check["location"]))
        check["location"] = location.model_dump(mode="json")
        check["thresholds"] = {
            k: v
            for k, v in check["thresholds"].items()
            if not k.startswith("radar_") and k != "lee_window"
        }
        check["sensors"] = [s for s in check["sensors"] if s["sensor"] == "s2"]
        check["usable_sensors"] = [s for s in check["usable_sensors"] if s == "s2"]
        check["errors"] = [e for e in check.get("errors", []) if e.get("sensor", "s2") == "s2"]
        check["detection_ids"] = [i for i in check["detection_ids"] if i in optical_ids]
        if check["status"] not in {
            "possible_change",
            "no_change_detected",
            "insufficient_data",
            "error",
        }:
            raise ValueError("unknown check status")
        # Older combined checks must not keep a status caused only by radar.
        check["status"] = (
            "possible_change"
            if check["detection_ids"]
            else "error"
            if check["errors"]
            else "no_change_detected"
            if check["usable_sensors"]
            else "insufficient_data"
        )
        previous = latest.get(location.id)
        if previous is None or (check["dates"]["end_exclusive"], check["checked_at"]) > (
            previous["dates"]["end_exclusive"],
            previous["checked_at"],
        ):
            latest[location.id] = check
    allowed = {"index.html", ".nojekyll", "style.css", "app.js", "reports.json"}
    allowed.update(f"locations/{identifier}.html" for identifier in latest)
    active_previews = {name for r in detections for name in r["previews"].values()}
    allowed.update(active_previews)
    if output.exists() and any(
        p.is_symlink()
        or (p.is_file() and p.relative_to(output).as_posix() not in allowed | all_previews)
        for p in output.rglob("*")
    ):
        raise ValueError("site output contains unexpected files; choose a clean directory")
    output.mkdir(parents=True, exist_ok=True)
    # Remove only known, validated obsolete generated previews from this output directory.
    for name in all_previews - active_previews:
        (output / name).unlink(missing_ok=True)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    for asset in ("style.css", "app.js"):
        copyfile(Path(__file__).parent / "web" / asset, output / asset)
    for record in detections:
        for name in record["previews"].values():
            source = history / name
            if source.is_symlink() or not source.resolve().is_relative_to(history):
                raise ValueError("preview path escapes history")
            (output / name).parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, output / name)
    e = html.escape
    categories = sorted(
        {c["location"]["category"] for c in latest.values()}
        | {r["location"]["category"] for r in detections},
        key=str.casefold,
    )
    cards: dict[str, list[str]] = {category: [] for category in categories}
    for identifier, check in sorted(
        latest.items(), key=lambda p: p[1]["location"]["name"].casefold()
    ):
        location, status = check["location"], check["status"]
        category = location["category"]
        usability = "usable" if check["usable_sensors"] else "insufficient or unavailable"
        cards[category].append(
            f'<article class="card location-card" data-status="{status}" '
            f'data-category="{e(category)}">'
            f'<span class="status {status}">{status.replace("_", " ")}</span>'
            f'<h3><a href="locations/{identifier}.html">{e(location["name"])}</a></h3>'
            f'<p class="category-badge">{e(category)}</p>'
            f'<p class="muted">{location["latitude"]:.6f}, {location["longitude"]:.6f}'
            " · 1 km square</p>"
            f"<p>Target {_utc(check['dates']['target_start'])} to "
            f"{_utc(check['dates']['end_exclusive'])} (exclusive)</p>"
            f'<p class="muted">Sentinel-2: {usability}</p></article>'
        )
        records = sorted(
            [r for r in detections if r["location"]["id"] == identifier],
            key=lambda r: r["current"]["acquired_at"],
            reverse=True,
        )
        category_url = "../index.html?category=" + quote(category, safe="")
        body = (
            f'<p class="category-badge">Category: <a href="{e(category_url)}">{e(category)}</a></p>'
            f'<p><span class="status {status}">{status.replace("_", " ")}</span>'
            f" · latest check ends {_utc(check['dates']['end_exclusive'])}</p>"
            f"<p>{location['latitude']:.6f}, {location['longitude']:.6f} · Sentinel-2 optical</p>"
            '<p class="muted">No detected change describes only valid observed coverage. '
            "Cloud, snow and other masks can leave insufficient data.</p>"
            "<details><summary>Latest check / data gaps</summary>"
            f"<pre>{e(json.dumps(check, ensure_ascii=False, indent=2))}</pre></details>"
            '<h2>Detection history</h2><div class="grid">'
            + (
                "".join(_detection_card(r, "../") for r in records)
                or "<p>No optical detections yet.</p>"
            )
            + "</div>"
        )
        target = output / "locations" / f"{identifier}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_page(location["name"], body, "../"), encoding="utf-8")
    groups = "".join(
        f'<section class="category-group" data-category-group="{e(category)}">'
        f'<h3>{e(category)}</h3><div class="grid">{"".join(cards[category])}</div></section>'
        for category in categories
        if cards[category]
    )
    options = '<option value="">All categories</option>' + "".join(
        f'<option value="{e(c)}">{e(c)}</option>' for c in categories
    )
    filters = (
        '<label class="category-filter">Category '
        '<select id="category-filter" aria-label="Category">'
        f"{options}</select></label>"
        '<div class="filters" aria-label="Filter latest check statuses">'
        + "".join(
            f'<button data-filter="{status}" aria-pressed="{str(status == "all").lower()}">'
            f"{label}</button>"
            for status, label in [
                ("all", "All checks"),
                ("possible_change", "Possible change"),
                ("no_change_detected", "No change detected"),
                ("insufficient_data", "Insufficient data"),
                ("error", "Errors"),
            ]
        )
        + "</div>"
    )
    recent = []
    for category in categories:
        recent.extend(
            sorted(
                [r for r in detections if r["location"]["category"] == category],
                key=lambda r: r["current"]["acquired_at"],
                reverse=True,
            )[:12]
        )
    recent.sort(key=lambda r: r["current"]["acquired_at"], reverse=True)
    body = (
        "<h2>Latest location checks</h2>"
        + filters
        + groups
        + '<p id="checks-empty" hidden>No locations match these filters.</p>'
        + ("" if latest else "<p>No location checks yet.</p>")
        + '<h2>Recent possible changes</h2><div class="grid">'
        + "".join(_detection_card(r, "") for r in recent)
        + "</div>"
        + f'<p id="detections-empty"{" hidden" if recent else ""}>'
        "No optical possible-change reports in this category.</p>"
    )
    (output / "index.html").write_text(_page("Possible ground change", body), encoding="utf-8")
    write_json(output / "reports.json", {"checks": list(latest.values()), "detections": detections})
    return {"locations": len(latest), "detections": len(detections)}
