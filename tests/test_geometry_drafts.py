import copy
import json
from pathlib import Path
from typing import Any

import pytest
from test_catalogue_packet import polygon, setup_packet
from typer.testing import CliRunner

from allyourbase.catalogue.approvals import record_packet_approval
from allyourbase.catalogue.geometry_drafts import draft_candidate, prepare_geometry
from allyourbase.catalogue.packet import build_packet
from allyourbase.cli import app
from allyourbase.loading import InputError
from allyourbase.models.catalogue import SiteFeature
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.store import Store


def candidate() -> dict[str, Any]:
    return {
        "id": "rus-synthetic",
        "source_record": "way/1",
        "name": "Synthetic test",
        "site_type": "airbase",
        "geometry": polygon(0, 0, 2, 2),
        "footprint_evidence": [],
        "primary_zone_types": ["apron"],
        "zones": [],
    }


def record(identifier: int, hint: str, geometry: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_record": f"way/{identifier}",
        "hint": hint,
        "geometry": geometry,
        "evidence": [{"source_id": "synthetic-source"}],
    }


def validate_site(draft: dict[str, Any]) -> SiteFeature:
    return SiteFeature.model_validate(
        {
            "type": "Feature",
            "geometry": draft["geometry"],
            "properties": {
                "id": "rus-synthetic",
                "name": "Fictional",
                "country": "RUS",
                "site_type": "airbase",
                "status": "active",
                "as_of": "2020-01-01",
                "sources": ["synthetic-source"],
                "sensors": "both",
                "zones": [z["zone"] for z in draft["zones"]],
            },
        }
    )


def test_masks_clip_to_zone_and_retain_derivations() -> None:
    c = candidate()
    c["zones"] = [
        record(2, "apron", polygon(0.2, 0.2, 0.8, 0.8)),
        record(3, "water_mask", polygon(0.5, 0.5, 3, 3)),
        record(4, "water_mask", polygon(0.8, 0.2, 1, 0.8)),  # boundary touch only
        record(5, "parking_candidate", polygon(0.1, 0.1, 0.2, 0.2)),
    ]
    c["notes"] = ["Synthetic boundary caveat"]
    c["source_attributes"] = {"note": "Estimated fictional outline"}
    original = copy.deepcopy(c)
    draft = draft_candidate(c)
    assert draft["notes"] == c["notes"]
    assert draft["source_attributes"] == c["source_attributes"]
    site = validate_site(draft)
    assert draft["geometry_ready"] is True
    assert site.properties.zones[0].water_mask is not None
    assert len(draft["zones"][0]["mask_operations"]) == 1
    assert draft["zones"][0]["mask_operations"][0]["source_record"] == "way/3"
    assert draft["zones"][0]["zone"]["geometry"] == c["zones"][0]["geometry"]
    assert {d["source_record"]: d["reason"] for d in draft["deferred_source_records"]} == {
        "way/4": "no_positive_area_overlap_with_selected_zones",
        "way/5": "unsupported_monitoring_role",
    }
    assert c == original


def test_masks_preserve_holes_and_disjoint_components() -> None:
    c = candidate()
    water = polygon(0.3, 0.3, 0.7, 0.7)
    water["coordinates"].append(polygon(0.4, 0.4, 0.5, 0.5)["coordinates"][0])
    c["zones"] = [
        record(2, "apron", polygon(0.2, 0.2, 1.8, 1.8)),
        record(3, "water_mask", water),
        record(4, "water_mask", polygon(1.2, 1.2, 1.5, 1.5)),
    ]
    draft = draft_candidate(c)
    site = validate_site(draft)
    mask = site.properties.zones[0].water_mask
    assert mask is not None and mask.type == "MultiPolygon"
    assert sorted(map(len, mask.coordinates)) == [1, 2]


def test_antimeridian_mask_roundtrip_is_contained() -> None:
    c = candidate()
    c["geometry"] = polygon(179, 0, -179, 2)
    c["zones"] = [
        record(2, "apron", polygon(179.5, 0.2, -179.5, 1.8)),
        record(3, "water_mask", polygon(179.75, 0.5, -178, 1.5)),
    ]
    draft = draft_candidate(c)
    assert draft["geometry_ready"] is True
    validate_site(draft)


