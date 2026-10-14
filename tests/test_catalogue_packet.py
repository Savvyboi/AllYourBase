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
