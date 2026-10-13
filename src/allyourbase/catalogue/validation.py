"""Offline structural, geometry, provenance and referential-integrity checks."""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from allyourbase.loading import InputError, load_model
from allyourbase.models.catalogue import (
    Equipment,
    EquipmentFile,
    SiteFeature,
    SitesFile,
    Source,
    SourcesFile,
    TaxonomyFile,
    Unit,
    UnitsFile,
)
from allyourbase.models.geometry import anchor_of, shape_on_anchor
from allyourbase.models.settings import Settings


@dataclass
class Catalogue:
    sites: dict[str, SiteFeature]
    units: dict[str, Unit]
    equipment: dict[str, Equipment]
    sources: dict[str, Source]
    taxonomy: TaxonomyFile


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    catalogue: Catalogue | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> dict[str, object]:
        counts = {}
        if self.catalogue:
            counts = {
                "sites": len(self.catalogue.sites),
                "units": len(self.catalogue.units),
                "equipment": len(self.catalogue.equipment),
                "sources": len(self.catalogue.sources),
            }
        return {"ok": self.ok, "counts": counts, "errors": self.errors, "warnings": self.warnings}


def _index[T](
    records: Iterable[T], key: Callable[[T], str], label: str, errors: list[str]
) -> dict[str, T]:
    result: dict[str, T] = {}
    for record in records:
        record_id = key(record)
        if record_id in result:
            errors.append(f"duplicate {label} id: {record_id}")
        else:
            result[record_id] = record
    return result


def check_catalogue(root: Path, settings: Settings) -> ValidationReport:
    report = ValidationReport()
    try:
        taxonomy = load_model(root / "taxonomy.yaml", TaxonomyFile)
        sources_file = load_model(root / "sources.yaml", SourcesFile)
        equipment_file = load_model(root / "equipment.yaml", EquipmentFile)
    except InputError as exc:
        report.errors.append(str(exc))
        return report

    sites: list[SiteFeature] = []
    units: list[Unit] = []
    countries = root / "countries"
    if not countries.is_dir():
        report.errors.append(f"missing countries directory: {countries}")
        return report
    for directory in sorted(countries.iterdir()):
        if not directory.is_dir():
            continue
        if not re.fullmatch(r"[A-Z]{3}", directory.name):
            report.errors.append(f"country directory must use ISO3 uppercase: {directory.name}")
            continue
        try:
            country_sites = load_model(directory / "sites.geojson", SitesFile)
            country_units = load_model(directory / "units.yaml", UnitsFile)
        except InputError as exc:
            report.errors.append(str(exc))
            continue
        for site in country_sites.features:
            if site.properties.country != directory.name:
                report.errors.append(f"{site.properties.id}: country differs from directory")
            sites.append(site)
        for unit in country_units.units:
            if unit.country != directory.name:
                report.errors.append(f"{unit.id}: country differs from directory")
            units.append(unit)

    catalogue = Catalogue(
        sites=_index(sites, lambda s: s.properties.id, "site", report.errors),
        units=_index(units, lambda u: u.id, "unit", report.errors),
        equipment=_index(equipment_file.equipment, lambda e: e.id, "equipment", report.errors),
        sources=_index(sources_file.sources, lambda s: s.id, "source", report.errors),
        taxonomy=taxonomy,
    )
    report.catalogue = catalogue
    _references_and_tags(catalogue, settings, report.errors)
    _duplicates(catalogue, report.errors)
    if not catalogue.sites:
        report.warnings.append("Catalogue is empty; no sites are approved for processing.")
    return report


