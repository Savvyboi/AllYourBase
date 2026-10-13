"""Resolve project inputs and enforce separation of code and bulky local state."""

import os
from dataclasses import dataclass
from pathlib import Path

from allyourbase.loading import InputError, load_model
from allyourbase.models.settings import Settings


@dataclass(frozen=True)
class Project:
    root: Path
    settings: Settings
    workspace: Path

    @classmethod
    def load(cls, root: Path, settings_path: Path) -> "Project":
        root = root.expanduser().resolve()
        path = settings_path.expanduser()
        if not path.is_absolute():
            path = root / path
        settings = load_model(path, Settings)
        configured = (
            os.environ.get(settings.runtime.home_env)
            or os.environ.get(settings.runtime.legacy_home_env)
            or settings.runtime.workspace
        )
        workspace = Path(configured).expanduser()
        if not workspace.is_absolute():
            workspace = root / workspace
        workspace = workspace.resolve()
        if workspace.is_relative_to(root):
            raise InputError("data workspace must be outside the code repository")
        return cls(root, settings, workspace)
