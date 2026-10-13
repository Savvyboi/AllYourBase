"""All tunable thresholds and provider choices belong in YAML, not algorithms."""

from typing import Annotated, Literal

from pydantic import Field, HttpUrl, model_validator

from allyourbase.models.common import Contract, NonEmpty, Slug

PositiveInt = Annotated[int, Field(gt=0)]
Fraction = Annotated[float, Field(ge=0, le=1)]
EnvName = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")]


class RuntimeSettings(Contract):
    profile: Literal["local", "colab"]
    workspace: NonEmpty
    workers: PositiveInt
    home_env: EnvName
    legacy_home_env: EnvName


class Provider(Contract):
    kind: Literal["stac", "sentinelhub"]
    catalogue_url: HttpUrl
    collection: NonEmpty
    enabled: bool
    process_url: HttpUrl | None = None
    token_url: HttpUrl | None = None
    client_id_env: EnvName | None = None
    client_secret_env: EnvName | None = None

    @model_validator(mode="after")
    def authentication_contract(self) -> "Provider":
        if self.kind == "sentinelhub" and not all(
            (self.process_url, self.token_url, self.client_id_env, self.client_secret_env)
        ):
            raise ValueError("sentinelhub needs process/token URLs and credential env names")
        return self


class ProviderSelection(Contract):
    primary: Slug
    fallbacks: list[Slug]


class ProvidersSettings(Contract):
    optical: ProviderSelection
    radar: ProviderSelection
    definitions: dict[Slug, Provider]

    @model_validator(mode="after")
    def references_exist(self) -> "ProvidersSettings":
        for selection in (self.optical, self.radar):
            ids = [selection.primary, *selection.fallbacks]
            if len(ids) != len(set(ids)):
                raise ValueError("provider primary/fallback ids must be distinct")
            for provider_id in ids:
                if provider_id not in self.definitions:
                    raise ValueError(f"unknown provider {provider_id}")
            if not self.definitions[selection.primary].enabled:
                raise ValueError("primary provider must be enabled")
        return self


class RadarProcessingSettings(Contract):
    backscatter_coefficient: Literal["GAMMA0_TERRAIN"]
    orthorectify: Literal[True]
    dem: Literal["COPERNICUS_30"]
    resolution: Literal["HIGH"]
    polarisation_pairs: list[tuple[str, str]]
    auxiliary_bands: list[str]


class PreprocessSettings(Contract):
    resolution_m: PositiveInt
    north_polar_above: Annotated[float, Field(ge=0, le=90)]
    south_polar_below: Annotated[float, Field(ge=-90, le=0)]
    optical_bands: list[NonEmpty]
    scl_keep: list[Annotated[int, Field(ge=0, le=11)]]
    cloud_dilation_px: Annotated[int, Field(ge=0)]
    min_valid_fraction: Fraction
    max_alignment_shift_px: Annotated[float, Field(ge=0)]
    radar: RadarProcessingSettings


class ScheduleSettings(Contract):
    late_scene_recheck_weeks: Annotated[int, Field(ge=0)]
    retry_attempts: PositiveInt
    week_timezone: Literal["UTC"]
    default_start_week: Annotated[str, Field(pattern=r"^\d{4}-W\d{2}$")]

    @model_validator(mode="after")
    def actual_week(self) -> "ScheduleSettings":
        from allyourbase.weeks import ISOWeek

        ISOWeek.parse(self.default_start_week)
        return self


class IndicatorSettings(Contract):
    sensor: Literal["s1", "s2", "both"]
    zones: Annotated[list[Slug], Field(min_length=1)]
    parameters: dict[Slug, float]
    mad_floor: Annotated[float, Field(gt=0)]


class BaselineSettings(Contract):
    previous_weeks: PositiveInt
    seasonal_half_window_weeks: Annotated[int, Field(ge=0)]
    min_observations: PositiveInt


class ScoreSettings(Contract):
    elevated_primary_z: Annotated[float, Field(gt=0)]
    elevated_pair_z: Annotated[float, Field(gt=0)]
    high_primary_z: Annotated[float, Field(gt=0)]
    corroboration_required: Literal[True]
    confidence_min_looks: PositiveInt
    confidence_min_valid_fraction: Fraction

    @model_validator(mode="after")
    def increasing_levels(self) -> "ScoreSettings":
        if not self.elevated_pair_z <= self.elevated_primary_z < self.high_primary_z:
            raise ValueError("score cutoffs must be pair <= elevated < high")
        return self


class BudgetSettings(Contract):
    monthly_processing_units: PositiveInt
    stop_optional_at_fraction: Annotated[float, Field(gt=0, le=1)]
    max_parallel_radar_requests: PositiveInt
    published_site_max_mb: PositiveInt
    published_file_max_bytes: PositiveInt


class ImageSettings(Contract):
    size_px: PositiveInt
    max_size_px: PositiveInt
    max_bytes: PositiveInt
    margin_fraction: Fraction
    attribution_template: NonEmpty

    @model_validator(mode="after")
    def bounded_size(self) -> "ImageSettings":
        if self.size_px > self.max_size_px:
            raise ValueError("image size exceeds maximum")
        return self


class PublishSettings(Contract):
    policy: Literal["reviewed_only", "all_flagged"]
    delay_days: Annotated[int, Field(ge=0)]
    recent_activity_weeks: PositiveInt
    stale_after_days: PositiveInt
    allowed_extensions: Annotated[list[str], Field(min_length=1)]
    site_repository: str | None
    branch: NonEmpty

    @model_validator(mode="after")
    def extension_allowlist(self) -> "PublishSettings":
        if any(not ext.startswith(".") or "/" in ext for ext in self.allowed_extensions):
            raise ValueError("allowed_extensions must be dotted file extensions")
        return self


class MatchingSettings(Contract):
    airfield_distance_km: Annotated[float, Field(gt=0)]
    name_similarity: Fraction
    garrison_candidate_radius_km: Annotated[float, Field(gt=0)]
    stale_link_months: PositiveInt


class Settings(Contract):
    schema_version: Literal[1]
    project_name: NonEmpty
    runtime: RuntimeSettings
    providers: ProvidersSettings
    preprocessing: PreprocessSettings
    schedule: ScheduleSettings
    indicators: dict[Slug, IndicatorSettings]
    zone_types: Annotated[list[Slug], Field(min_length=1)]
    primary_indicators: dict[Slug, Annotated[list[Slug], Field(min_length=1)]]
    baseline: BaselineSettings
    scoring: ScoreSettings
    budgets: BudgetSettings
    images: ImageSettings
    publish: PublishSettings
    matching: MatchingSettings

    @model_validator(mode="after")
    def indicator_references(self) -> "Settings":
        if len(self.zone_types) != len(set(self.zone_types)):
            raise ValueError("zone_types must be distinct")
        for site_type, indicators in self.primary_indicators.items():
            for indicator in indicators:
                if indicator not in self.indicators:
                    raise ValueError(f"{site_type}: unknown primary indicator {indicator}")
        for name, config in self.indicators.items():
            for zone in config.zones:
                if zone != "all" and zone not in self.zone_types:
                    raise ValueError(f"{name}: unknown zone type {zone}")
        return self
