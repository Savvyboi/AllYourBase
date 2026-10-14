"""Validate human-edited bundles before recoverable, provenance-preserving catalogue writes."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from shutil import copytree
from typing import Any

import yaml
from pydantic import Field

from allyourbase.catalogue.validation import check_catalogue
from allyourbase.loading import InputError, load_data
from allyourbase.models.catalogue import Equipment, SiteFeature, Source, TaxonomyTerm, Unit
from allyourbase.models.common import Contract
from allyourbase.project import Project
from allyourbase.sources.contracts import Digest, Snapshot
from allyourbase.sources.snapshots import canonical, verify_snapshot
from allyourbase.sources.store import Store, workflow_lock


class ReviewBundle(Contract):
    sites: list[SiteFeature] = Field(default_factory=list)
    units: list[Unit] = Field(default_factory=list)
    equipment: list[Equipment] = Field(default_factory=list)
    terms: dict[str, list[TaxonomyTerm]] = Field(default_factory=dict)
    evidence_proposals: list[Digest] = Field(default_factory=list, max_length=100)


def _merge(
    records: list[dict[str, Any]], additions: list[dict[str, Any]], site: bool = False
) -> None:
    def identifier(value: dict[str, Any]) -> str:
        return str(value["properties"]["id"] if site else value["id"])

    for addition in additions:
        key = identifier(addition)
        records[:] = [value for value in records if identifier(value) != key]
        records.append(addition)
    records.sort(key=identifier)


def _write(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(content, ensure_ascii=False, indent=2)
        if path.suffix == ".geojson"
        else yaml.safe_dump(content, allow_unicode=True, sort_keys=False)
    )
    path.write_text(text + "\n", encoding="utf-8")


def prepare(
    project: Project,
    store: Store,
    identifier: str,
    bundle: ReviewBundle,
    reviewer: str,
    note: str,
    directory: Path,
) -> dict[str, Any]:
    proposal = store.proposal(identifier)
    if proposal["state"] != "pending" or not proposal["active"] or not reviewer.strip():
        raise InputError("an active pending proposal and reviewer are required")
    if not (bundle.sites or bundle.units or bundle.equipment):
        raise InputError("acceptance requires at least one structured catalogue record")
    identifiers = [identifier, *bundle.evidence_proposals]
    if len(identifiers) != len(set(identifiers)):
        raise InputError("evidence proposal IDs must be distinct, excluding the primary proposal")
    evidence = list(proposal["evidence"])
    for related_id in bundle.evidence_proposals:
        related = store.proposal(related_id)
        if not related["active"] or related["state"] not in {"pending", "accepted"}:
            raise InputError("supporting evidence must be active and pending or accepted")
        evidence.extend(related["evidence"])
    evidence = list({canonical(entry): entry for entry in evidence}.values())
    current = check_catalogue(project.root / "catalogue", project.settings)
    if not current.ok or current.catalogue is None:
        raise InputError("repair the existing catalogue before accepting proposals")
    copytree(project.root / "catalogue", directory)
    source_data = load_data(directory / "sources.yaml")
    sources = {
        entry["id"]: Source.model_validate(entry).model_dump(mode="json")
        for entry in source_data["sources"]
    }
    for entry in evidence:
        pinned = Snapshot.model_validate(entry["manifest"])
        retained, _ = verify_snapshot(
            project.workspace / "sources" / pinned.spec.source.id / pinned.id / "manifest.json"
        )
        if retained != pinned:
            raise InputError("retained source manifest differs from staged evidence")
        source = retained.spec.source.model_dump(mode="json")
        if source["id"] in sources and sources[source["id"]] != source:
            raise InputError(
                "source ID already exists with different metadata; use a versioned source ID"
            )
        sources[source["id"]] = source
    source_data["sources"] = sorted(sources.values(), key=lambda s: s["id"])
    _write(directory / "sources.yaml", source_data)
    for country in sorted(
        {s.properties.country for s in bundle.sites} | {u.country for u in bundle.units}
    ):
        folder = directory / "countries" / country
        sites_path, units_path = folder / "sites.geojson", folder / "units.yaml"
        sites: dict[str, Any] = (
            load_data(sites_path)
            if sites_path.exists()
            else {"type": "FeatureCollection", "features": []}
        )
        units: dict[str, Any] = (
            load_data(units_path) if units_path.exists() else {"schema_version": 1, "units": []}
        )
        _merge(
            sites["features"],
            [s.model_dump(mode="json") for s in bundle.sites if s.properties.country == country],
            True,
        )
        _merge(
            units["units"],
            [
                u.model_dump(mode="json", by_alias=True)
                for u in bundle.units
                if u.country == country
            ],
        )
        _write(sites_path, sites)
        _write(units_path, units)
    equipment = load_data(directory / "equipment.yaml")
    _merge(equipment["equipment"], [e.model_dump(mode="json") for e in bundle.equipment])
    _write(directory / "equipment.yaml", equipment)
    taxonomy = load_data(directory / "taxonomy.yaml")
    for facet, terms in bundle.terms.items():
        if facet not in taxonomy["facets"]:
            raise InputError("unknown taxonomy facet in acceptance bundle")
        _merge(taxonomy["facets"][facet]["terms"], [t.model_dump(mode="json") for t in terms])
    _write(directory / "taxonomy.yaml", taxonomy)
    report = check_catalogue(directory, project.settings)
    if not report.ok:
        raise InputError("bundle rejected: " + "; ".join(report.errors))
    if not evidence:
        raise InputError("proposal has no immutable source evidence")
    provenance = {
        "schema_version": 1,
        "proposal_id": identifier,
        "evidence_proposals": bundle.evidence_proposals,
        "reviewer": reviewer,
        "note": note,
        "bundle": bundle.model_dump(mode="json", by_alias=True),
        "evidence": evidence,
    }
    _write(directory / "provenance" / f"{identifier}.yaml", provenance)
    return provenance


def accept(
    project: Project,
    identifier: str,
    bundle: ReviewBundle,
    reviewer: str,
    note: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    from filelock import FileLock

    store = Store(project.workspace)
    journal = project.workspace / "review" / "pending-acceptance.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with workflow_lock(project.workspace), FileLock(str(journal) + ".lock", timeout=0):
        if journal.exists():
            raise InputError("unfinished catalogue write; run catalogue recover first")
        baseline = {
            path.relative_to(project.root / "catalogue").as_posix(): path.read_bytes()
            for path in (project.root / "catalogue").rglob("*")
            if path.is_file()
        }
        with tempfile.TemporaryDirectory(dir=project.workspace / "review") as temporary:
            directory = Path(temporary) / "catalogue"
            provenance = prepare(project, store, identifier, bundle, reviewer, note, directory)
            changes = []
            for candidate in sorted(directory.rglob("*")):
                if not candidate.is_file():
                    continue
                relative = candidate.relative_to(directory)
                target = project.root / "catalogue" / relative
                old = baseline.get(relative.as_posix())
                actual = target.read_bytes() if target.exists() else None
                if actual != old:
                    raise InputError(
                        "catalogue changed during validation; retry after reviewing edits"
                    )
                content = candidate.read_bytes().decode("utf-8")
                if old == candidate.read_bytes():
                    continue
                changes.append(
                    {
                        "path": relative.as_posix(),
                        "old_sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
                        "new_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                        "content": content,
                    }
                )
            result = {
                "proposal_id": identifier,
                "validated": True,
                "changed_files": [c["path"] for c in changes],
                "dry_run": dry_run,
            }
            if dry_run:
                return result
            data = {
                "root": str(project.root.resolve()),
                "proposal_id": identifier,
                "reviewer": reviewer,
                "note": note,
                "bundle": provenance["bundle"],
                "changes": changes,
            }
            temporary_journal = journal.with_suffix(".tmp")
            with temporary_journal.open("w", encoding="utf-8") as output:
                output.write(canonical(data))
                output.flush()
                os.fsync(output.fileno())
            temporary_journal.replace(journal)
            _apply(project, data)
            journal.unlink()
            return result


def _apply(project: Project, data: dict[str, Any]) -> None:
    if data["root"] != str(project.root.resolve()):
        raise InputError("catalogue journal belongs to another project")
    targets = []
    for change in data["changes"]:
        target = (project.root / "catalogue" / change["path"]).resolve()
        if not target.is_relative_to(
            (project.root / "catalogue").resolve()
        ) or not target.is_relative_to(project.root.resolve()):
            raise InputError("catalogue journal path escapes the catalogue")
        current = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if current not in {change["old_sha256"], change["new_sha256"]}:
            raise InputError(
                "catalogue changed during acceptance; preserve journal and resolve the conflict"
            )
        if hashlib.sha256(change["content"].encode("utf-8")).hexdigest() != change["new_sha256"]:
            raise InputError("catalogue journal hash mismatch")
        targets.append((target, change))
    # Validate every precondition before writing any file. Recovery safely repeats each replace.
    for target, change in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".review-tmp")
        with temporary.open("w", encoding="utf-8", newline="") as output:
            output.write(change["content"])
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(target)
    report = check_catalogue(project.root / "catalogue", project.settings)
    if not report.ok:
        raise InputError(
            "catalogue changed during write; preserve journal and resolve validation errors"
        )
    store = Store(project.workspace)
    if store.proposal(data["proposal_id"])["state"] == "pending":
        store.decide(
            data["proposal_id"], "accepted", data["reviewer"], data["note"], data["bundle"]
        )


def recover(project: Project) -> None:
    from filelock import FileLock

    journal = project.workspace / "review" / "pending-acceptance.json"
    with workflow_lock(project.workspace), FileLock(str(journal) + ".lock", timeout=0):
        if not journal.exists():
            raise InputError("no pending catalogue write")
        _apply(project, json.loads(journal.read_text(encoding="utf-8")))
        journal.unlink()
