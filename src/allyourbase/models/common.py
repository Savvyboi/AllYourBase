"""Shared contracts; unknown fields are errors, including accidental credentials."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")]
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
NonEmpty = Annotated[str, Field(min_length=1)]
Confidence = Literal["confirmed", "likely", "reported"]
SourceIds = Annotated[list[Slug], Field(min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ExternalLink(Contract):
    label: NonEmpty
    url: HttpUrl


class DatedClaim(Contract):
    """A fact at a stated date, with an interval that may later be closed."""

    confidence: Confidence
    sources: SourceIds
    as_of: date
    from_date: date = Field(alias="from")
    to_date: date | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def valid_interval(self) -> "DatedClaim":
        if self.to_date is not None and self.to_date < self.from_date:
            raise ValueError("to must be on or after from")
        if self.as_of < self.from_date:
            raise ValueError("as_of must be on or after from")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("sources must not contain duplicates")
        return self
