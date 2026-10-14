import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from allyourbase.catalogue.review import ReviewBundle, accept, recover
from allyourbase.catalogue.validation import check_catalogue
from allyourbase.loading import InputError, load_model
from allyourbase.project import Project
from allyourbase.review.catalogue_app import create_app
from allyourbase.sources.connectors import parse_records
from allyourbase.sources.contracts import Record, SourceSpec
from allyourbase.sources.matching import (
    MatchSettings,
    designation,
    distance,
    geocode,
    normalize,
    site_match,
)
from allyourbase.sources.snapshots import fetch_snapshot, save_snapshot, verify_snapshot
from allyourbase.sources.store import Store


def csv_file(tmp_path: Path, name: str = "Fictional airfield", longitude: str = "20") -> Path:
    path = tmp_path / "airports.csv"
    path.write_text(
        "id,ident,name,iso_country,longitude_deg,latitude_deg,type,gps_code\n"
        f"1,TEST,{name},RU,{longitude},60,small_airport,TEST\n",
        encoding="utf-8",
    )
    return path


def manual_snapshot(
    workspace: Path, tmp_path: Path, spec: SourceSpec, records: list[dict[str, Any]]
) -> Path:
    source = spec.source.model_copy(update={"reuse_class": "manual"})
    manual = SourceSpec(source=source, connector="manual", country=spec.country)
    path = tmp_path / "manual.json"
    path.write_text(json.dumps({"records": records}), encoding="utf-8")
    return save_snapshot(workspace, manual, path)


def test_immutable_snapshot_and_repeated_stage(tmp_path: Path, spec: SourceSpec) -> None:
    workspace = tmp_path / "data"
    path = csv_file(tmp_path)
    manifest = save_snapshot(workspace, spec, path)
    before = manifest.read_bytes()
    assert save_snapshot(workspace, spec, path) == manifest
    assert manifest.read_bytes() == before
    store = Store(workspace)
    assert store.stage(manifest, MatchSettings()) == {"parsed_records": 1, "new_proposals": 1}
    proposal = store.proposals()[0]
    store.decide(proposal["id"], "rejected", "test-reviewer", "fictional")
    assert Store(workspace).stage(manifest, MatchSettings())["new_proposals"] == 0
    assert not store.proposals()
    assert len(store.proposals("rejected")) == 1
    assert store.proposal(proposal["id"])["evidence"][0]["locator"] == "CSV row 2; id 1"


@pytest.mark.parametrize("part", ["payload", "manifest"])
def test_tamper_detected(tmp_path: Path, spec: SourceSpec, part: str) -> None:
    manifest = save_snapshot(tmp_path / "data", spec, csv_file(tmp_path))
    if part == "payload":
        (manifest.parent / "payload").write_text("changed")
    else:
        data = json.loads(manifest.read_text())
        data["spec"]["source"]["licence"] = "changed"
        manifest.write_text(json.dumps(data))
    with pytest.raises(InputError, match="mismatch"):
        verify_snapshot(manifest)


@pytest.mark.parametrize("reuse", ["manual", "reference"])
def test_reuse_permissions(reuse: str, spec: SourceSpec, tmp_path: Path) -> None:
    data = spec.model_dump(mode="json")
    data["source"]["reuse_class"] = reuse
    with pytest.raises(ValidationError):
        SourceSpec.model_validate(data)
    data["connector"] = "manual" if reuse == "manual" else "pdf"
    data["extraction_permitted"] = True
    allowed = SourceSpec.model_validate(data)
    with pytest.raises(InputError, match="only import"):
        fetch_snapshot(tmp_path, allowed)


def test_failed_parse_rolls_back(tmp_path: Path, spec: SourceSpec) -> None:
    path = csv_file(tmp_path)
    path.write_text(path.read_text() + "2,BAD,Broken,RU,not-a-number,60,small_airport,BAD\n")
    store = Store(tmp_path / "data")
    manifest = save_snapshot(store.workspace, spec, path)
    with pytest.raises(ValueError):
        store.stage(manifest, MatchSettings())
    assert store.proposals() == []
    with store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM heads").fetchone()[0] == 0


def test_changed_record_preserves_history(tmp_path: Path, spec: SourceSpec) -> None:
    store = Store(tmp_path / "data")
    first = save_snapshot(store.workspace, spec, csv_file(tmp_path))
    store.stage(first, MatchSettings())
    second = save_snapshot(store.workspace, spec, csv_file(tmp_path, "Changed fictional airfield"))
    assert first != second
    assert store.stage(second, MatchSettings())["new_proposals"] == 1
    with store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM records").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM stg_site").fetchone()[0] == 1


