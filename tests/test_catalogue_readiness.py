import json
from pathlib import Path

import httpx
import pytest
from test_ingestion import acceptance_case, manual_snapshot
from typer.testing import CliRunner

from allyourbase.catalogue.readiness import readiness
from allyourbase.catalogue.review import ReviewBundle, accept
from allyourbase.cli import app
from allyourbase.loading import InputError, load_data, load_model
from allyourbase.models.catalogue import SourcesFile
from allyourbase.project import Project
from allyourbase.sources.contracts import SourceSpec
from allyourbase.sources.matching import MatchSettings
from allyourbase.sources.snapshots import fetch_snapshot, verify_snapshot
from allyourbase.sources.store import Store


def evidence_case(project: Path, tmp_path: Path) -> tuple[Project, str, ReviewBundle, str]:
    configured, primary, bundle = acceptance_case(project, tmp_path)
    source = load_model(project / "catalogue/sources.yaml", SourcesFile).sources[0]
    supporting = source.model_copy(update={"id": "supporting-fixture"})
    spec = SourceSpec(source=supporting, connector="manual", country="XXX")
    manifest = manual_snapshot(
        configured.workspace,
        tmp_path,
        spec,
        [
            {
                "kind": "equipment",
                "external_id": "fixture-equipment",
                "name": "Fictional equipment evidence",
                "country": "XXX",
                "locator": "page 7",
            }
        ],
    )
    store = Store(configured.workspace)
    store.stage(manifest, MatchSettings())
    related = next(p["id"] for p in store.proposals() if p["id"] != primary)
    data = bundle.model_dump(mode="json", by_alias=True)
    data["evidence_proposals"] = [related]
    data["sites"][0]["properties"]["sources"].append(supporting.id)
    data["sites"][0]["properties"]["zones"][0]["sources"] = [supporting.id]
    data["units"] = load_data(project / "catalogue/countries/XXX/units.yaml")["units"]
    data["equipment"] = load_data(project / "catalogue/equipment.yaml")["equipment"]
    data["equipment"][0]["sources"] = [supporting.id]
    return configured, primary, ReviewBundle.model_validate(data), related


def test_accept_combines_sources_without_deciding_supporting_proposal(
    project: Path,
    tmp_path: Path,
) -> None:
    configured, primary, bundle, related = evidence_case(project, tmp_path)
    before = (project / "catalogue/sources.yaml").read_bytes()
    accept(configured, primary, bundle, "test-reviewer", "synthetic", dry_run=True)
    assert (project / "catalogue/sources.yaml").read_bytes() == before
    accept(configured, primary, bundle, "test-reviewer", "synthetic")
    provenance = load_data(project / "catalogue/provenance" / f"{primary}.yaml")
    assert provenance["evidence_proposals"] == [related]
    assert len(provenance["evidence"]) == 2
    assert Store(configured.workspace).proposal(related)["state"] == "pending"
    report = readiness(configured, "XXX", 1, ["airbase"])
    assert report["ready"] is True, report
    assert report["sites"][0]["linked_units"] == ["xxx-example-unit"]
    assert readiness(configured, "XXX", 10, ["airbase"])["ready"] is False
    assert readiness(configured, "XXX", 1, ["airbase", "naval_base"])["ready"] is False


