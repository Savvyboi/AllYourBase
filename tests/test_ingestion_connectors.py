import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from test_ingestion import csv_file, manual_snapshot
from typer.testing import CliRunner

from allyourbase.cli import app
from allyourbase.loading import InputError
from allyourbase.sources.connectors import parse_records
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.matching import MatchSettings, unit_match
from allyourbase.sources.snapshots import fetch_snapshot, save_snapshot, verify_snapshot
from allyourbase.sources.store import Store


def test_geonames_filter_and_aliases(tmp_path: Path, spec: SourceSpec) -> None:
    spec = spec.model_copy(update={"connector": "geonames"})
    path = tmp_path / "RU.txt"
    path.write_text(
        "1\tТест\tTest\tSynthetic town,Test\t60\t20\tP\tPPL\tRU\t\t01\t\t\t\t"
        "1\t\t0\tEurope/Moscow\t2026-01-01\n",
        encoding="utf-8",
    )
    snapshot, payload = verify_snapshot(save_snapshot(tmp_path / "data", spec, path))
    rows = list(parse_records(snapshot, payload))
    assert len(rows) == 1 and rows[0].region == "01" and "Synthetic town" in rows[0].aliases


def test_wikidata_keeps_multiple_claims(tmp_path: Path, spec: SourceSpec) -> None:
    spec = spec.model_copy(update={"connector": "wikidata"})
    path = tmp_path / "query.json"
    rows = [
        {
            "item": "http://www.wikidata.org/entity/Q123",
            "itemLabel": "Fictional unit",
            "kind": "unit",
            "garrison": value,
        }
        for value in ["Q456", "Q789"]
    ]
    path.write_text(
        json.dumps(
            {"results": {"bindings": [{k: {"value": v} for k, v in row.items()} for row in rows]}}
        )
    )
    store = Store(tmp_path / "data")
    assert (
        store.stage(save_snapshot(store.workspace, spec, path), MatchSettings())["new_proposals"]
        == 2
    )
    assert {p["content"]["record"]["attributes"]["garrison"] for p in store.proposals()} == {
        "Q456",
        "Q789",
    }


def test_osm_polygon_preserves_original_object_id(tmp_path: Path, spec: SourceSpec) -> None:
    spec = spec.model_copy(update={"connector": "osm"})
    path = tmp_path / "filtered.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "@type": "relation",
                            "@id": 123,
                            "landuse": "military",
                            "name": "Fictional geometry",
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[179, 0], [-179, 0], [-179, 1], [179, 1], [179, 0]]],
                        },
                    }
                ],
            }
        )
    )
    snapshot, payload = verify_snapshot(save_snapshot(tmp_path / "data", spec, path))
    row = list(parse_records(snapshot, payload))[0]
    assert row.external_id == "relation/123" and row.geometry is not None
    assert row.longitude == -180 and row.latitude == 0.5


def test_pdf_page_provenance(
    tmp_path: Path, spec: SourceSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pdfplumber

    source = spec.source.model_copy(update={"reuse_class": "reference"})
    spec = SourceSpec(source=source, connector="pdf", country="RUS", extraction_permitted=True)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"synthetic PDF mocked for page provenance")

    class Page:
        def extract_text(self) -> str:
            return "Fictional source text stays local."

    class Document:
        pages = [Page(), Page()]

        def __enter__(self) -> "Document":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    monkeypatch.setattr(pdfplumber, "open", lambda _: Document())
    snapshot, payload = verify_snapshot(save_snapshot(tmp_path / "data", spec, path))
    rows = list(parse_records(snapshot, payload))
    assert [r.locator for r in rows] == ["page 1", "page 2"]
    assert all(r.kind == "document" for r in rows)


def test_matches_are_idempotent_and_rejections_survive(tmp_path: Path, spec: SourceSpec) -> None:
    store = Store(tmp_path / "data")
    first = {
        "kind": "site",
        "external_id": "a",
        "name": "Synthetic",
        "country": "RUS",
        "locator": "fixture",
        "longitude": 20,
        "latitude": 60,
        "attributes": {"icao": "TEST"},
    }
    for source_id in ["test-a", "test-b"]:
        source_spec = spec.model_copy(
            update={"source": spec.source.model_copy(update={"id": source_id})}
        )
        store.stage(
            manual_snapshot(store.workspace, tmp_path, source_spec, [first]), MatchSettings()
        )
    assert store.match(MatchSettings()) == 1
    match = next(p for p in store.proposals() if p["kind"] == "match")
    assert len(store.proposal(match["id"])["records"]) == 2
    store.decide(match["id"], "rejected", "test-reviewer", "fixture")
    assert store.match(MatchSettings()) == 0


