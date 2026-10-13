from pathlib import Path

import pytest

from allyourbase.loading import InputError
from allyourbase.project import Project


def test_workspace_override_precedence(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEWATCH_HOME", str(tmp_path / "legacy"))
    monkeypatch.setenv("ALLYOURBASE_HOME", str(tmp_path / "new"))
    project = Project.load(root, Path("config/settings.yaml"))
    assert project.workspace == tmp_path / "new"
    assert not project.workspace.exists()


def test_legacy_workspace(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLYOURBASE_HOME", raising=False)
    monkeypatch.setenv("BASEWATCH_HOME", str(tmp_path / "legacy"))
    assert Project.load(root, Path("config/settings.yaml")).workspace == tmp_path / "legacy"


def test_workspace_inside_code_rejected(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLYOURBASE_HOME", str(root / "state"))
    with pytest.raises(InputError, match="outside the code"):
        Project.load(root, Path("config/settings.yaml"))


def test_symlink_cannot_bypass_workspace_separation(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "linked-code"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable on this platform")
    monkeypatch.setenv("ALLYOURBASE_HOME", str(link / "state"))
    with pytest.raises(InputError, match="outside the code"):
        Project.load(root, Path("config/settings.yaml"))
