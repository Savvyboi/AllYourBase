import json
from pathlib import Path

import pytest
from test_catalogue_packet import polygon, setup_packet
from typer.testing import CliRunner

from allyourbase.catalogue.approvals import approval_for_packet, record_packet_approval, review_id
from allyourbase.catalogue.packet import build_packet
from allyourbase.cli import app
from allyourbase.loading import InputError
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.store import Store


def test_approval_is_durable_idempotent_and_does_not_accept_catalogue(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    path = output / "packet.json"
    before = Store(configured.workspace).proposals()
    original_catalogue = {
        p: p.read_bytes() for p in (project / "catalogue").rglob("*") if p.is_file()
    }
    result = record_packet_approval(configured, path, "owner", "Approve the displayed proposals")
    repeat = record_packet_approval(configured, path, "owner", "Same approval repeated")
    assert result["created"] is True and repeat["created"] is False
    assert result["approval"] == repeat["approval"]
    assert result["approval"]["production_accepted"] is False
    rebuilt = build_packet(
        configured, selection, footprints, zones, output, "http://127.0.0.1:8770"
    )
    packet = json.loads(path.read_text())
    assert rebuilt["owner_approved"] is True and rebuilt["approved"] is False
    assert approval_for_packet(configured, packet) == result["approval"]
    assert not any(gap.startswith("owner_") for gap in packet["candidates"][0]["missing"])
    assert "crossing_source_geometry" in packet["candidates"][0]["missing"]
    assert "sourced_status_and_claim_dates" in packet["candidates"][0]["missing"]
    assert "dated_unit_and_equipment_links" in packet["candidates"][0]["missing"]
    assert Store(configured.workspace).proposals() == before
    assert all(p.read_bytes() == data for p, data in original_catalogue.items())
    assert "Owner approval is recorded" in (output / "review-packet.md").read_text()


@pytest.mark.parametrize("change", ["geometry", "role", "identity", "source"])
def test_approval_never_carries_to_changed_displayed_content(
    project: Path, tmp_path: Path, spec: SourceSpec, change: str
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    record_packet_approval(configured, output / "packet.json", "owner", "Approve displayed packet")
    packet = json.loads((output / "packet.json").read_text())
    if change == "geometry":
        packet["candidates"][0]["geometry"] = polygon(0, 0, 1, 1)
    elif change == "role":
        packet["candidates"][0]["zones"][0]["hint"] = "parking_candidate"
    elif change == "identity":
        packet["candidates"][0]["name"] = "Another identity"
    else:
        packet["sources"][0]["sha256"] = "0" * 64
    assert approval_for_packet(configured, packet) is None


@pytest.mark.parametrize("change", ["archive", "candidate_ids"])
def test_changed_approval_archive_is_refused(
    project: Path, tmp_path: Path, spec: SourceSpec, change: str
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    packet = json.loads((output / "packet.json").read_text())
    record_packet_approval(configured, output / "packet.json", "owner", "Approve displayed packet")
    directory = configured.workspace / "review/packet-approvals" / review_id(packet)
    if change == "archive":
        (directory / "packet.json").write_text("{}")
    else:
        approval = json.loads((directory / "approval.json").read_text())
        approval["candidate_ids"] = ["rus-another"]
        (directory / "approval.json").write_text(json.dumps(approval))
    with pytest.raises(InputError, match="changed"):
        approval_for_packet(configured, packet)


@pytest.mark.parametrize("reviewer,note", [("", "Approved"), ("owner", " ")])
def test_approval_requires_explicit_reviewer_and_note(
    project: Path, tmp_path: Path, spec: SourceSpec, reviewer: str, note: str
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    with pytest.raises(InputError, match="reviewer"):
        record_packet_approval(configured, output / "packet.json", reviewer, note)
    assert not (configured.workspace / "review/packet-approvals").exists()


def test_approval_checks_retained_sources(project: Path, tmp_path: Path, spec: SourceSpec) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    (footprints.parent / "payload").write_text("tampered")
    with pytest.raises(InputError, match="hash or size"):
        record_packet_approval(
            configured, output / "packet.json", "owner", "Approve displayed packet"
        )
    assert not (configured.workspace / "review/packet-approvals").exists()


def test_approve_packet_cli_records_owner_decision(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(project),
            "catalogue",
            "approve-packet",
            str(output / "packet.json"),
            "--reviewer",
            "owner",
            "--note",
            "Approved displayed proposals",
        ],
        env={"ALLYOURBASE_HOME": str(configured.workspace)},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["approval"]["candidate_ids"] == ["rus-synthetic"]
    assert not Store(configured.workspace).proposals("accepted")
