"""Human-curated site, unit, equipment, source and controlled-tag contracts."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, model_validator

from allyourbase.models.common import (
    Contract,
    CountryCode,
    DatedClaim,
    ExternalLink,
    NonEmpty,
    Slug,
    SourceIds,
)
from allyourbase.models.geometry import Geometry, anchor_of, shape_on_anchor

WikidataId = Annotated[str, Field(pattern=r"^Q[1-9][0-9]*$")]


class Source(Contract):
    id: Slug
    title: NonEmpty
    url: HttpUrl
    publisher: NonEmpty
    accessed: date
    archive_url: HttpUrl | None = None
    reuse_class: Literal["import", "reference", "manual"]
    licence: NonEmpty
    attribution: NonEmpty


class SourcesFile(Contract):
    schema_version: Literal[1]
    sources: list[Source]


class TaxonomyTerm(Contract):
    id: Slug
    label: NonEmpty
    labels: dict[str, NonEmpty] = Field(default_factory=dict)
    parent: Slug | None = None


class TaxonomyFacet(Contract):
    label: NonEmpty
    terms: list[TaxonomyTerm]

    @model_validator(mode="after")
    def valid_tree(self) -> "TaxonomyFacet":
        ids = [term.id for term in self.terms]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate taxonomy term")
        parents = {term.id: term.parent for term in self.terms}
        for term in self.terms:
            seen = {term.id}
            parent = term.parent
            while parent is not None:
                if parent not in parents:
                    raise ValueError(f"unknown parent {parent}")
                if parent in seen:
                    raise ValueError(f"taxonomy parent cycle involving {parent}")
                seen.add(parent)
                parent = parents[parent]
        return self


class TaxonomyFile(Contract):
    schema_version: Literal[1]
    facets: dict[Slug, TaxonomyFacet]


class Zone(Contract):
    id: Slug
    zone_type: Slug
    geometry: Geometry
    sources: SourceIds
    indicator_overrides: dict[Slug, dict[str, float]] = Field(default_factory=dict)
    water_mask: Geometry | None = None
    exclusion_masks: list[Geometry] = Field(default_factory=list)


class SiteProperties(Contract):
    id: Slug
    name: NonEmpty
    name_local: NonEmpty | None = None
    country: CountryCode
    site_type: Slug
    status: Slug
    sources: SourceIds
    as_of: date
    zones: Annotated[list[Zone], Field(min_length=1)]
    tags: dict[Slug, list[Slug]] = Field(default_factory=dict)
    wikidata: WikidataId | None = None
    osm_ids: list[Annotated[str, Field(pattern=r"^(node|way|relation)/[1-9][0-9]*$")]] = Field(
        default_factory=list
    )
    sensors: Literal["both", "radar_only"]
    links: list[ExternalLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def stable_id_and_zones(self) -> "SiteProperties":
        if not self.id.startswith(f"{self.country.lower()}-"):
            raise ValueError("site id must start with its lowercase country code and a hyphen")
        zone_ids = [zone.id for zone in self.zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("duplicate zone id within site")
        return self


class SiteFeature(Contract):
    type: Literal["Feature"]
    geometry: Geometry
    properties: SiteProperties

    @model_validator(mode="after")
    def contained_zones(self) -> "SiteFeature":
        validate_zone_containment(self.geometry, self.properties.zones)
        return self


def validate_zone_containment(geometry: Geometry, zones: list[Zone]) -> None:
    """Check geometry alone, without filling absent status, dates or sensor choices."""
    anchor = anchor_of(geometry)
    aoi = shape_on_anchor(geometry, anchor)
    for zone in zones:
        zone_shape = shape_on_anchor(zone.geometry, anchor)
        if not aoi.covers(zone_shape):
            raise ValueError(f"zone {zone.id} extends beyond site AOI")
        masks = [*zone.exclusion_masks]
        if zone.water_mask is not None:
            masks.append(zone.water_mask)
        for mask in masks:
            if not zone_shape.covers(shape_on_anchor(mask, anchor)):
                raise ValueError(f"mask extends beyond zone {zone.id}")


class SitesFile(Contract):
    type: Literal["FeatureCollection"]
    features: list[SiteFeature]


class GarrisonLink(DatedClaim):
    site: Slug


class EquipmentLink(DatedClaim):
    equipment: Slug


class Unit(Contract):
    id: Slug
    name: NonEmpty
    name_local: NonEmpty | None = None
    country: CountryCode
    designation: NonEmpty
    branch: Slug
    echelon: Slug
    parent: Slug | None = None
    wikidata: WikidataId | None = None
    sources: SourceIds
    as_of: date
    links: list[ExternalLink] = Field(default_factory=list)
    garrisons: list[GarrisonLink] = Field(default_factory=list)
    equipment: list[EquipmentLink] = Field(default_factory=list)


class UnitsFile(Contract):
    schema_version: Literal[1]
    units: list[Unit]


class Equipment(Contract):
    id: Slug
    name: NonEmpty
    category: Slug
    origin_country: CountryCode
    wikidata: WikidataId | None = None
    sources: SourceIds
    as_of: date
    links: list[ExternalLink] = Field(default_factory=list)


class EquipmentFile(Contract):
    schema_version: Literal[1]
    equipment: list[Equipment]
