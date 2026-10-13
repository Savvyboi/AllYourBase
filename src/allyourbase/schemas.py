"""Deterministic JSON Schemas generated from the same models used by the CLI."""

import json
from pathlib import Path

from pydantic import BaseModel

from allyourbase.models.catalogue import (
    EquipmentFile,
    SitesFile,
    SourcesFile,
    TaxonomyFile,
    UnitsFile,
)
from allyourbase.models.settings import Settings

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "settings.schema.json": Settings,
    "sites.schema.json": SitesFile,
    "units.schema.json": UnitsFile,
    "equipment.schema.json": EquipmentFile,
    "sources.schema.json": SourcesFile,
    "taxonomy.schema.json": TaxonomyFile,
}


def schema_text(model: type[BaseModel]) -> str:
    schema = model.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def generate_schemas(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMA_MODELS.items():
        temporary = directory / f".{filename}.tmp"
        temporary.write_text(schema_text(model), encoding="utf-8")
        temporary.replace(directory / filename)


def stale_schemas(directory: Path) -> list[str]:
    return [
        filename
        for filename, model in SCHEMA_MODELS.items()
        if not (directory / filename).is_file()
        or (directory / filename).read_text(encoding="utf-8") != schema_text(model)
    ]
