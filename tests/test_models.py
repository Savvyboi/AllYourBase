from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from allyourbase.loading import InputError, load_data, load_model
from allyourbase.models.catalogue import GarrisonLink, SitesFile, Source, TaxonomyFacet
from allyourbase.models.geometry import MultiPolygon, Polygon
from allyourbase.models.settings import Settings


def test_default_settings_review_first(settings: Settings) -> None:
    assert settings.publish.policy == "reviewed_only"
    assert settings.publish.site_repository is None
    assert settings.preprocessing.radar.orthorectify is True
    assert settings.preprocessing.radar.backscatter_coefficient == "GAMMA0_TERRAIN"


@pytest.mark.parametrize("change", ["secret", "bad_indicator", "levels", "budget", "iso_week"])
def test_settings_reject_bad_inputs(root: Path, change: str) -> None:
    data = load_data(root / "config/settings.yaml")
    if change == "secret":
        data["providers"]["definitions"]["cdse_sentinelhub"]["client_secret"] = "private-value"
    elif change == "bad_indicator":
        data["primary_indicators"]["airbase"] = ["does_not_exist"]
    elif change == "levels":
        data["scoring"]["high_primary_z"] = data["scoring"]["elevated_primary_z"]
    elif change == "budget":
        data["budgets"]["stop_optional_at_fraction"] = 1.5
    else:
        data["schedule"]["default_start_week"] = "2021-W53"
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_dated_link_requires_asof_and_sources() -> None:
    valid: dict[str, Any] = {
        "site": "xxx-example-site",
        "from": "2025-01-01",
        "as_of": "2026-01-01",
        "confidence": "reported",
        "sources": ["synthetic-fixture"],
    }
    assert GarrisonLink.model_validate(valid).to_date is None
    changes: list[dict[str, Any]] = [
        {"sources": []},
        {"to": "2024-01-01"},
        {"as_of": "2024-01-01"},
    ]
    for change in changes:
        with pytest.raises(ValidationError):
            GarrisonLink.model_validate(valid | change)
    del valid["as_of"]
    with pytest.raises(ValidationError):
        GarrisonLink.model_validate(valid)


@pytest.mark.parametrize("reuse", ["import", "reference", "manual"])
def test_source_reuse_classes(catalogue: Path, reuse: str) -> None:
    data = load_data(catalogue / "sources.yaml")["sources"][0]
    data["reuse_class"] = reuse
    assert Source.model_validate(data).reuse_class == reuse


def test_taxonomy_cycle_rejected() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        TaxonomyFacet.model_validate(
            {
                "label": "Example",
                "terms": [
                    {"id": "a", "label": "A", "parent": "b"},
                    {"id": "b", "label": "B", "parent": "a"},
                ],
            }
        )


@pytest.mark.parametrize("kind", ["unclosed", "self_crossing", "out_of_range", "zero_area"])
def test_bad_polygons(kind: str) -> None:
    rings = {
        "unclosed": [[0, 0], [1, 0], [1, 1], [0, 1]],
        "self_crossing": [[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]],
        "out_of_range": [[181, 0], [182, 0], [182, 1], [181, 1], [181, 0]],
        "zero_area": [[0, 0], [1, 0], [2, 0], [0, 0]],
    }
    with pytest.raises(ValidationError):
        Polygon.model_validate({"type": "Polygon", "coordinates": [rings[kind]]})


def test_antimeridian_zone_containment(catalogue: Path) -> None:
    data = load_data(catalogue / "countries/XXX/sites.geojson")
    site = data["features"][0]
    site["geometry"]["coordinates"] = [[[179, 0], [-179, 0], [-179, 2], [179, 2], [179, 0]]]
    site["properties"]["zones"][0]["geometry"]["coordinates"] = [
        [[179.5, 0.5], [-179.5, 0.5], [-179.5, 1.5], [179.5, 1.5], [179.5, 0.5]]
    ]
    SitesFile.model_validate(data)
    site["properties"]["zones"][0]["geometry"]["coordinates"] = [
        [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    ]
    with pytest.raises(ValidationError, match="beyond site AOI"):
        SitesFile.model_validate(data)


def test_split_multipolygon() -> None:
    MultiPolygon.model_validate(
        {
            "type": "MultiPolygon",
            "coordinates": [
                [[[179, 0], [180, 0], [180, 1], [179, 1], [179, 0]]],
                [[[-180, 0], [-179, 0], [-179, 1], [-180, 1], [-180, 0]]],
            ],
        }
    )


def test_multilingual_names(catalogue: Path) -> None:
    loaded = load_model(catalogue / "countries/XXX/sites.geojson", SitesFile)
    assert loaded.features[0].properties.name_local == "Пример · مثال · 示例"


def test_validation_error_does_not_expose_secret(tmp_path: Path, root: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text((root / "config/settings.yaml").read_text() + "client_secret: private-value\n")
    with pytest.raises(InputError) as exc:
        load_model(path, Settings)
    assert "private-value" not in str(exc.value)
