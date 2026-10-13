from pathlib import Path

import pytest

from allyourbase.loading import InputError, load_data


@pytest.mark.parametrize("text", ["key: 1\nkey: 2\n", "outer:\n  key: 1\n  key: 2\n"])
def test_duplicate_yaml_keys(tmp_path: Path, text: str) -> None:
    path = tmp_path / "input.yaml"
    path.write_text(text)
    with pytest.raises(InputError, match="duplicate YAML key"):
        load_data(path)


def test_yaml_never_constructs_python_objects(tmp_path: Path) -> None:
    path = tmp_path / "input.yaml"
    path.write_text("!!python/object/apply:os.system ['echo should-not-execute']")
    with pytest.raises(InputError, match="malformed"):
        load_data(path)


def test_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"key": 1, "key": 2}')
    with pytest.raises(InputError, match="duplicate JSON key"):
        load_data(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="unable to read"):
        load_data(tmp_path / "not_here.yaml")
