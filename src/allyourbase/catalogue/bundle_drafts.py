"""Prepare incomplete review bundles from reconstructed, approved source geometry."""

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from allyourbase.catalogue.geometry_drafts import build_geometry_drafts, check_draft_output
from allyourbase.catalogue.review import ReviewBundle
from allyourbase.loading import InputError
from allyourbase.project import Project
from allyourbase.sources.snapshots import canonical


def _candidate_draft(candidate: dict[str, Any], country: str) -> dict[str, Any]:
    evidence = list(candidate["footprint_evidence"])
    for entry in candidate["zones"]:
        evidence.extend(entry["evidence"])
        for operation in entry["mask_operations"]:
            evidence.extend(operation["evidence"])
    evidence = sorted({canonical(e): e for e in evidence}.values(), key=canonical)
    primary = next(
        (e["proposal_id"] for e in candidate["footprint_evidence"] if e["state"] == "pending"),
        None,
    )
    bundle = {
        "sites": [
            {
                "type": "Feature",
                "geometry": candidate["geometry"],
                "properties": {
                    "id": candidate["candidate_id"],
                    "name": candidate["name"],
                    "country": country,
                    "site_type": candidate["site_type"],
                    "sources": sorted({e["source_id"] for e in evidence}),
                    "osm_ids": [candidate["source_record"]],
                    "zones": [entry["zone"] for entry in candidate["zones"]],
                },
            }
        ],
        "units": [],
        "equipment": [],
        "terms": {},
        "evidence_proposals": sorted({e["proposal_id"] for e in evidence} - {primary}),
    }
    errors = []
    try:
        ReviewBundle.model_validate(bundle)
    except ValidationError as exc:
        errors = [
            {
                "path": "/".join(map(str, error["loc"])),
                "code": error["type"],
                "message": error["msg"],
            }
            for error in exc.errors(include_input=False, include_url=False)
        ]
    return {
        "candidate_id": candidate["candidate_id"],
        "name": candidate["name"],
        "primary_proposal": primary,
        "bundle": bundle,
        "evidence": evidence,
        "geometry_ready": candidate["geometry_ready"],
        "bundle_contract_valid": not errors,
        "validation_errors": errors,
        "missing": [*candidate["missing"], "processing_sensor_choice"]
        + ([] if primary else ["active_pending_primary_proposal"]),
    }


def prepare_bundles(project: Project, packet_path: Path, output: Path) -> dict[str, Any]:
    """Write review drafts and an evidence worklist; leave decisions/catalogue untouched."""
    output = check_draft_output(project, packet_path, output)
    geometry = build_geometry_drafts(project, packet_path)
    candidates = []
    files: dict[str, Any] = {}
    for candidate in geometry["candidates"]:
        draft = _candidate_draft(candidate, geometry["country"])
        identifier = draft["candidate_id"]
        bundle_path = f"{identifier}/bundle-draft.json"
        provenance_path = f"{identifier}/provenance.json"
        files[bundle_path] = draft.pop("bundle")
        files[provenance_path] = {
            "schema_version": 1,
            "production_accepted": False,
            "source_review_id": geometry["source_review_id"],
            "source_packet_sha256": geometry["source_packet_sha256"],
            "owner_approval": geometry["owner_approval"],
            "sources": geometry["sources"],
            "evidence": draft.pop("evidence"),
            "geometry": candidate,
        }
        candidates.append(draft | {"bundle_path": bundle_path, "provenance_path": provenance_path})
    gap_counts: dict[str, int] = {}
    for draft in candidates:
        for gap in draft["missing"]:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1
    report = {
        "schema_version": 1,
        "production_accepted": False,
        "milestone_ready": False,
        "source_review_id": geometry["source_review_id"],
        "source_packet_sha256": geometry["source_packet_sha256"],
        "owner_approval": geometry["owner_approval"],
        "candidate_sites": len(candidates),
        "geometry_ready_sites": geometry["geometry_ready_sites"],
        "prepared_zones": geometry["prepared_zones"],
        "contract_valid_bundles": sum(d["bundle_contract_valid"] for d in candidates),
        "gap_counts": dict(sorted(gap_counts.items())),
        "candidates": candidates,
        "notice": "Incomplete review drafts. Status, factual dates and sensor choices are "
        "omitted; historical unit/equipment associations require separately verified evidence. "
        "Owner approval covers displayed source proposals only. Geometry validity and bundle "
        "contract validity do not establish milestone readiness or factual truth.",
    }
    encoded = {
        name: (json.dumps(content, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        for name, content in files.items()
    }
    report["file_sha256"] = {
        name: hashlib.sha256(content).hexdigest() for name, content in encoded.items()
    }
    encoded["bundle-drafts.json"] = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    lines = [
        "# Structured catalogue review drafts",
        "",
        report["notice"],
        "",
        f"Source review ID: `{geometry['source_review_id']}`.",
        "",
        "| Candidate | Zones | Geometry ready | Contract gaps | Draft |",
        "| --- | --- | --- | --- | --- |",
    ]
    for candidate, draft in zip(geometry["candidates"], candidates, strict=True):
        # Display labels can contain source text; keep the table structure intact.
        label = draft["name"].replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        gaps = ", ".join(error["path"] for error in draft["validation_errors"])
        lines.append(
            f"| {label} | {len(candidate['zones'])} | {draft['geometry_ready']} | "
            f"{gaps} | [JSON]({draft['bundle_path']}) |"
        )
    lines += [
        "",
        "The JSON report retains missing evidence tasks and exact proposal/snapshot locators. "
        "Each candidate has a provenance sidecar with unchanged source caveats and geometry "
        "operations. Existing historical notes remain pending and are not automatically attached.",
        "",
        "Copy a draft before editing it. Supply supported status/dates, choose sensors and "
        "resolve the evidence tasks before validating through catalogue accept --dry-run. "
        "A successful dry-run checks contracts; catalogue readiness separately checks dated "
        "historical links. Neither operation substitutes for source verification.",
        "",
    ]
    encoded["review-bundles.md"] = "\n".join(lines).encode("utf-8")
    # Refuse all conflicts before writing, so regeneration cannot erase review edits.
    for name, content in encoded.items():
        target = output / name
        if not target.resolve().is_relative_to(output):
            raise InputError("draft output path escapes its directory")
        if target.exists() and (not target.is_file() or target.read_bytes() != content):
            raise InputError("draft output differs; use a new directory to preserve review edits")
    for name, content in encoded.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
    return {
        key: report[key]
        for key in (
            "candidate_sites",
            "geometry_ready_sites",
            "prepared_zones",
            "contract_valid_bundles",
            "production_accepted",
            "milestone_ready",
            "source_review_id",
        )
    } | {"output": str(output)}
