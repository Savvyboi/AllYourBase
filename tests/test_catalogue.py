from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from allyourbase.catalogue.validation import check_catalogue
from allyourbase.loading import load_data
from allyourbase.models.settings import Settings


def write(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_complete_synthetic_catalogue(catalogue: Path, settings: Settings) -> None:
    report = check_catalogue(catalogue, settings)
    assert report.ok, report.errors
    assert report.summary()["counts"] == {"sites": 1, "units": 1, "equipment": 1, "sources": 1}


def test_empty_catalogue_is_valid_with_warning(root: Path, settings: Settings) -> None:
    report = check_catalogue(root / "catalogue", settings)
    assert report.ok
    assert report.warnings


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("garrison", "unknown garrison"),
        ("equipment", "unknown equipment"),
        ("source", "unknown source"),
        ("tag", "unknown role term"),
        ("parent", "unknown parent"),
        ("cycle", "parent cycle"),
        ("derived", "must be derived"),
        ("country", "country differs"),
        ("zone", "unknown zone_type"),
        ("override", "unknown indicator override"),
        ("duplicate_site", "duplicate site id"),
        ("duplicate_source", "duplicate source id"),
    ],
)
def test_broken_references_rejected(
    catalogue: Path, settings: Settings, change: str, expected: str
) -> None:
    units_path = catalogue / "countries/XXX/units.yaml"
    sites_path = catalogue / "countries/XXX/sites.geojson"
    units = load_data(units_path)
    # geojson must remain JSON, so use the JSON writer below.
    sites = load_data(sites_path)
    unit = units["units"][0]
    props = sites["features"][0]["properties"]
    if change == "garrison":
        unit["garrisons"][0]["site"] = "xxx-missing"
    elif change == "equipment":
        unit["equipment"][0]["equipment"] = "missing"
    elif change == "source":
        unit["sources"] = ["missing"]
    elif change == "tag":
        props["tags"]["role"] = ["missing"]
    elif change == "parent":
        unit["parent"] = "missing"
    elif change == "cycle":
        unit["parent"] = unit["id"]
    elif change == "derived":
        props["tags"]["activity"] = ["aircraft_increase"]
    elif change == "country":
        unit["country"] = "YYY"
    elif change == "zone":
        props["zones"][0]["zone_type"] = "missing"
    elif change == "override":
        props["zones"][0]["indicator_overrides"] = {"missing": {"threshold": 1}}
    elif change == "duplicate_site":
        sites["features"].append(deepcopy(sites["features"][0]))
    else:
        sources_path = catalogue / "sources.yaml"
        sources = load_data(sources_path)
        sources["sources"].append(deepcopy(sources["sources"][0]))
        write(sources_path, sources)
    write(units_path, units)
    import json

    sites_path.write_text(json.dumps(sites), encoding="utf-8")
    report = check_catalogue(catalogue, settings)
    assert not report.ok
    assert any(expected in error for error in report.errors), report.errors


def test_duplicate_aoi_is_not_a_second_site(catalogue: Path, settings: Settings) -> None:
    import json

    path = catalogue / "countries/XXX/sites.geojson"
    data = load_data(path)
    other = deepcopy(data["features"][0])
    other["properties"]["id"] = "xxx-other-site"
    data["features"].append(other)
    path.write_text(json.dumps(data))
    report = check_catalogue(catalogue, settings)
    assert any("duplicate site AOI" in error for error in report.errors)


def test_orphan_equipment_term(catalogue: Path, settings: Settings) -> None:
    path = catalogue / "taxonomy.yaml"
    data = load_data(path)
    data["facets"]["equipment"]["terms"].append({"id": "missing", "label": "Missing"})
    write(path, data)
    report = check_catalogue(catalogue, settings)
    assert any("orphan equipment" in error for error in report.errors)


def test_missing_country_file(catalogue: Path, settings: Settings) -> None:
    (catalogue / "countries/XXX/units.yaml").unlink()
    report = check_catalogue(catalogue, settings)
    assert not report.ok
    assert any("unable to read" in error for error in report.errors)
