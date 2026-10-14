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
from allyourbase.sources.contracts import Record
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
    footprints = {r.external_id: r for r in parse_records(footprint_snapshot, footprint_payload)}
    zone_records = [r for r in parse_records(zone_snapshot, zone_payload) if r.geometry is not None]
    proposals = Store(project.workspace).proposals()
    by_record: dict[str, list[str]] = {}
    for proposal in proposals:
        record = proposal["content"].get("record")
        if record:
            by_record.setdefault(record["external_id"], []).append(proposal["id"])
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
            zones.append(
                {
                    "source_record": record.external_id,
                    "hint": hint,
                    "contained": bool(area.covers(other)),
                    "geometry": record.geometry,
                    "attributes": attributes,
                    "proposal_ids": by_record.get(record.external_id, []),
                }
            )
        footprint_proposals = []
        for proposal_id in by_record.get(selected.source_record, []):
            proposal = Store(project.workspace).proposal(proposal_id)
            if any(e["manifest"]["id"] == footprint_snapshot.id for e in proposal["evidence"]):
                footprint_proposals.append(proposal_id)
        if not footprint_proposals:
            raise InputError("selected source footprint must be staged in the review queue")
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
                "identity_proposals": {
                    key: by_record.get(key, []) for key in selected.identity_records
                },
                "missing": [
                    "owner_geometry_and_zone_review",
                    "sourced_status_and_claim_dates",
                    "dated_unit_and_equipment_links",
                ]
                + ([] if compatible else ["compatible_monitoring_zone_geometry_or_role"]),
            }
        )
    packet = {
        "schema_version": 1,
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
    output.mkdir(parents=True, exist_ok=True)
    (output / "packet.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Mixed Russian pilot review packet",
        "",
        selection.scope,
        "",
        (
            f"All {len(candidates)} candidates and their zones remain unapproved. "
            "The production catalogue is unchanged."
        ),
        "",
        (
            "| Candidate | Proposed type | Source footprint | "
            "Contained zone/mask polygons | Review gaps |"
        ),
        "| --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        contained = sum(z["contained"] for z in item["zones"])
        lines.append(
            f"| {item['name']} | {item['site_type']} | "
            f"[{item['source_record']}](https://www.openstreetmap.org/{item['source_record']}) | "
            f"{contained} | geometry, classification, status/dates, unit/equipment links |"
        )
    lines += [
        "",
        (
            "The geometry preview and source notes are in preview.html; "
            "exact hashes and proposal IDs are in packet.json."
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
        "approved": False,
        "output": str(output),
    }
