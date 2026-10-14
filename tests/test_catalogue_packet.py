import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from allyourbase.catalogue.packet import Selection, build_packet
from allyourbase.loading import InputError
from allyourbase.project import Project
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.matching import MatchSettings
from allyourbase.sources.snapshots import save_snapshot
from allyourbase.sources.store import Store


def polygon(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def setup_packet(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> tuple[Project, Path, Path, Path]:
    configured = Project.load(project, Path("config/settings.yaml"))
    configured = Project(project, configured.settings, tmp_path / "data")
    store = Store(configured.workspace)
    manifests = []
    for label, features in [
        (
            "footprints",
            [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {"military": "airfield"},
                    "geometry": polygon(0, 0, 2, 2),
                }
            ],
        ),
        (
            "zones",
            [
                {
                    "type": "Feature",
                    "id": f"way/{i}",
                    "properties": {"aeroway": "apron"},
                    "geometry": geometry,
                }
                for i, geometry in enumerate(
                    [polygon(0.2, 0.2, 0.4, 0.4), polygon(1, 1, 3, 3), polygon(4, 4, 5, 5)], 2
                )
            ],
        ),
    ]:
        source = spec.source.model_copy(update={"id": "test-" + label})
        current = spec.model_copy(update={"source": source, "connector": "osm"})
        path = tmp_path / (label + ".geojson")
        path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
        manifest = save_snapshot(configured.workspace, current, path)
        store.stage(manifest, MatchSettings())
        manifests.append(manifest)
    selection = tmp_path / "selection.yaml"
    selection.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "country": "RUS",
                "status": "proposed",
                "scope": "Synthetic test only",
                "requested_on": "2026-10-14",
                "sites": [
                    {
                        "id": "rus-synthetic",
                        "name": "Synthetic source",
                        "site_type": "airbase",
                        "source_record": "way/1",
                    }
                ],
            }
        )
    )
    return configured, selection, manifests[0], manifests[1]


