"""Prepare source-pinned monitoring geometry without inventing roles or dated claims."""

import hashlib
import html
import json
import tempfile
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter
from shapely.geometry import mapping
from shapely.ops import unary_union

from allyourbase.catalogue.approvals import approval_for_packet, review_id
from allyourbase.catalogue.packet import build_packet
from allyourbase.loading import InputError
from allyourbase.models.catalogue import Zone, validate_zone_containment
from allyourbase.models.geometry import Geometry, anchor_of, shape_on_anchor
from allyourbase.project import Project
from allyourbase.sources.contracts import Snapshot
from allyourbase.sources.store import workflow_lock


def _geometry(raw: dict[str, Any]) -> Geometry:
    return cast(Geometry, TypeAdapter[Any](cast(Any, Geometry)).validate_python(raw))


def _polygonal(shape: Any) -> Any:
    if shape.geom_type in {"Polygon", "MultiPolygon"}:
        return shape
    return unary_union([_polygonal(part) for part in shape.geoms if part.area > 0])


def _wrapped(shape: Any) -> Geometry:
    def wrap(value: Any) -> Any:
        if len(value) == 2 and all(isinstance(v, (float, int)) for v in value):
            # Avoid rounding ordinary longitudes during an identity operation.
            x = value[0]
            return [x if -180 <= x <= 180 else (x + 180) % 360 - 180, value[1]]
        return [wrap(part) for part in value]

    raw = dict(mapping(_polygonal(shape)))
    raw["coordinates"] = wrap(raw["coordinates"])
    return _geometry(raw)


