"""Build an unapproved source-geometry review packet without editing the catalogue."""

import html
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from pydantic import Field, TypeAdapter, model_validator

from allyourbase.loading import InputError, load_model
from allyourbase.models.common import Contract, CountryCode, NonEmpty, Slug
from allyourbase.models.geometry import Geometry, anchor_of, shape_on_anchor
from allyourbase.project import Project
from allyourbase.sources.connectors import parse_records
from allyourbase.sources.contracts import Record, Snapshot
from allyourbase.sources.snapshots import verify_snapshot
from allyourbase.sources.store import Store


class Candidate(Contract):
    id: Slug
    name: NonEmpty
    site_type: Slug
    source_record: NonEmpty
    identity_records: list[NonEmpty] = Field(default_factory=list)
    notes: list[NonEmpty] = Field(default_factory=list)


class Selection(Contract):
    schema_version: Literal[1]
    country: CountryCode
    status: Literal["proposed"]
    scope: NonEmpty
    requested_on: date
    sites: list[Candidate] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sites(self) -> "Selection":
        if len({site.id for site in self.sites}) != len(self.sites):
            raise ValueError("duplicate candidate id")
        if len({site.source_record for site in self.sites}) != len(self.sites):
            raise ValueError("duplicate footprint in candidate selection")
        return self


def _shape(record: Record, anchor: float) -> Any:
    geometry = TypeAdapter[Any](cast(Any, Geometry)).validate_python(record.geometry)
    return shape_on_anchor(geometry, anchor)


def _records(snapshot: Snapshot, payload: Path) -> dict[str, Record]:
    selected = set(snapshot.spec.record_ids)
    records: dict[str, Record] = {}
    for record in parse_records(snapshot, payload):
        if selected and record.external_id not in selected:
            continue
        if record.external_id in records:
            raise InputError("duplicate source record ID in packet input")
        records[record.external_id] = record
    return records


