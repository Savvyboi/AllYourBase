"""Provider-neutral acquisition records; no activity assessment is made here."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from allyourbase.models.common import Contract, NonEmpty, Slug
from allyourbase.models.geometry import Geometry


class ProviderError(RuntimeError):
    """A public error code; raw response bodies, tokens and signed URLs are excluded."""

    def __init__(self, code: str, provider: str) -> None:
        self.code = code
        self.provider = provider
        super().__init__(f"{provider}: {code}")


def public_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.username is not None or parts.password is not None:
        return "[credential-bearing URL omitted]"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class Asset(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    key: NonEmpty
    href: NonEmpty = Field(repr=False)
    media_type: str | None = None
    roles: tuple[str, ...] = ()

    @field_serializer("href")
    def redact_signature(self, value: str) -> str:
        return public_url(value)


class Acquisition(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    provider: Slug
    collection: NonEmpty
    scene_id: NonEmpty
    sensor: Literal["s1", "s2"]
    acquired_at: datetime
    acquisition_end: datetime | None = None
    platform: str | None = None
    orbit_direction: Literal["ascending", "descending"] | None = None
    relative_orbit: Annotated[int, Field(gt=0)] | None = None
    instrument_mode: str | None = None
    polarisations: tuple[str, ...] = ()
    cloud_cover: Annotated[float, Field(ge=0, le=100)] | None = None
    assets: tuple[Asset, ...] = ()

    @field_validator("acquired_at", "acquisition_end")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("acquisition timestamps must have a timezone")
        return value

    @model_validator(mode="after")
    def increasing_interval(self) -> "Acquisition":
        if self.acquisition_end is not None and self.acquisition_end < self.acquired_at:
            raise ValueError("acquisition end precedes start")
        return self


class DiscoveryProvider(Protocol):
    def discover(self, geometry: Geometry, start: datetime, end: datetime) -> list[Acquisition]: ...


class AccessProvider(DiscoveryProvider, Protocol):
    def read_window(
        self, acquisition: Acquisition, geometry: Geometry, directory: Path
    ) -> dict[str, Any]: ...
