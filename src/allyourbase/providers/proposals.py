"""Source-backed test AOIs are separate from the production military catalogue."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, HttpUrl

from allyourbase.models.common import Contract, CountryCode, NonEmpty, Slug
from allyourbase.models.geometry import Geometry


class ProbeProperties(Contract):
    id: Slug
    name: NonEmpty
    country: CountryCode
    approved: bool
    source_url: HttpUrl
    source_snapshot_url: HttpUrl
    source_record: NonEmpty
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    accessed: date
    geometry_note: NonEmpty


class ProbeAOI(Contract):
    type: Literal["Feature"]
    geometry: Geometry
    properties: ProbeProperties


class ProbeAOIs(Contract):
    type: Literal["FeatureCollection"]
    features: Annotated[list[ProbeAOI], Field(min_length=1)]
