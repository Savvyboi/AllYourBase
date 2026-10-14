"""Report catalogue milestone evidence without accepting source claims."""

import re
from typing import Any

from allyourbase.catalogue.validation import Catalogue, check_catalogue
from allyourbase.loading import InputError, load_data
from allyourbase.models.common import DatedClaim
from allyourbase.project import Project
from allyourbase.sources.contracts import Snapshot
from allyourbase.sources.snapshots import verify_snapshot
from allyourbase.sources.store import Store


def _sources(record: dict[str, Any]) -> set[str]:
    properties = record.get("properties", record)
    sources = set(properties["sources"])
    for key in ("zones", "garrisons", "equipment"):
        for claim in properties.get(key, []):
            sources.update(claim["sources"])
    return sources


def _reviews(project: Project, catalogue: Catalogue) -> tuple[set[str], list[str]]:
    reviewed: set[str] = set()
    problems: list[str] = []
    current = {
        "sites": {key: value.model_dump(mode="json") for key, value in catalogue.sites.items()},
        "units": {
            key: value.model_dump(mode="json", by_alias=True)
            for key, value in catalogue.units.items()
        },
        "equipment": {
            key: value.model_dump(mode="json") for key, value in catalogue.equipment.items()
        },
    }
    for path in sorted((project.root / "catalogue/provenance").glob("*.yaml")):
        try:
            data = load_data(path)
            reviewer = data.get("reviewer")
            if (
                data.get("schema_version") != 1
                or not isinstance(reviewer, str)
                or not reviewer.strip()
                or not data.get("evidence")
            ):
                raise InputError("reviewer or evidence absent")
            sources: set[str] = set()
            for entry in data["evidence"]:
                pinned = Snapshot.model_validate(entry["manifest"])
                manifest, _ = verify_snapshot(
                    project.workspace
                    / "sources"
                    / pinned.spec.source.id
                    / pinned.id
                    / "manifest.json"
                )
                source = manifest.spec.source
                registered = catalogue.sources.get(source.id)
                if manifest != pinned or not entry["locator"] or registered != source:
                    raise InputError("retained evidence differs from the review record")
                sources.add(source.id)
            for kind, entities in current.items():
                for record in data["bundle"].get(kind, []):
                    key = record.get("properties", record)["id"]
                    if entities.get(key) == record and _sources(record).issubset(sources):
                        reviewed.add(f"{kind}:{key}")
        except (InputError, OSError, ValueError, KeyError, TypeError, AttributeError):
            problems.append(f"{path.name}: review evidence missing, invalid or changed")
    return reviewed, problems


def _overlap(left: DatedClaim, right: DatedClaim) -> bool:
    # A retrieval date never extends a claim interval. Open claims are bounded by as_of.
    return max(left.from_date, right.from_date) <= min(
        left.to_date or left.as_of, right.to_date or right.as_of, left.as_of, right.as_of
    )


def readiness(
    project: Project, country: str, minimum_sites: int, required_types: list[str]
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Z]{3}", country) or minimum_sites < 1:
        raise InputError("use an uppercase ISO3 country and a positive minimum site count")
    if (project.workspace / "review/pending-acceptance.json").exists():
        raise InputError("unfinished catalogue write; run catalogue recover first")
    validation = check_catalogue(project.root / "catalogue", project.settings)
    if not validation.ok or validation.catalogue is None:
        return {"ready": False, "country": country, "validation": validation.summary()}
    catalogue = validation.catalogue
    known_types = {term.id for term in catalogue.taxonomy.facets["site_type"].terms}
    if set(required_types) - known_types:
        raise InputError("unknown required site type")
    reviewed, problems = _reviews(project, catalogue)
    sites = []
    type_counts: dict[str, int] = {}
    for key, site in sorted(catalogue.sites.items()):
        if site.properties.country != country:
            continue
        site_type = site.properties.site_type
        type_counts[site_type] = type_counts.get(site_type, 0) + 1
        linked_units = []
        for unit in catalogue.units.values():
            if f"units:{unit.id}" not in reviewed:
                continue
            garrisons = [claim for claim in unit.garrisons if claim.site == key]
            equipment = [
                claim for claim in unit.equipment if f"equipment:{claim.equipment}" in reviewed
            ]
            if any(_overlap(garrison, item) for garrison in garrisons for item in equipment):
                linked_units.append(unit.id)
        missing = []
        if f"sites:{key}" not in reviewed:
            missing.append("reviewed_site_and_zones_with_retained_evidence")
        if not linked_units:
            missing.append("reviewed_dated_unit_and_equipment_links_with_overlapping_intervals")
        sites.append(
            {
                "id": key,
                "name": site.properties.name,
                "site_type": site_type,
                "linked_units": sorted(linked_units),
                "missing": missing,
            }
        )
    candidates = []
    for proposal in Store(project.workspace).proposals():
        record = proposal["content"].get("record")
        if not record or record["kind"] != "site" or record["country"] != country:
            continue
        candidates.append(
            {
                "proposal_id": proposal["id"],
                "external_id": record["external_id"],
                "name": record["name"],
                "source_type_hint": record["attributes"].get("site_type"),
                "source_polygon": record["geometry"] is not None,
            }
        )
    missing_types = sorted(set(required_types) - type_counts.keys())
    return {
        "ready": (
            len(sites) >= minimum_sites
            and not missing_types
            and all(not site["missing"] for site in sites)
            and not problems
        ),
        "country": country,
        "minimum_sites": minimum_sites,
        "production_sites": len(sites),
        "site_type_counts": type_counts,
        "missing_site_types": missing_types,
        "sites": sites,
        "pending_site_records": len(candidates),
        "candidates": candidates,
        "provenance_problems": problems,
        "validation": validation.summary(),
        "notice": "Evidence completeness only. Candidate records may duplicate sites. "
        "Source hints and matching scores are not reviewed facts or current deployments.",
    }