def _proposal_index(store: Store, external_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Keep active pending/accepted records; external IDs alone never establish evidence."""
    index: dict[str, list[dict[str, Any]]] = {}
    for state in ("pending", "accepted"):
        for summary in store.proposals(state):
            record = summary["content"].get("record")
            if not record or record["external_id"] not in external_ids:
                continue
            proposal = store.proposal(summary["id"])
            if proposal["active"] and proposal["state"] in {"pending", "accepted"}:
                index.setdefault(record["external_id"], []).append(proposal)
    return index


def _evidence(
    proposals: list[dict[str, Any]], record: Record, snapshot: Snapshot
) -> list[dict[str, Any]]:
    result = []
    semantic = record.model_dump(mode="json", exclude={"locator"})
    for proposal in proposals:
        staged = Record.model_validate(proposal["content"]["record"])
        if staged.model_dump(mode="json", exclude={"locator"}) != semantic:
            continue
        for entry in proposal["evidence"]:
            if entry["manifest"] != snapshot.model_dump(mode="json"):
                continue
            result.append(
                {
                    "proposal_id": proposal["id"],
                    "record_id": entry["record_id"],
                    "source_id": snapshot.spec.source.id,
                    "snapshot_id": snapshot.id,
                    "locator": entry["locator"],
                    "state": proposal["state"],
                }
            )
    return result


def build_packet(
    project: Project,
    selection_path: Path,
    footprint_manifest: Path,
    zone_manifest: Path,
    output: Path,
    review_url: str,
) -> dict[str, Any]:
    selection = load_model(selection_path, Selection)
    url = urlsplit(review_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.username
        or url.password
    ):
        raise InputError("review URL must be an uncredentialed loopback HTTP address")
    output = output.expanduser().resolve()
    if output.is_relative_to(project.root.resolve()):
        raise InputError("review packets and source geometry must stay outside the code repository")
    footprint_snapshot, footprint_payload = verify_snapshot(footprint_manifest)
    zone_snapshot, zone_payload = verify_snapshot(zone_manifest)
    if any(s.spec.country != selection.country for s in (footprint_snapshot, zone_snapshot)):
        raise InputError("selection and source country scopes differ")
    for definition in selection.sites:
        if definition.site_type not in project.settings.primary_indicators:
            raise InputError("candidate site type is not configured")
    if any(s.spec.connector != "osm" for s in (footprint_snapshot, zone_snapshot)):
        raise InputError("source-geometry packets require OSM footprint and zone inputs")
    footprints = _records(footprint_snapshot, footprint_payload)
    zone_records = [
        record
        for record in _records(zone_snapshot, zone_payload).values()
        if record.geometry is not None and record.kind in {"zone", "mask"}
    ]
    external_ids = {record.external_id for record in zone_records}
    for candidate in selection.sites:
        external_ids.update([candidate.source_record, *candidate.identity_records])
    by_record = _proposal_index(Store(project.workspace), external_ids)
    candidates = []
    for selected in selection.sites:
        footprint = footprints.get(selected.source_record)
        if footprint is None or footprint.geometry is None:
            raise InputError("a selected site lacks a usable source polygon")
        if footprint.kind != "site":
            raise InputError("selected footprint is a zone or mask rather than a site source")
        geometry = TypeAdapter[Any](cast(Any, Geometry)).validate_python(footprint.geometry)
        anchor = anchor_of(geometry)
        area = shape_on_anchor(geometry, anchor)
        zones = []
        for record in zone_records:
            other = _shape(record, anchor)
            if not area.intersects(other) or area.intersection(other).area == 0:
                continue
            attributes = record.attributes
            hint = (
                "water_mask"
                if record.kind == "mask"
                else "apron"
                if attributes.get("aeroway") == "apron"
                else "pier"
                if attributes.get("man_made") == "pier"
                else "parking_candidate"
            )
            evidence = _evidence(by_record.get(record.external_id, []), record, zone_snapshot)
            zones.append(
                {
                    "source_record": record.external_id,
                    "hint": hint,
                    "contained": bool(area.covers(other)),
                    "geometry": record.geometry,
                    "attributes": attributes,
                    "proposal_ids": sorted({entry["proposal_id"] for entry in evidence}),
                    "evidence": evidence,
                }
            )
        footprint_evidence = _evidence(
            by_record.get(selected.source_record, []), footprint, footprint_snapshot
        )
        footprint_proposals = sorted({entry["proposal_id"] for entry in footprint_evidence})
        if not footprint_proposals:
            raise InputError(
                "selected source footprint must be active and staged in the review queue"
            )
        conflicts = [zone["source_record"] for zone in zones if not zone["contained"]]
        unstaged = [zone["source_record"] for zone in zones if not zone["evidence"]]
        primary_zone_types = sorted(
            {
                zone_type
                for indicator in project.settings.primary_indicators[selected.site_type]
                for zone_type in project.settings.indicators[indicator].zones
                if zone_type != "all"
            }
        )
        compatible = any(zone["contained"] and zone["hint"] in primary_zone_types for zone in zones)
        candidates.append(
            {
                **selected.model_dump(mode="json"),
                "geometry": footprint.geometry,
                "source_attributes": footprint.attributes,
                "primary_zone_types": primary_zone_types,
                "compatible_source_zone": compatible,
                "zones": zones,
                "proposal_ids": footprint_proposals,
                "footprint_evidence": footprint_evidence,
                "crossing_source_records": conflicts,
                "unstaged_source_records": unstaged,
                "identity_proposals": {
                    key: [
                        proposal["id"]
                        for proposal in by_record.get(key, [])
                        if proposal["content"]["record"]["kind"] == "site"
                        and proposal["content"]["record"]["country"] == selection.country
                    ]
                    for key in selected.identity_records
                },
                "missing": [
                    "owner_identity_and_location_review",
                    "owner_geometry_and_zone_review",
                    "sourced_status_and_claim_dates",
                    "dated_unit_and_equipment_links",
                ]
                + ([] if compatible else ["compatible_monitoring_zone_geometry_or_role"])
                + (["crossing_source_geometry"] if conflicts else [])
                + (["unstaged_zone_or_mask_evidence"] if unstaged else []),
            }
        )
    packet = {
        "schema_version": 2,
        "approved": False,
        "selection": selection.model_dump(mode="json"),
        "candidates": candidates,
        "sources": [
            footprint_snapshot.model_dump(mode="json"),
            zone_snapshot.model_dump(mode="json"),
        ],
        "review_url": review_url,
        "notice": "Unapproved source geometry and tentative classifications. "
        "Mapped features are not a complete base inventory or proof of current deployments.",
    }
    from allyourbase.catalogue.approvals import OWNER_REVIEW_GAPS, approval_for_packet, review_id

    packet["review_id"] = review_id(packet)
    packet["owner_approval"] = approval_for_packet(project, packet)
    owner_approved = packet["owner_approval"] is not None
    if owner_approved:
        for item in candidates:
            item["missing"] = [gap for gap in item["missing"] if gap not in OWNER_REVIEW_GAPS]
        packet["notice"] = (
            "Owner approval of the displayed proposals is recorded. "
            "Catalogue acceptance still requires validated geometry and dated source evidence."
        )
    gap_counts: dict[str, int] = {}
    gaps = []
    for item in candidates:
        for gap in item["missing"]:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1
        gaps.append(
            {
                "candidate_id": item["id"],
                "name": item["name"],
                "missing": item["missing"],
                "crossing_source_records": item["crossing_source_records"],
                "unstaged_source_records": item["unstaged_source_records"],
                "identity_proposals": item["identity_proposals"],
                "footprint_evidence": item["footprint_evidence"],
            }
        )
    gap_report = {
        "schema_version": 1,
        "approved": False,
        "candidate_sites": len(candidates),
        "owner_approval": packet["owner_approval"],
        "gap_counts": dict(sorted(gap_counts.items())),
        "candidates": gaps,
        "notice": "Review worklist only; this report makes no catalogue decisions.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "review-gaps.json").write_text(
        json.dumps(gap_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    gap_labels = {
        "owner_identity_and_location_review": "identity/location review",
        "owner_geometry_and_zone_review": "boundary/zone review",
        "sourced_status_and_claim_dates": "dated status evidence",
        "dated_unit_and_equipment_links": "dated historical unit/equipment evidence",
        "compatible_monitoring_zone_geometry_or_role": "compatible zone geometry/role",
        "crossing_source_geometry": "crossing polygons",
        "unstaged_zone_or_mask_evidence": "unlinked source evidence",
    }
    lines = [
        "# Mixed Russian pilot review packet",
        "",
        selection.scope,
        "",
        (
            f"Owner approval is recorded for all {len(candidates)} displayed proposals. "
            "Production acceptance remains pending."
            if owner_approved
            else f"All {len(candidates)} candidates and their zones await owner approval. "
            "The production catalogue is unchanged."
        ),
        "",
        (
            "| Candidate | Proposed type | Source footprint | "
            "Contained zone/mask polygons | Boundary conflicts | Review gaps |"
        ),
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        contained = sum(z["contained"] for z in item["zones"])
        lines.append(
            f"| {item['name']} | {item['site_type']} | "
            f"[{item['source_record']}](https://www.openstreetmap.org/{item['source_record']}) | "
            f"{contained} | {len(item['crossing_source_records'])} | "
            + ", ".join(gap_labels[gap] for gap in item["missing"])
            + " |"
        )
    lines += [
        "",
        (
            "The geometry preview and source notes are in preview.html; "
            "exact hashes and proposal IDs are in packet.json; "
            "per-candidate gaps are in review-gaps.json."
        ),
        "",
        (
            "No source-centre point was converted to a polygon. Zones crossing a footprint "
            "are retained as conflicts, not clipped or silently accepted."
        ),
        "",
        (
            "Parking tags do not establish military vehicle use. Estimated boundaries "
            "and unnamed parcels require additional review."
        ),
    ]
    (output / "review-packet.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    template = Path(__file__).with_name("packet.html").read_text(encoding="utf-8")
    encoded = json.dumps(packet, ensure_ascii=False).replace("<", r"\u003c").replace("&", r"\u0026")
    (output / "preview.html").write_text(
        template.replace("PACKET_SCOPE", html.escape(selection.scope)).replace(
            "PACKET_DATA", encoded
        ),
        encoding="utf-8",
    )
    features = []
    for item in candidates:
        features.append(
            {
                "type": "Feature",
                "geometry": item["geometry"],
                "properties": {
                    "candidate_id": item["id"],
                    "source_record": item["source_record"],
                    "role": "source_footprint",
                    "owner_approved": owner_approved,
                    "approved": False,
                },
            }
        )
        features.extend(
            {
                "type": "Feature",
                "geometry": zone["geometry"],
                "properties": {
                    "candidate_id": item["id"],
                    "source_record": zone["source_record"],
                    "role": zone["hint"],
                    "contained": zone["contained"],
                    "owner_approved": owner_approved,
                    "approved": False,
                },
            }
            for zone in item["zones"]
        )
    (output / "source-polygons.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    return {
        "candidate_sites": len(candidates),
        "source_polygons": len(candidates),
        "zone_or_mask_associations": sum(len(item["zones"]) for item in candidates),
        "contained_associations": sum(z["contained"] for item in candidates for z in item["zones"]),
        "boundary_conflicts": sum(len(item["crossing_source_records"]) for item in candidates),
        "unstaged_associations": sum(len(item["unstaged_source_records"]) for item in candidates),
        "gap_counts": gap_report["gap_counts"],
        "owner_approved": owner_approved,
        "approved": False,
        "output": str(output),
    }