def test_country_and_civilian_status_not_invented(tmp_path: Path, spec: SourceSpec) -> None:
    manifest, payload = verify_snapshot(save_snapshot(tmp_path / "data", spec, csv_file(tmp_path)))
    row = list(parse_records(manifest, payload))[0]
    assert row.country == "RUS"
    assert "site_type" not in row.attributes and "status" not in row.attributes
    assert row.geometry is None


def test_normalization_and_global_distance() -> None:
    assert normalize("Тестовый полк") == "testovyy polk"
    settings = MatchSettings(honorifics=["Guards"], designation_types={"regiment": "regiment"})
    assert designation("12th Guards regiment", settings) == ("12 regiment", ["Guards"])
    a = Record(
        kind="site",
        external_id="a",
        name="Synthetic",
        country="RUS",
        locator="row 1",
        longitude=179.999,
        latitude=0,
    )
    b = a.model_copy(update={"longitude": -179.999})
    assert distance(a, b) < 0.3
    assert site_match(a, b, settings) is not None
    assert site_match(a, b.model_copy(update={"country": "FIN"}), settings) is None


def test_geocoding_keeps_ambiguous_towns() -> None:
    a = Record(
        kind="place",
        external_id="a",
        name="Synthetic town",
        country="RUS",
        locator="row 1",
        region="A",
    )
    b = a.model_copy(update={"external_id": "b", "region": "B"})
    assert geocode("Synthetic town", "RUS", None, [a, b]) == [a, b]
    assert geocode("Synthetic town", "RUS", "B", [a, b]) == [b]


def acceptance_case(project: Path, tmp_path: Path) -> tuple[Project, str, ReviewBundle]:
    from allyourbase.models.catalogue import SourcesFile

    source = load_model(project / "catalogue/sources.yaml", SourcesFile).sources[0]
    spec = SourceSpec(source=source, connector="manual", country="XXX")
    workspace = tmp_path / "data"
    path = tmp_path / "claim.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "kind": "site",
                        "external_id": "fictional",
                        "name": "Fictional",
                        "country": "XXX",
                        "locator": "human fixture",
                    }
                ]
            }
        )
    )
    store = Store(workspace)
    store.stage(save_snapshot(workspace, spec, path), MatchSettings())
    identifier = store.proposals()[0]["id"]
    feature = json.loads(
        (project / "catalogue/countries/XXX/sites.geojson").read_text(encoding="utf-8")
    )["features"][0]
    feature["properties"]["name"] = "Updated synthetic facility"
    bundle = ReviewBundle.model_validate({"sites": [feature]})
    return (
        Project.load(project, Path("config/settings.yaml")).__class__(
            project, Project.load(project, Path("config/settings.yaml")).settings, workspace
        ),
        identifier,
        bundle,
    )


def test_acceptance_validates_then_persists(project: Path, tmp_path: Path) -> None:
    configured, identifier, bundle = acceptance_case(project, tmp_path)
    target = project / "catalogue/countries/XXX/sites.geojson"
    original = target.read_bytes()
    assert accept(configured, identifier, bundle, "test-reviewer", "fixture", dry_run=True)[
        "validated"
    ]
    assert target.read_bytes() == original
    accept(configured, identifier, bundle, "test-reviewer", "fixture")
    assert check_catalogue(project / "catalogue", configured.settings).ok
    assert Store(configured.workspace).proposal(identifier)["state"] == "accepted"
    assert (project / "catalogue/provenance" / f"{identifier}.yaml").exists()
    assert (
        json.loads(target.read_text())["features"][0]["properties"]["name"]
        == "Updated synthetic facility"
    )
    with pytest.raises(InputError, match="pending"):
        accept(configured, identifier, bundle, "test-reviewer", "fixture")


def test_invalid_bundle_has_no_catalogue_side_effect(project: Path, tmp_path: Path) -> None:
    configured, identifier, bundle = acceptance_case(project, tmp_path)
    original = (project / "catalogue/countries/XXX/sites.geojson").read_bytes()
    bundle.sites[0].properties.status = "unknown"
    with pytest.raises(InputError, match="bundle rejected"):
        accept(configured, identifier, bundle, "test-reviewer", "fixture")
    assert (project / "catalogue/countries/XXX/sites.geojson").read_bytes() == original
    assert Store(configured.workspace).proposal(identifier)["state"] == "pending"