def test_crossing_zone_and_parking_are_deferred_without_role_invention() -> None:
    c = candidate()
    c["zones"] = [
        record(2, "apron", polygon(1, 1, 3, 3)),
        record(3, "parking_candidate", polygon(0.2, 0.2, 0.8, 0.8)),
        record(4, "water_mask", polygon(1, 1, 3, 3)),
    ]
    draft = draft_candidate(c)
    assert draft["geometry_ready"] is False and not draft["zones"]
    assert "compatible_monitoring_zone_geometry_or_role" in draft["missing"]
    assert {d["reason"] for d in draft["deferred_source_records"]} == {
        "monitoring_zone_crosses_footprint",
        "unsupported_monitoring_role",
        "no_positive_area_overlap_with_selected_zones",
    }


def test_unstaged_water_is_a_visible_evidence_gap() -> None:
    c = candidate()
    mask = record(3, "water_mask", polygon(0.3, 0.3, 0.5, 0.5))
    mask["evidence"] = []
    c["zones"] = [record(2, "apron", polygon(0.2, 0.2, 0.8, 0.8)), mask]
    draft = draft_candidate(c)
    assert not draft["geometry_ready"]
    assert "unstaged_zone_or_mask_evidence" in draft["missing"]


def test_preparation_checks_approval_sources_queue_and_preserves_inputs(
    project: Path,
    tmp_path: Path,
    spec: SourceSpec,
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    packet_dir = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, packet_dir, "http://127.0.0.1:8768")
    packet_path = packet_dir / "packet.json"
    output = tmp_path / "prepared"
    with pytest.raises(InputError, match="owner approval"):
        prepare_geometry(configured, packet_path, output)
    assert not output.exists()
    record_packet_approval(configured, packet_path, "owner", "Approve synthetic packet")
    before = packet_path.read_bytes()
    catalogue = {p: p.read_bytes() for p in (project / "catalogue").rglob("*") if p.is_file()}
    result = prepare_geometry(configured, packet_path, output)
    assert result["geometry_ready_sites"] == 1 and result["prepared_zones"] == 1
    assert result["production_accepted"] is False
    drafts = json.loads((output / "geometry-drafts.json").read_text(encoding="utf-8"))
    assert drafts["owner_approval"]["production_accepted"] is False
    assert all(p.read_bytes() == data for p, data in catalogue.items())
    assert packet_path.read_bytes() == before
    assert not Store(configured.workspace).proposals("accepted")
    original_output = {p: p.read_bytes() for p in output.iterdir()}
    prepare_geometry(configured, packet_path, output)
    assert all(p.read_bytes() == data for p, data in original_output.items())
    rejected = json.loads(before)["candidates"][0]["zones"][0]["proposal_ids"][0]
    Store(configured.workspace).decide(rejected, "rejected", "owner", "Withdraw source")
    with pytest.raises(InputError, match="eligible evidence"):
        prepare_geometry(configured, packet_path, tmp_path / "after-rejection")


def test_even_approved_forged_packet_fails_source_reconstruction(
    project: Path,
    tmp_path: Path,
    spec: SourceSpec,
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    packet_dir = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, packet_dir, "http://127.0.0.1:8768")
    packet_path = packet_dir / "packet.json"
    packet = json.loads(packet_path.read_text())
    packet["candidates"][0]["zones"][0]["geometry"] = polygon(0.1, 0.1, 0.9, 0.9)
    packet_path.write_text(json.dumps(packet))
    record_packet_approval(configured, packet_path, "owner", "Approve manually altered packet")
    with pytest.raises(InputError, match="retained source"):
        prepare_geometry(configured, packet_path, tmp_path / "prepared")


def test_cli_and_output_boundaries(project: Path, tmp_path: Path, spec: SourceSpec) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    packet_dir = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, packet_dir, "http://127.0.0.1:8768")
    packet_path = packet_dir / "packet.json"
    record_packet_approval(configured, packet_path, "owner", "Approve synthetic packet")
    for bad in [project / "drafts", packet_dir, tmp_path]:
        with pytest.raises(InputError, match="outside|overwrite"):
            prepare_geometry(configured, packet_path, bad)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(project),
            "catalogue",
            "prepare-geometry",
            str(packet_path),
            str(tmp_path / "prepared"),
        ],
        env={"ALLYOURBASE_HOME": str(configured.workspace)},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["prepared_zones"] == 1
