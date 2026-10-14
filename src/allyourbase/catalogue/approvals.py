"""Retain an owner's approval of displayed proposals separately from catalogue acceptance."""

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from allyourbase.loading import InputError, load_model
from allyourbase.models.common import Contract, NonEmpty, Slug
from allyourbase.project import Project
from allyourbase.sources.contracts import Digest, Snapshot
from allyourbase.sources.snapshots import canonical, verify_snapshot
from allyourbase.sources.store import workflow_lock

OWNER_REVIEW_GAPS = {"owner_identity_and_location_review", "owner_geometry_and_zone_review"}


class PacketApproval(Contract):
    schema_version: Literal[1] = 1
    review_id: Digest
    packet_sha256: Digest
    reviewer: NonEmpty
    note: NonEmpty
    approved_at: AwareDatetime
    candidate_ids: list[Slug] = Field(min_length=1)
    scope: Literal["displayed_candidate_identity_and_source_geometry"] = (
        "displayed_candidate_identity_and_source_geometry"
    )
    production_accepted: Literal[False] = False


def review_id(packet: dict[str, Any]) -> str:
    """Bind approval to displayed content and source versions, independent of UI addresses."""
    from allyourbase.catalogue.packet import Selection

    if packet.get("schema_version") != 2 or packet.get("approved") is not False:
        raise InputError("approval requires a version 2 proposal packet")
    selection = Selection.model_validate(packet["selection"])
    candidates = deepcopy(packet["candidates"])
    if [item["id"] for item in candidates] != [item.id for item in selection.sites]:
        raise InputError("packet candidates differ from the retained selection")
    if len(packet["sources"]) != 2:
        raise InputError("packet needs both retained source snapshots")
    for item, selected in zip(candidates, selection.sites, strict=True):
        if (
            item["source_record"] != selected.source_record
            or item["site_type"] != selected.site_type
        ):
            raise InputError("candidate source or classification differs from the selection")
        item.pop("missing", None)
        for evidence in item["footprint_evidence"]:
            evidence.pop("state", None)
        for zone in item["zones"]:
            for evidence in zone["evidence"]:
                evidence.pop("state", None)
    content = {
        "selection": packet["selection"],
        "candidates": candidates,
        "sources": packet["sources"],
    }
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def _verify_sources(project: Project, packet: dict[str, Any]) -> None:
    for raw in packet["sources"]:
        pinned = Snapshot.model_validate(raw)
        retained, _ = verify_snapshot(
            project.workspace / "sources" / pinned.spec.source.id / pinned.id / "manifest.json"
        )
        if retained != pinned:
            raise InputError("approval source snapshot differs from the displayed packet")


def approval_for_packet(project: Project, packet: dict[str, Any]) -> dict[str, Any] | None:
    identifier = review_id(packet)
    directory = project.workspace / "review/packet-approvals" / identifier
    if not directory.exists():
        return None
    approval = load_model(directory / "approval.json", PacketApproval)
    archive = (directory / "packet.json").read_bytes()
    retained = json.loads(archive)
    if (
        approval.review_id != identifier
        or hashlib.sha256(archive).hexdigest() != approval.packet_sha256
        or review_id(retained) != identifier
        or approval.candidate_ids != [item["id"] for item in packet["candidates"]]
    ):
        raise InputError("retained packet approval or archive changed")
    _verify_sources(project, retained)
    return approval.model_dump(mode="json")


def record_packet_approval(
    project: Project, packet_path: Path, reviewer: str, note: str
) -> dict[str, Any]:
    path = packet_path.expanduser().resolve()
    if path.is_relative_to(project.root.resolve()):
        raise InputError("proposal packets and approval archives must stay outside the repository")
    if not reviewer.strip() or not note.strip():
        raise InputError("reviewer and explicit approval note are required")
    archive = path.read_bytes()
    packet = json.loads(archive)
    identifier = review_id(packet)
    _verify_sources(project, packet)
    approval = PacketApproval(
        review_id=identifier,
        packet_sha256=hashlib.sha256(archive).hexdigest(),
        reviewer=reviewer,
        note=note,
        approved_at=datetime.now(UTC),
        candidate_ids=[item["id"] for item in packet["candidates"]],
    )
    with workflow_lock(project.workspace):
        existing = approval_for_packet(project, packet)
        if existing is not None:
            return {"approval": existing, "created": False}
        parent = project.workspace / "review/packet-approvals"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            staging = Path(temporary) / "approval"
            staging.mkdir()
            for name, content in (
                ("packet.json", archive),
                ("approval.json", (approval.model_dump_json(indent=2) + "\n").encode("utf-8")),
            ):
                with (staging / name).open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            staging.rename(parent / identifier)
    return {"approval": approval.model_dump(mode="json"), "created": True}