@pytest.mark.parametrize(
    "condition", ["duplicate", "self", "rejected", "superseded", "tampered", "manifest_metadata"]
)
def test_invalid_supporting_evidence_never_changes_catalogue(
    project: Path,
    tmp_path: Path,
    condition: str,
) -> None:
    configured, primary, bundle, related = evidence_case(project, tmp_path)
    store = Store(configured.workspace)
    if condition == "duplicate":
        bundle.evidence_proposals = [related, related]
    elif condition == "self":
        bundle.evidence_proposals = [primary]
    elif condition == "rejected":
        store.decide(related, "rejected", "test-reviewer", "fixture")
    else:
        entry = store.proposal(related)["evidence"][0]["manifest"]
        manifest = configured.workspace / "sources" / entry["spec"]["source"]["id"]
        manifest = manifest / entry["id"] / "manifest.json"
        if condition == "manifest_metadata":
            entry["spec"]["source"]["title"] = "Forged source metadata"
            with store.connect() as connection:
                connection.execute(
                    "UPDATE snapshots SET manifest=? WHERE id=?", [json.dumps(entry), entry["id"]]
                )
        elif condition == "tampered":
            manifest.with_name("payload").write_text("changed")
        else:
            snapshot, _ = verify_snapshot(manifest)
            store.stage(
                manual_snapshot(
                    configured.workspace,
                    tmp_path,
                    snapshot.spec,
                    [
                        {
                            "kind": "equipment",
                            "external_id": "fixture-equipment",
                            "name": "Changed",
                            "country": "XXX",
                            "locator": "page 8",
                        }
                    ],
                ),
                MatchSettings(),
            )
    before = {p: p.read_bytes() for p in (project / "catalogue").rglob("*") if p.is_file()}
    with pytest.raises(InputError):
        accept(configured, primary, bundle, "test-reviewer", "fixture")
    assert all(p.read_bytes() == content for p, content in before.items())
    assert store.proposal(primary)["state"] == "pending"


@pytest.mark.parametrize(
    "condition", ["record_edited", "snapshot_changed", "missing_snapshot", "reviewer_missing"]
)
def test_readiness_requires_exact_reviewed_records_and_retained_evidence(
    project: Path,
    tmp_path: Path,
    condition: str,
) -> None:
    configured, primary, bundle, related = evidence_case(project, tmp_path)
    accept(configured, primary, bundle, "test-reviewer", "fixture")
    if condition == "reviewer_missing":
        import yaml

        path = project / "catalogue/provenance" / f"{primary}.yaml"
        data = load_data(path)
        data["reviewer"] = None
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
    elif condition == "record_edited":
        path = project / "catalogue/countries/XXX/sites.geojson"
        data = load_data(path)
        data["features"][0]["properties"]["name"] = "Unreviewed edit"
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        evidence = Store(configured.workspace).proposal(related)["evidence"][0]["manifest"]
        payload = (
            configured.workspace
            / "sources"
            / evidence["spec"]["source"]["id"]
            / evidence["id"]
            / "payload"
        )
        if condition == "snapshot_changed":
            payload.write_text("changed")
        else:
            payload.unlink()
    report = readiness(configured, "XXX", 1, ["airbase"])
    assert report["ready"] is False
    assert "reviewed_site_and_zones_with_retained_evidence" in report["sites"][0]["missing"]


def test_non_overlapping_historical_links_do_not_satisfy_readiness(
    project: Path,
    tmp_path: Path,
) -> None:
    configured, primary, bundle, _ = evidence_case(project, tmp_path)
    data = bundle.model_dump(mode="json", by_alias=True)
    data["units"][0]["equipment"][0].update({"from": "2027-01-01", "as_of": "2027-01-01"})
    accept(configured, primary, ReviewBundle.model_validate(data), "test-reviewer", "fixture")
    report = readiness(configured, "XXX", 1, ["airbase"])
    assert report["ready"] is False and report["sites"][0]["linked_units"] == []


def test_contract_valid_catalogue_and_candidates_are_not_completed_reviews(
    project: Path,
    tmp_path: Path,
) -> None:
    configured, _, _, _ = evidence_case(project, tmp_path)
    report = readiness(configured, "XXX", 1, ["airbase"])
    assert report["validation"]["ok"] is True and report["ready"] is False
    assert report["pending_site_records"] == 1
    assert all(site["missing"] for site in report["sites"])
    with pytest.raises(InputError, match="unknown required"):
        readiness(configured, "XXX", 1, ["typo"])
    with pytest.raises(InputError, match="ISO3"):
        readiness(configured, "xx", 1, [])