def test_interrupted_acceptance_recovers(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import allyourbase.catalogue.review as review

    configured, identifier, bundle = acceptance_case(project, tmp_path)
    original_apply = review._apply

    def interrupted(project: Project, data: dict[str, Any]) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(review, "_apply", interrupted)
    with pytest.raises(OSError):
        accept(configured, identifier, bundle, "test-reviewer", "fixture")
    monkeypatch.setattr(review, "_apply", original_apply)
    recover(configured)
    assert Store(configured.workspace).proposal(identifier)["state"] == "accepted"
    assert check_catalogue(project / "catalogue", configured.settings).ok
    assert not (configured.workspace / "review/pending-acceptance.json").exists()


def test_review_api_requires_loopback_and_token(project: Path, tmp_path: Path) -> None:
    configured, identifier, _ = acceptance_case(project, tmp_path)
    with TestClient(create_app(configured), base_url="http://127.0.0.1") as client:
        assert client.get("/", headers={"host": "evil.invalid"}).status_code == 403
        assert client.get("/api/queue").status_code == 403
        html = client.get("/").text
        token = html.split("const token='")[1].split("'")[0]
        headers = {"X-Review-Token": token}
        assert len(client.get("/api/queue", headers=headers).json()) == 1
        assert (
            client.post(
                "/api/decision/" + identifier,
                headers=headers | {"Origin": "https://evil.invalid"},
                json={"action": "reject", "reviewer": "test-reviewer"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/decision/" + identifier,
                headers=headers,
                json={"action": "reject", "reviewer": "test-reviewer"},
            ).status_code
            == 200
        )
        assert client.get("/api/queue", headers=headers).json() == []


def test_pending_journal_blocks_check_and_planning(project: Path, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from allyourbase.cli import app

    workspace = tmp_path / "data"
    (workspace / "review").mkdir(parents=True)
    (workspace / "review/pending-acceptance.json").write_text("{}")
    for command in [["catalogue", "check"], ["run", "--plan"]]:
        result = CliRunner().invoke(
            app, ["--root", str(project), *command], env={"ALLYOURBASE_HOME": str(workspace)}
        )
        assert result.exit_code == 1 and "catalogue recover" in result.output


def test_recovery_preserves_intervening_edits(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import allyourbase.catalogue.review as review

    configured, identifier, bundle = acceptance_case(project, tmp_path)
    original_apply = review._apply

    def interrupted(project: Project, data: dict[str, Any]) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(review, "_apply", interrupted)
    with pytest.raises(OSError):
        accept(configured, identifier, bundle, "test-reviewer", "fixture")
    monkeypatch.setattr(review, "_apply", original_apply)
    target = project / "catalogue/countries/XXX/sites.geojson"
    target.write_text("unrelated external edit")
    with pytest.raises(InputError, match="changed during acceptance"):
        recover(configured)
    assert target.read_text() == "unrelated external edit"
    assert Store(configured.workspace).proposal(identifier)["state"] == "pending"


def test_repeated_current_snapshot_skips_parsing_after_hash_check(
    tmp_path: Path, spec: SourceSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "data"
    manifest = save_snapshot(workspace, spec, csv_file(tmp_path))
    store = Store(workspace)
    store.stage(manifest, MatchSettings())
    proposal = store.proposals()[0]
    store.decide(proposal["id"], "rejected", "fixture-reviewer", "Retain decision")

    def unexpected_parse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("unchanged current snapshot was parsed again")

    monkeypatch.setattr("allyourbase.sources.store.parse_records", unexpected_parse)
    assert store.stage(manifest, MatchSettings()) == {"parsed_records": 1, "new_proposals": 0}
    assert store.proposal(proposal["id"])["state"] == "rejected"
    (manifest.parent / "payload").write_text("changed bytes")
    with pytest.raises(InputError, match="hash or size"):
        store.stage(manifest, MatchSettings())


def test_restaging_old_snapshot_restores_head_even_with_cached_count(
    tmp_path: Path, spec: SourceSpec
) -> None:
    workspace = tmp_path / "data"
    first = save_snapshot(workspace, spec, csv_file(tmp_path))
    store = Store(workspace)
    store.stage(first, MatchSettings())
    original = store.proposals()[0]["id"]
    second = save_snapshot(workspace, spec, csv_file(tmp_path, name="Changed fixture"))
    store.stage(second, MatchSettings())
    assert store.proposal(original)["active"] is False
    assert store.stage(first, MatchSettings()) == {"parsed_records": 1, "new_proposals": 0}
    assert store.proposal(original)["active"] is True
    assert len(store.proposals("superseded")) == 1


def test_existing_database_without_ingestion_stats_is_upgraded(
    tmp_path: Path, spec: SourceSpec
) -> None:
    workspace = tmp_path / "data"
    manifest = save_snapshot(workspace, spec, csv_file(tmp_path))
    store = Store(workspace)
    store.stage(manifest, MatchSettings())
    with store.connect() as connection:
        connection.execute("DROP TABLE ingestion_stats")
    assert store.stage(manifest, MatchSettings()) == {"parsed_records": 1, "new_proposals": 0}
    with store.connect() as connection:
        assert connection.execute("SELECT parsed_records FROM ingestion_stats").fetchall() == [(1,)]