def _references_and_tags(catalogue: Catalogue, settings: Settings, errors: list[str]) -> None:
    terms = {
        facet: {term.id for term in definition.terms}
        for facet, definition in catalogue.taxonomy.facets.items()
    }

    def sources_exist(ids: list[str], label: str) -> None:
        if len(ids) != len(set(ids)):
            errors.append(f"{label}: duplicate source reference")
        for source in ids:
            if source not in catalogue.sources:
                errors.append(f"{label}: unknown source {source}")

    def term_exists(facet: str, term: str, label: str) -> None:
        if facet not in terms:
            errors.append(f"{label}: unknown facet {facet}")
        elif term not in terms[facet]:
            errors.append(f"{label}: unknown {facet} term {term}")

    for site in catalogue.sites.values():
        props = site.properties
        sources_exist(props.sources, props.id)
        term_exists("country", props.country.lower(), props.id)
        term_exists("site_type", props.site_type, props.id)
        term_exists("status", props.status, props.id)
        if props.site_type not in settings.primary_indicators:
            errors.append(f"{props.id}: site_type has no primary indicators in settings")
        if props.sensors == "radar_only":
            term_exists("data", "radar_only", props.id)
        for facet, values in props.tags.items():
            if len(values) != len(set(values)):
                errors.append(f"{props.id}: duplicate {facet} tag")
            for value in values:
                term_exists(facet, value, props.id)
            derived = {
                "country": props.country.lower(),
                "site_type": props.site_type,
                "status": props.status,
            }
            if facet in derived and values != [derived[facet]]:
                errors.append(f"{props.id}: {facet} tags conflict with site properties")
            if facet in {"activity", "unit", "equipment", "branch", "data"}:
                errors.append(f"{props.id}: {facet} tags must be derived, not manually assigned")
        for zone in props.zones:
            label = f"{props.id}/{zone.id}"
            sources_exist(zone.sources, label)
            if zone.zone_type not in settings.zone_types:
                errors.append(f"{label}: unknown zone_type {zone.zone_type}")
            for indicator_id, overrides in zone.indicator_overrides.items():
                indicator = settings.indicators.get(indicator_id)
                if indicator is None:
                    errors.append(f"{label}: unknown indicator override {indicator_id}")
                else:
                    for parameter in overrides:
                        if parameter not in indicator.parameters:
                            errors.append(f"{label}: unknown {indicator_id} parameter {parameter}")

    for unit in catalogue.units.values():
        sources_exist(unit.sources, unit.id)
        term_exists("branch", unit.branch, unit.id)
        term_exists("unit", unit.id, unit.id)
        if unit.parent is not None and unit.parent not in catalogue.units:
            errors.append(f"{unit.id}: unknown parent unit {unit.parent}")
        seen = {unit.id}
        parent = unit.parent
        while parent in catalogue.units:
            if parent in seen:
                errors.append(f"{unit.id}: unit parent cycle")
                break
            seen.add(parent)
            parent = catalogue.units[parent].parent
        for garrison in unit.garrisons:
            sources_exist(garrison.sources, f"{unit.id}/garrison")
            if garrison.site not in catalogue.sites:
                errors.append(f"{unit.id}: unknown garrison site {garrison.site}")
        for equipment_link in unit.equipment:
            sources_exist(equipment_link.sources, f"{unit.id}/equipment")
            if equipment_link.equipment not in catalogue.equipment:
                errors.append(f"{unit.id}: unknown equipment {equipment_link.equipment}")

    for equipment in catalogue.equipment.values():
        sources_exist(equipment.sources, equipment.id)
        term_exists("equipment", equipment.id, equipment.id)
    for facet, entity_ids in (("unit", catalogue.units), ("equipment", catalogue.equipment)):
        for term in terms.get(facet, set()):
            if term not in entity_ids:
                errors.append(f"orphan {facet} taxonomy term {term}")


def _duplicates(catalogue: Catalogue, errors: list[str]) -> None:
    wikidata: dict[tuple[str, str], str] = {}
    geometry: dict[tuple[str, str], str] = {}
    osm: dict[str, str] = {}
    for site in catalogue.sites.values():
        props = site.properties
        if props.wikidata:
            key = ("site", props.wikidata)
            if key in wikidata:
                errors.append(f"duplicate site Wikidata id: {props.id} and {wikidata[key]}")
            wikidata[key] = props.id
        normalized = shape_on_anchor(site.geometry, anchor_of(site.geometry)).normalize().wkb_hex
        geometry_key = (props.site_type, normalized)
        if geometry_key in geometry:
            errors.append(f"duplicate site AOI: {props.id} and {geometry[geometry_key]}")
        geometry[geometry_key] = props.id
        for osm_id in props.osm_ids:
            if osm_id in osm:
                errors.append(f"duplicate OSM reference: {props.id} and {osm[osm_id]}")
            osm[osm_id] = props.id
    for kind, entities in (("unit", catalogue.units.values()),):
        for unit in entities:
            if unit.wikidata:
                key = (kind, unit.wikidata)
                if key in wikidata:
                    errors.append(f"duplicate {kind} Wikidata id: {unit.id} and {wikidata[key]}")
                wikidata[key] = unit.id
    for equipment in catalogue.equipment.values():
        if equipment.wikidata:
            key = ("equipment", equipment.wikidata)
            if key in wikidata:
                errors.append(
                    f"duplicate equipment Wikidata id: {equipment.id} and {wikidata[key]}"
                )
            wikidata[key] = equipment.id
