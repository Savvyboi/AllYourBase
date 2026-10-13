import json
from pathlib import Path

from jsonschema import Draft202012Validator

from allyourbase.loading import load_data
from allyourbase.schemas import SCHEMA_MODELS, generate_schemas, schema_text, stale_schemas


def test_schemas_validate_documents(root: Path, catalogue: Path) -> None:
    files = {
        "settings.schema.json": root / "config/settings.yaml",
        "sites.schema.json": catalogue / "countries/XXX/sites.geojson",
        "units.schema.json": catalogue / "countries/XXX/units.yaml",
        "equipment.schema.json": catalogue / "equipment.yaml",
        "sources.schema.json": catalogue / "sources.yaml",
        "taxonomy.schema.json": catalogue / "taxonomy.yaml",
    }
    for name, model in SCHEMA_MODELS.items():
        schema = json.loads(schema_text(model))
        Draft202012Validator.check_schema(schema)
        # YAML dates are date objects; serialize to the interchange representation.
        document = json.loads(json.dumps(load_data(files[name]), default=str))
        Draft202012Validator(schema).validate(document)


def test_schema_drift_detected(tmp_path: Path) -> None:
    generate_schemas(tmp_path)
    assert stale_schemas(tmp_path) == []
    path = tmp_path / "settings.schema.json"
    path.write_text("{}")
    assert stale_schemas(tmp_path) == ["settings.schema.json"]


def test_committed_schemas_are_current(root: Path) -> None:
    assert stale_schemas(root / "schemas") == []
