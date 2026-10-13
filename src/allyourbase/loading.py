"""Safe file loading with duplicate YAML keys rejected and values redacted on error."""

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError


class InputError(ValueError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise InputError("expected a YAML mapping")
        self.flatten_mapping(node)
        keys: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in keys
                keys.add(key)
            except TypeError as exc:
                raise InputError("YAML mapping key must be a scalar") from exc
            if duplicate:
                raise InputError(f"duplicate YAML key on line {key_node.start_mark.line + 1}")
        return super().construct_mapping(node, deep=deep)


def load_data(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".json", ".geojson"}:
            return json.loads(text, object_pairs_hook=_unique_json_object)
        return yaml.load(text, Loader=UniqueKeyLoader)
    except OSError as exc:
        raise InputError(f"{path}: unable to read file") from exc
    except (yaml.YAMLError, json.JSONDecodeError, UnicodeError) as exc:
        raise InputError(f"{path}: malformed {path.suffix} file") from exc


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON key")
        result[key] = value
    return result


def load_model[T: BaseModel](path: Path, model: type[T]) -> T:
    try:
        return model.model_validate(load_data(path))
    except ValidationError as exc:
        locations = [
            f"{'.'.join(map(str, error['loc'])) or '<root>'}: {error['type']}"
            for error in exc.errors(include_input=False, include_context=False)
        ]
        raise InputError(f"{path}: " + "; ".join(locations)) from exc