def draft_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Retain contained, compatible zones; water is a mask only within each zone."""
    geometry = _geometry(candidate["geometry"])
    anchor = anchor_of(geometry)
    footprint = shape_on_anchor(geometry, anchor)
    selected = []
    deferred = []
    masks = []
    for record in candidate["zones"]:
        shape = shape_on_anchor(_geometry(record["geometry"]), anchor)
        if record["hint"] == "water_mask" and record["evidence"]:
            masks.append((record, shape))
            continue
        reason = (
            "missing_exact_staged_evidence"
            if not record["evidence"]
            else "unsupported_monitoring_role"
            if record["hint"] not in candidate["primary_zone_types"]
            else "monitoring_zone_crosses_footprint"
            if not footprint.covers(shape)
            else None
        )
        if reason:
            deferred.append({"source_record": record["source_record"], "reason": reason})
        else:
            selected.append((record, shape))
    prepared = []
    used_masks: set[str] = set()
    for record, shape in selected:
        intersections = []
        mask_evidence = []
        for mask, water in masks:
            intersection = shape.intersection(water)
            if intersection.area <= 0:
                continue
            intersections.append(_polygonal(intersection))
            used_masks.add(mask["source_record"])
            mask_evidence.append(
                {
                    "source_record": mask["source_record"],
                    "operation": "intersection_with_monitoring_zone",
                    "evidence": mask["evidence"],
                }
            )
        water_mask = _wrapped(unary_union(intersections)) if intersections else None
        zone = Zone(
            id=record["source_record"].replace("/", "-"),
            zone_type=record["hint"],
            geometry=_geometry(record["geometry"]),
            water_mask=water_mask,
            sources=sorted(
                {e["source_id"] for e in record["evidence"]}
                | {e["source_id"] for m in mask_evidence for e in m["evidence"]}
            ),
        )
        if water_mask is not None and not shape.covers(shape_on_anchor(water_mask, anchor)):
            raise InputError("derived water mask failed exact zone containment")
        prepared.append(
            {
                "zone": zone.model_dump(mode="json"),
                "source_record": record["source_record"],
                "operation": "unchanged_source_zone",
                "evidence": record["evidence"],
                "mask_operations": mask_evidence,
            }
        )
    deferred.extend(
        {
            "source_record": mask["source_record"],
            "reason": "no_positive_area_overlap_with_selected_zones",
        }
        for mask, _ in masks
        if mask["source_record"] not in used_masks
    )
    validate_zone_containment(geometry, [Zone.model_validate(z["zone"]) for z in prepared])
    missing_evidence = any(r["reason"] == "missing_exact_staged_evidence" for r in deferred)
    return {
        "candidate_id": candidate["id"],
        "source_record": candidate["source_record"],
        "name": candidate["name"],
        "site_type": candidate["site_type"],
        "notes": candidate.get("notes", []),
        "source_attributes": candidate.get("source_attributes", {}),
        "geometry": candidate["geometry"],
        "footprint_evidence": candidate["footprint_evidence"],
        "zones": prepared,
        "deferred_source_records": deferred,
        "geometry_ready": bool(prepared) and not missing_evidence,
        "missing": ["sourced_status_and_claim_dates", "dated_unit_and_equipment_links"]
        + ([] if prepared else ["compatible_monitoring_zone_geometry_or_role"])
        + (["unstaged_zone_or_mask_evidence"] if missing_evidence else []),
    }


def check_draft_output(project: Project, packet_path: Path, output: Path) -> Path:
    packet_path, output = packet_path.expanduser().resolve(), output.expanduser().resolve()
    if output.is_relative_to(project.root.resolve()):
        raise InputError("prepared geometry must stay outside the code repository")
    if output == packet_path.parent or output in packet_path.parents:
        raise InputError("prepared geometry must not overwrite the source packet")
    return output


def build_geometry_drafts(project: Project, packet_path: Path) -> dict[str, Any]:
    """Reconstruct approved source evidence and validate geometry without writing drafts."""
    packet_path = packet_path.expanduser().resolve()
    packet_bytes = packet_path.read_bytes()
    packet = json.loads(packet_bytes)
    with workflow_lock(project.workspace):
        approval = approval_for_packet(project, packet)
        if approval is None:
            raise InputError("prepare geometry from a packet with retained owner approval")
        # Reconstruct from snapshots and eligible proposals, rather than trusting packet
        # flags/IDs or an approval of a manually altered packet.
        with tempfile.TemporaryDirectory(dir=project.workspace / "review") as temporary:
            directory = Path(temporary)
            selection = directory / "selection.json"
            selection.write_text(json.dumps(packet["selection"]), encoding="utf-8")
            manifests = [
                project.workspace / "sources" / s.spec.source.id / s.id / "manifest.json"
                for s in (Snapshot.model_validate(raw) for raw in packet["sources"])
            ]
            build_packet(
                project,
                selection,
                manifests[0],
                manifests[1],
                directory / "packet",
                packet["review_url"],
            )
            fresh = json.loads((directory / "packet/packet.json").read_text(encoding="utf-8"))
            if review_id(fresh) != review_id(packet):
                raise InputError("packet no longer matches retained source and eligible evidence")
        candidates = [draft_candidate(candidate) for candidate in fresh["candidates"]]
        return {
            "schema_version": 1,
            "production_accepted": False,
            "source_review_id": review_id(packet),
            "source_packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
            "owner_approval": approval,
            "country": fresh["selection"]["country"],
            "sources": fresh["sources"],
            "candidate_sites": len(candidates),
            "geometry_ready_sites": sum(c["geometry_ready"] for c in candidates),
            "prepared_zones": sum(len(c["zones"]) for c in candidates),
            "candidates": candidates,
            "notice": "Geometry drafts only. Dates, status and historical links remain required. "
            "Source footprints and compatible zones are unchanged. Water masks are intersected "
            "with each selected zone; unrelated water and unsupported roles are deferred.",
        }


def prepare_geometry(project: Project, packet_path: Path, output: Path) -> dict[str, Any]:
    output = check_draft_output(project, packet_path, output)
    report = build_geometry_drafts(project, packet_path)
    candidates = report["candidates"]
    features = []
    for candidate in candidates:
        for entry in candidate["zones"]:
            zone = entry["zone"]
            for role, geometry in (
                (zone["zone_type"], zone["geometry"]),
                ("water_mask", zone["water_mask"]),
            ):
                if geometry is not None:
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": geometry,
                            "properties": {
                                "candidate_id": candidate["candidate_id"],
                                "zone_id": zone["id"],
                                "role": role,
                                "production_accepted": False,
                            },
                        }
                    )
    output.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("geometry-drafts.json", report),
        ("prepared-geometry.geojson", {"type": "FeatureCollection", "features": features}),
    ):
        (output / name).write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    template = Path(__file__).with_name("geometry_drafts.html").read_text(encoding="utf-8")
    encoded = json.dumps(report, ensure_ascii=False).replace("<", r"\u003c").replace("&", r"\u0026")
    (output / "preview.html").write_text(
        template.replace("DRAFT_NOTICE", html.escape(report["notice"])).replace(
            "DRAFT_DATA", encoded
        ),
        encoding="utf-8",
    )
    return {
        key: report[key]
        for key in (
            "candidate_sites",
            "geometry_ready_sites",
            "prepared_zones",
            "production_accepted",
            "source_review_id",
        )
    } | {"output": str(output)}