def test_readiness_cli_returns_nonzero_for_incomplete_milestone(root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "absent-data"
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(root),
            "catalogue",
            "readiness",
            "--country",
            "RUS",
            "--require-type",
            "garrison",
        ],
        env={"ALLYOURBASE_HOME": str(workspace)},
    )
    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    assert report["ready"] is False and report["production_sites"] == 0
    assert not workspace.exists()


def test_source_http_errors_report_status_without_response_body(
    tmp_path: Path,
    spec: SourceSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client
    seen: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        return httpx.Response(429, text="private-debug-body")

    transport = httpx.MockTransport(response)
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    with pytest.raises(InputError, match="HTTP 429") as exc:
        fetch_snapshot(
            tmp_path, spec.model_copy(update={"download_url": "https://example.invalid/data.csv"})
        )
    assert "private-debug-body" not in str(exc.value)
    assert "https://github.com/Savvyboi/AllYourBase" in seen[0]
    assert len(seen) == 1


def test_review_api_validates_and_retains_supporting_sources(project: Path, tmp_path: Path) -> None:
    import re

    from fastapi.testclient import TestClient

    from allyourbase.review.catalogue_app import create_app

    configured, primary, bundle, related = evidence_case(project, tmp_path)
    with TestClient(create_app(configured), base_url="http://127.0.0.1") as client:
        token = re.search(r"const token='([^']+)'", client.get("/").text)
        assert token is not None
        headers = {"X-Review-Token": token[1]}
        body = {
            "action": "validate",
            "reviewer": "test-reviewer",
            "note": "synthetic",
            "bundle": bundle.model_dump(mode="json", by_alias=True),
        }
        response = client.post("/api/decision/" + primary, json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert Store(configured.workspace).proposal(primary)["state"] == "pending"
        body["action"] = "accept"
        response = client.post("/api/decision/" + primary, json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert Store(configured.workspace).proposal(related)["state"] == "pending"
        assert readiness(configured, "XXX", 1, ["airbase"])["ready"] is True


def test_previously_accepted_active_evidence_can_be_reused(project: Path, tmp_path: Path) -> None:
    configured, primary, bundle, related = evidence_case(project, tmp_path)
    Store(configured.workspace).decide(related, "accepted", "test-reviewer", "synthetic")
    accept(configured, primary, bundle, "test-reviewer", "synthetic")
    assert readiness(configured, "XXX", 1, ["airbase"])["ready"] is True


def test_windows_bom_query_is_pinned_without_bom(
    root: Path,
    tmp_path: Path,
    spec: SourceSpec,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yaml

    real_client = httpx.Client
    queries: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params["query"])
        return httpx.Response(200, json={"results": {"bindings": []}})

    transport = httpx.MockTransport(response)
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    spec = SourceSpec.model_validate(
        spec.model_dump(mode="json")
        | {"connector": "wikidata", "download_url": "https://example.invalid/sparql"}
    )
    spec_file = tmp_path / "source.yaml"
    spec_file.write_text(yaml.safe_dump(spec.model_dump(mode="json")), encoding="utf-8")
    query = tmp_path / "query.rq"
    query.write_text("SELECT ?item WHERE {} LIMIT 1", encoding="utf-8-sig")
    workspace = tmp_path / "data"
    result = CliRunner().invoke(
        app,
        ["--root", str(root), "sources", "fetch", str(spec_file), "--query-file", str(query)],
        env={"ALLYOURBASE_HOME": str(workspace)},
    )
    assert result.exit_code == 0, result.output
    manifest = Path(json.loads(result.output)["manifest"])
    _, payload = verify_snapshot(manifest)
    assert json.loads(payload.read_text(encoding="utf-8"))["allyourbase_query"] == queries[0]
    assert not queries[0].startswith("\ufeff")
