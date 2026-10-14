"""Versioned source and staging contracts; imported rows are unapproved evidence."""

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from allyourbase.models.catalogue import Source
from allyourbase.models.common import Contract, CountryCode, NonEmpty

Connector = Literal["ourairports", "runways", "geonames", "osm", "wikidata", "pdf", "manual"]
Kind = Literal["site", "unit", "equipment", "place", "runway", "document", "link"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PARSER_VERSION = "1"


class SourceSpec(Contract):
    source: Source
    connector: Connector
    country: CountryCode
    download_url: HttpUrl | None = None
    extraction_permitted: bool = False
    pdf_unit_patterns: list[NonEmpty] = Field(default_factory=list)
    record_ids: list[NonEmpty] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def permissions(self) -> "SourceSpec":
        for url in (self.source.url, self.source.archive_url, self.download_url):
            if url is not None:
                parts = urlsplit(str(url))
                if parts.username or parts.password:
                    raise ValueError("source URLs must not contain credentials")
        import re

        for pattern in self.pdf_unit_patterns:
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                raise ValueError("invalid PDF unit rule") from exc
            if "designation" not in compiled.groupindex:
                raise ValueError("PDF unit rules need a named designation group")
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("duplicate source record selector")
        if self.connector == "manual" and self.source.reuse_class != "manual":
            raise ValueError("manual records require a manual-class source")
        if self.connector != "manual" and self.source.reuse_class == "manual":
            raise ValueError("manual-class sources cannot be parsed automatically")
        if self.source.reuse_class == "reference" and self.connector != "pdf":
            raise ValueError("reference sources support permitted local PDF extraction only")
        if self.connector == "pdf" and not self.extraction_permitted:
            raise ValueError(
                "PDF extraction needs explicit extraction_permitted in the source spec"
            )
        return self


class Snapshot(Contract):
    schema_version: Literal[1] = 1
    id: Digest
    sha256: Digest
    size_bytes: Annotated[int, Field(ge=0)]
    retrieved_at: AwareDatetime
    original_name: NonEmpty
    spec: SourceSpec
    parser_version: str = PARSER_VERSION


class Record(Contract):
    kind: Kind
    external_id: NonEmpty
    name: NonEmpty
    country: CountryCode
    locator: NonEmpty
    name_local: str | None = None
    aliases: list[str] = Field(default_factory=list)
    region: str | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    geometry: dict[str, Any] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coordinate_pair(self) -> "Record":
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("coordinates must be supplied as a pair")
        return self
