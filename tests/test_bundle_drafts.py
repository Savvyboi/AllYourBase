import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_catalogue_packet import polygon, setup_packet
from typer.testing import CliRunner

from allyourbase.catalogue.approvals import record_packet_approval
from allyourbase.catalogue.bundle_drafts import prepare_bundles
from allyourbase.catalogue.geometry_drafts import build_geometry_drafts
from allyourbase.catalogue.packet import build_packet
from allyourbase.catalogue.review import ReviewBundle
from allyourbase.cli import app
from allyourbase.loading import InputError
from allyourbase.models.catalogue import Zone, validate_zone_containment
from allyourbase.models.geometry import Polygon
from allyourbase.project import Project
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.snapshots import verify_snapshot
from allyourbase.sources.store import Store


def approved_packet(project: Path, tmp_path: Path, spec: SourceSpec) -> tuple[Project, Path]:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    build_packet(
        configured, selection, footprints, zones, tmp_path / "packet", "http://127.0.0.1:8768"
    )
    packet = tmp_path / "packet/packet.json"
    record_packet_approval(configured, packet, "owner", "Approve fictional test geometry")
    return configured, packet


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_drafts_keep_exact_geometry_evidence_and_omit_unsupported_facts(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, packet = approved_packet(project, tmp_path, spec)
    store = Store(configured.workspace)
    proposals = store.proposals()
    catalogue = {p: p.read_bytes() for p in (project / "catalogue").rglob("*") if p.is_file()}
    source_bytes = packet.read_bytes()
    output = tmp_path / "drafts"
    result = prepare_bundles(configured, packet, output)
    assert result["geometry_ready_sites"] == 1 and result["prepared_zones"] == 1
    assert result["contract_valid_bundles"] == 0
    assert result["production_accepted"] is False and result["milestone_ready"] is False
    report = read_json(output / "bundle-drafts.json")
    candidate = report["candidates"][0]
    draft = read_json(output / candidate["bundle_path"])
    props = draft["sites"][0]["properties"]
    assert {error["path"] for error in candidate["validation_errors"]} == {
        "sites/0/properties/status",
        "sites/0/properties/as_of",
        "sites/0/properties/sensors",
    }
    assert not ({"status", "as_of", "sensors", "wikidata"} & props.keys())
    assert draft["units"] == draft["equipment"] == []
    assert "dated_unit_and_equipment_links" in candidate["missing"]
    assert "processing_sensor_choice" in candidate["missing"]
    provenance = read_json(output / candidate["provenance_path"])
    geometry = build_geometry_drafts(configured, packet)
    assert props["zones"] == [z["zone"] for z in geometry["candidates"][0]["zones"]]
    assert draft["sites"][0]["geometry"] == geometry["candidates"][0]["geometry"]
    assert candidate["primary_proposal"] not in draft["evidence_proposals"]
    assert {e["proposal_id"] for e in provenance["evidence"]} == {
        candidate["primary_proposal"],
        *draft["evidence_proposals"],
    }
    assert all(
        e["snapshot_id"] in {s["id"] for s in provenance["sources"]} for e in provenance["evidence"]
    )
    for name, digest in report["file_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    with pytest.raises(ValidationError):
        ReviewBundle.model_validate(draft)
    # Synthetic completion demonstrates the draft uses the existing bundle shape.
    props.update(status="active", as_of="2020-01-01", sensors="both")
    ReviewBundle.model_validate(draft)
    assert store.proposals() == proposals and not store.proposals("accepted")
    assert packet.read_bytes() == source_bytes
    assert all(p.read_bytes() == data for p, data in catalogue.items())


def test_no_compatible_zones_remains_an_incomplete_draft(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, packet = approved_packet(project, tmp_path, spec)
    content = read_json(packet)
    content["selection"]["sites"][0]["site_type"] = "naval_base"
    selection = tmp_path / "garrison-selection.json"
    selection.write_text(json.dumps(content["selection"]), encoding="utf-8")
    manifests = [
        configured.workspace / "sources" / s["spec"]["source"]["id"] / s["id"] / "manifest.json"
        for s in content["sources"]
    ]
    build_packet(
        configured,
        selection,
        manifests[0],
        manifests[1],
        tmp_path / "garrison-packet",
        "http://localhost:8768",
    )
    packet = tmp_path / "garrison-packet/packet.json"
    record_packet_approval(configured, packet, "owner", "Approve fictional garrison geometry")
    output = tmp_path / "drafts"
    result = prepare_bundles(configured, packet, output)
    assert result["geometry_ready_sites"] == result["prepared_zones"] == 0
    candidate = read_json(output / "bundle-drafts.json")["candidates"][0]
    assert "compatible_monitoring_zone_geometry_or_role" in candidate["missing"]
    assert any(e["path"] == "sites/0/properties/zones" for e in candidate["validation_errors"])
    assert read_json(output / candidate["bundle_path"])["sites"][0]["properties"]["zones"] == []


def test_regeneration_preserves_review_edits_before_any_writes(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, packet = approved_packet(project, tmp_path, spec)
    output = tmp_path / "drafts"
    prepare_bundles(configured, packet, output)
    original = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
    prepare_bundles(configured, packet, output)
    assert all(p.read_bytes() == data for p, data in original.items())
    edited = output / "rus-synthetic/bundle-draft.json"
    edited.write_text("Human review edit\n", encoding="utf-8")
    sidecar = output / "rus-synthetic/provenance.json"
    sidecar.unlink()
    with pytest.raises(InputError, match="preserve review edits"):
        prepare_bundles(configured, packet, output)
    assert edited.read_text() == "Human review edit\n"
    assert not sidecar.exists()


@pytest.mark.parametrize("state", ["rejected", "corrupt_source", "forged_packet", "unapproved"])
def test_unusable_evidence_never_writes_drafts(
    project: Path, tmp_path: Path, spec: SourceSpec, state: str
) -> None:
    configured, packet = approved_packet(project, tmp_path, spec)
    content = read_json(packet)
    if state == "rejected":
        Store(configured.workspace).decide(
            content["candidates"][0]["zones"][0]["proposal_ids"][0],
            "rejected",
            "owner",
            "Withdraw fixture",
        )
    elif state == "corrupt_source":
        source = content["sources"][0]
        manifest = (
            configured.workspace
            / "sources"
            / source["spec"]["source"]["id"]
            / source["id"]
            / "manifest.json"
        )
        _, payload = verify_snapshot(manifest)
        payload.write_bytes(b"changed source")
    else:
        content["candidates"][0]["geometry"] = polygon(0, 0, 3, 3)
        packet.write_text(json.dumps(content), encoding="utf-8")
        if state == "forged_packet":
            record_packet_approval(configured, packet, "owner", "Approve forged fixture")
    output = tmp_path / "drafts"
    with pytest.raises(InputError):
        prepare_bundles(configured, packet, output)
    assert not output.exists()


def test_cli_output_and_external_boundaries(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, packet = approved_packet(project, tmp_path, spec)
    for output in [project / "drafts", packet.parent, tmp_path]:
        with pytest.raises(InputError, match="outside|overwrite"):
            prepare_bundles(configured, packet, output)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(project),
            "catalogue",
            "prepare-bundles",
            str(packet),
            str(tmp_path / "drafts"),
        ],
        env={"ALLYOURBASE_HOME": str(configured.workspace)},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["contract_valid_bundles"] == 0


@pytest.mark.parametrize("kind", ["outside_zone", "inside_aoi_hole", "mask_in_zone_hole"])
def test_geometry_validation_does_not_require_dummy_status_or_dates(kind: str) -> None:
    footprint = polygon(179, 0, -179, 2)
    zone: dict[str, Any] = {
        "id": "synthetic",
        "zone_type": "apron",
        "sources": ["test"],
        "geometry": polygon(179.2, 0.2, -179.2, 1.8),
    }
    if kind == "outside_zone":
        zone["water_mask"] = polygon(179.1, 0.5, 179.3, 1)
    elif kind == "inside_aoi_hole":
        footprint["coordinates"].append(polygon(179.5, 0.5, -179.5, 1.5)["coordinates"][0])
        zone["geometry"] = polygon(179.6, 0.6, -179.6, 1.4)
    else:
        zone["geometry"]["coordinates"].append(polygon(179.5, 0.5, -179.5, 1.5)["coordinates"][0])
        zone["water_mask"] = polygon(179.6, 0.6, -179.6, 1.4)
    with pytest.raises(ValueError, match="beyond"):
        validate_zone_containment(Polygon.model_validate(footprint), [Zone.model_validate(zone)])