def test_packet_preserves_conflicts_and_never_accepts(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    before = (project / "catalogue/countries/XXX/sites.geojson").read_bytes()
    result = build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    packet = json.loads((output / "packet.json").read_text())
    assert result["candidate_sites"] == 1 and result["contained_associations"] == 1
    assert len(packet["candidates"][0]["zones"]) == 2
    assert [z["contained"] for z in packet["candidates"][0]["zones"]] == [True, False]
    assert result["approved"] is False and packet["approved"] is False
    assert (project / "catalogue/countries/XXX/sites.geojson").read_bytes() == before
    assert not Store(configured.workspace).proposals("accepted")


def test_packet_refuses_output_inside_repository(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    with pytest.raises(InputError, match="outside"):
        build_packet(
            configured, selection, footprints, zones, project / "packet", "http://127.0.0.1:8768"
        )
    assert not (project / "packet").exists()


def test_packet_escapes_source_html(project: Path, tmp_path: Path, spec: SourceSpec) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    data = yaml.safe_load(selection.read_text())
    data["sites"][0]["name"] = "</script><script>throw new Error('unsafe')</script>"
    selection.write_text(yaml.safe_dump(data))
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    assert "</script><script>throw" not in (output / "preview.html").read_text()
    assert r"\u003c/script>" in (output / "preview.html").read_text()


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "https://evil.invalid", "http://owner:secret@127.0.0.1"]
)
def test_packet_link_stays_on_loopback(
    project: Path, tmp_path: Path, spec: SourceSpec, url: str
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    with pytest.raises(InputError, match="loopback"):
        build_packet(configured, selection, footprints, zones, tmp_path / "packet", url)


def test_duplicate_footprint_not_counted_as_two_sites() -> None:
    from pydantic import ValidationError

    data = {
        "schema_version": 1,
        "country": "RUS",
        "status": "proposed",
        "scope": "Synthetic",
        "requested_on": "2026-10-14",
        "sites": [
            {"id": "rus-a", "name": "A", "site_type": "airbase", "source_record": "way/1"},
            {"id": "rus-b", "name": "B", "site_type": "airbase", "source_record": "way/1"},
        ],
    }
    with pytest.raises(ValidationError, match="duplicate footprint"):
        Selection.model_validate(data)


def test_packet_pins_zone_links_to_exact_snapshot(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    from allyourbase.sources.snapshots import verify_snapshot

    snapshot, payload = verify_snapshot(zones)
    other_source = snapshot.spec.source.model_copy(update={"id": "unrelated-source"})
    other_spec = snapshot.spec.model_copy(update={"source": other_source})
    unrelated = save_snapshot(configured.workspace, other_spec, payload)
    store = Store(configured.workspace)
    store.stage(unrelated, MatchSettings())
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    candidate = json.loads((output / "packet.json").read_text())["candidates"][0]
    for zone in candidate["zones"]:
        assert len(zone["proposal_ids"]) == 1
        assert {entry["snapshot_id"] for entry in zone["evidence"]} == {snapshot.id}
        assert {entry["source_id"] for entry in zone["evidence"]} == {snapshot.spec.source.id}
        assert all(entry["locator"] and entry["record_id"] for entry in zone["evidence"])


def test_packet_keeps_active_accepted_supporting_records(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    store = Store(configured.workspace)
    accepted = [
        proposal["id"]
        for proposal in store.proposals()
        if proposal["content"]["record"]["external_id"] in {"way/1", "way/2"}
    ]
    for identifier in accepted:
        # Only fictional source decisions are used; no production acceptance occurs.
        store.decide(identifier, "accepted", "synthetic-reviewer", "Fixture decision")
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    candidate = json.loads((output / "packet.json").read_text())["candidates"][0]
    assert candidate["footprint_evidence"][0]["state"] == "accepted"
    assert candidate["zones"][0]["evidence"][0]["state"] == "accepted"
    assert len(store.proposals("accepted")) == len(accepted)


@pytest.mark.parametrize("state", ["rejected", "superseded", "accepted_superseded"])
def test_packet_flags_unavailable_zone_evidence(
    project: Path, tmp_path: Path, spec: SourceSpec, state: str
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    store = Store(configured.workspace)
    identifier = next(
        proposal["id"]
        for proposal in store.proposals()
        if proposal["content"]["record"]["external_id"] == "way/2"
    )
    if state == "rejected":
        store.decide(identifier, "rejected", "synthetic-reviewer", "Fixture decision")
    else:
        if state == "accepted_superseded":
            store.decide(identifier, "accepted", "synthetic-reviewer", "Old fixture decision")
        from allyourbase.sources.snapshots import verify_snapshot

        snapshot, payload = verify_snapshot(zones)
        data = json.loads(payload.read_text())
        data["features"][0]["properties"]["name"] = "Changed source version"
        changed = tmp_path / "changed.geojson"
        changed.write_text(json.dumps(data))
        store.stage(save_snapshot(configured.workspace, snapshot.spec, changed), MatchSettings())
    output = tmp_path / "packet"
    result = build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    candidate = json.loads((output / "packet.json").read_text())["candidates"][0]
    assert candidate["zones"][0]["proposal_ids"] == []
    assert candidate["zones"][0]["evidence"] == []
    assert candidate["unstaged_source_records"] == ["way/2"]
    assert result["unstaged_associations"] == 1
    assert "unstaged_zone_or_mask_evidence" in candidate["missing"]


def test_packet_gap_report_is_repeatable_and_read_only(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    output = tmp_path / "packet"
    store = Store(configured.workspace)
    before = store.proposals()
    result = build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    report = (output / "review-gaps.json").read_bytes()
    gaps = json.loads(report)
    assert gaps["approved"] is False
    assert gaps["gap_counts"]["crossing_source_geometry"] == 1
    assert gaps["candidates"][0]["crossing_source_records"] == ["way/3"]
    assert result["boundary_conflicts"] == 1
    build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    assert (output / "review-gaps.json").read_bytes() == report
    assert store.proposals() == before
    assert not store.proposals("accepted")


def test_packet_honors_zone_record_selectors(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    from allyourbase.sources.snapshots import verify_snapshot

    snapshot, payload = verify_snapshot(zones)
    selected_spec = snapshot.spec.model_copy(update={"record_ids": ["way/3"]})
    filtered = save_snapshot(configured.workspace, selected_spec, payload)
    Store(configured.workspace).stage(filtered, MatchSettings())
    output = tmp_path / "packet"
    build_packet(configured, selection, footprints, filtered, output, "http://127.0.0.1:8768")
    candidate = json.loads((output / "packet.json").read_text())["candidates"][0]
    assert [zone["source_record"] for zone in candidate["zones"]] == ["way/3"]
    assert "compatible_monitoring_zone_geometry_or_role" in candidate["missing"]


def test_packet_refuses_duplicate_source_ids(
    project: Path, tmp_path: Path, spec: SourceSpec
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    from allyourbase.sources.snapshots import verify_snapshot

    snapshot, payload = verify_snapshot(footprints)
    data = json.loads(payload.read_text())
    data["features"].append(data["features"][0])
    duplicated = tmp_path / "duplicate.geojson"
    duplicated.write_text(json.dumps(data))
    manifest = save_snapshot(configured.workspace, snapshot.spec, duplicated)
    output = tmp_path / "packet"
    with pytest.raises(InputError, match="duplicate source record"):
        build_packet(configured, selection, manifest, zones, output, "http://127.0.0.1:8768")
    assert not output.exists()


@pytest.mark.parametrize("state", ["rejected", "superseded"])
def test_packet_refuses_unavailable_footprint(
    project: Path, tmp_path: Path, spec: SourceSpec, state: str
) -> None:
    configured, selection, footprints, zones = setup_packet(project, tmp_path, spec)
    store = Store(configured.workspace)
    identifier = next(
        proposal["id"]
        for proposal in store.proposals()
        if proposal["content"]["record"]["external_id"] == "way/1"
    )
    if state == "rejected":
        store.decide(identifier, "rejected", "synthetic-reviewer", "Fixture decision")
    else:
        from allyourbase.sources.snapshots import verify_snapshot

        snapshot, payload = verify_snapshot(footprints)
        data = json.loads(payload.read_text())
        data["features"][0]["properties"]["name"] = "Replacement footprint"
        changed = tmp_path / "replacement.geojson"
        changed.write_text(json.dumps(data))
        store.stage(save_snapshot(configured.workspace, snapshot.spec, changed), MatchSettings())
    output = tmp_path / "packet"
    with pytest.raises(InputError, match="active and staged"):
        build_packet(configured, selection, footprints, zones, output, "http://127.0.0.1:8768")
    assert not output.exists()