def test_selectors_fail_closed(tmp_path: Path, spec: SourceSpec) -> None:
    spec = spec.model_copy(update={"record_ids": ["MISSING"]})
    store = Store(tmp_path / "data")
    with pytest.raises(InputError, match="not found"):
        store.stage(save_snapshot(store.workspace, spec, csv_file(tmp_path)), MatchSettings())
    assert store.proposals() == []


def test_download_size_limit_and_permissions(
    tmp_path: Path, spec: SourceSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"too much data"))
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs)
    )
    spec = spec.model_copy(update={"download_url": "https://example.invalid/data.csv"})
    with pytest.raises(InputError, match="byte limit"):
        fetch_snapshot(tmp_path, spec, max_bytes=2)
    assert not (tmp_path / "sources").exists()


def test_superseded_claims_are_visible_separately(tmp_path: Path, spec: SourceSpec) -> None:
    store = Store(tmp_path / "data")
    store.stage(save_snapshot(store.workspace, spec, csv_file(tmp_path)), MatchSettings())
    first = store.proposals()[0]["id"]
    store.stage(
        save_snapshot(store.workspace, spec, csv_file(tmp_path, "Changed")), MatchSettings()
    )
    assert len(store.proposals()) == 1 and len(store.proposals("superseded")) == 1
    assert store.proposal(first)["active"] is False


def test_cli_stage_and_queue(tmp_path: Path, spec: SourceSpec, root: Path) -> None:
    runner = CliRunner()
    workspace = tmp_path / "data"
    manifest = save_snapshot(workspace, spec, csv_file(tmp_path))
    args = ["--root", str(root)]
    env = {"ALLYOURBASE_HOME": str(workspace)}
    staged = runner.invoke(app, [*args, "sources", "stage", str(manifest)], env=env)
    assert staged.exit_code == 0, staged.output
    assert json.loads(staged.stdout)["new_proposals"] == 1
    queued = runner.invoke(app, [*args, "catalogue", "queue"], env=env)
    assert queued.exit_code == 0 and len(json.loads(queued.stdout)) == 1


def test_units_match_by_designation_and_branch() -> None:
    from allyourbase.sources.contracts import Record

    record = Record(
        kind="unit",
        external_id="a",
        name="12 Guards regiment",
        country="RUS",
        locator="fixture",
        attributes={"branch": "air_force", "designation": "12 Guards regiment"},
    )
    other = record.model_copy(
        update={
            "external_id": "b",
            "attributes": {"branch": "air_force", "designation": "12 regiment"},
        }
    )
    assert unit_match(record, other, MatchSettings(honorifics=["Guards"]))
    assert not unit_match(record, other.model_copy(update={"country": "FIN"}), MatchSettings())


def test_ambiguous_garrison_links_keep_every_candidate(tmp_path: Path, spec: SourceSpec) -> None:
    store = Store(tmp_path / "data")
    records = [
        {
            "kind": "place",
            "external_id": str(i),
            "name": "Fictional town",
            "country": "RUS",
            "locator": "fixture",
            "longitude": 20 + i * 0.01,
            "latitude": 60,
            "region": str(i),
        }
        for i in [1, 2]
    ]
    records += [
        {
            "kind": "unit",
            "external_id": "unit",
            "name": "Fictional unit",
            "country": "RUS",
            "locator": "fixture",
            "attributes": {"town": "Fictional town", "branch": "army"},
        },
        {
            "kind": "site",
            "external_id": "site",
            "name": "Fictional site",
            "country": "RUS",
            "locator": "fixture",
            "longitude": 20,
            "latitude": 60,
            "attributes": {"site_type": "garrison"},
        },
    ]
    store.stage(manual_snapshot(store.workspace, tmp_path, spec, records), MatchSettings())
    settings = MatchSettings(branch_site_types={"army": ["garrison"]})
    assert store.match(settings) == 2
    assert len([p for p in store.proposals() if p["kind"] == "link"]) == 2
    assert store.match(settings) == 0


def test_pdf_extracts_actual_text_and_configured_unit_rule(
    tmp_path: Path, spec: SourceSpec
) -> None:
    text = b"BT /F1 12 Tf 50 100 Td (12 regiment in Fictional Town) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream",
    ]
    content = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += str(number).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(content)
    content += b"xref\n0 6\n0000000000 65535 f \n"
    content += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    content += b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF"
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(content)
    spec = SourceSpec(
        source=spec.source.model_copy(update={"reuse_class": "reference"}),
        connector="pdf",
        country="RUS",
        extraction_permitted=True,
        pdf_unit_patterns=[r"(?P<designation>12 regiment) in (?P<town>Fictional Town)"],
    )
    snapshot, payload = verify_snapshot(save_snapshot(tmp_path / "data", spec, path))
    rows = list(parse_records(snapshot, payload))
    assert rows[0].kind == "unit" and rows[0].attributes["town"] == "Fictional Town"
    assert rows[0].locator.startswith("page 1")
    assert rows[1].attributes["text"] == "12 regiment in Fictional Town"
