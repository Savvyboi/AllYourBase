from datetime import date
from pathlib import Path
from shutil import copytree

import pytest

from allyourbase.loading import load_model
from allyourbase.models.catalogue import Source
from allyourbase.models.settings import Settings
from allyourbase.monitor.config import MonitorConfig
from allyourbase.sources.contracts import SourceSpec

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def settings(root: Path) -> Settings:
    return load_model(root / "config/settings.yaml", Settings)


@pytest.fixture
def catalogue(tmp_path: Path, root: Path) -> Path:
    destination = tmp_path / "catalogue"
    copytree(root / "fixtures/catalogue", destination)
    return destination


@pytest.fixture
def project(tmp_path: Path, root: Path, catalogue: Path) -> Path:
    destination = tmp_path / "project"
    copytree(root / "config", destination / "config")
    copytree(catalogue, destination / "catalogue")
    return destination


@pytest.fixture
def spec() -> SourceSpec:
    return SourceSpec(
        source=Source(
            id="test-import",
            title="Synthetic dataset",
            url="https://example.invalid/data",
            publisher="Test suite",
            accessed=date(2026, 1, 1),
            reuse_class="import",
            licence="Synthetic only",
            attribution="Test suite",
        ),
        connector="ourairports",
        country="RUS",
    )


@pytest.fixture
def monitor_config(root: Path) -> "MonitorConfig":
    return load_model(root / "config/monitor.yaml", MonitorConfig)
