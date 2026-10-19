from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from allyourbase.monitor.config import (
    Location,
    Locations,
    MonitorConfig,
    freeze_grid,
    make_grid,
    windows,
)
from allyourbase.monitor.detect import detect, patches
from allyourbase.monitor.fetch import Cutout
from allyourbase.monitor.main import SyntheticImagery
from allyourbase.monitor.prepare import compare, valid_pixels
from allyourbase.providers.contracts import ProviderError


def observations(sensor: str = "s2") -> list[Cutout]:
    source = SyntheticImagery(date(2020, 10, 12), True)
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    return [
        source.cutout(s, grid)
        for s in source.discover(grid, sensor, *windows(date(2020, 10, 12))[::2])
    ]


def test_seven_complete_days_and_disjoint_28_day_baseline() -> None:
    baseline, start, end = windows(date(2026, 10, 15))
    assert start == datetime(2026, 10, 8, tzinfo=UTC)
    assert end - start == timedelta(days=7) and start - baseline == timedelta(days=28)
    assert end.hour == 0 and end.tzinfo == UTC


@pytest.mark.parametrize(
    "lat,lon,epsg",
    [
        (55.8783, 38.061699, 32637),
        (-30, 20, 32734),
        (85, 10, 32661),
        (-85, 10, 32761),
        (10, 179.999, 32660),
        (10, -179.999, 32601),
    ],
)
def test_metric_square_is_exactly_1000_m_and_coordinate_order(
    lat: float, lon: float, epsg: int
) -> None:
    from pyproj import Transformer

    location = Location(id="test", name="Fictional", latitude=lat, longitude=lon)
    grid = make_grid(location)
    assert grid.epsg == epsg
    assert grid.width == grid.height == 100 and grid.resolution_m == 10
    assert grid.bbox[2] - grid.bbox[0] == pytest.approx(1000)
    assert grid.bbox[3] - grid.bbox[1] == pytest.approx(1000)
    longitude, latitude = Transformer.from_crs(epsg, 4326, always_xy=True).transform(
        (grid.bbox[0] + grid.bbox[2]) / 2, (grid.bbox[1] + grid.bbox[3]) / 2
    )
    assert longitude == pytest.approx(lon) and latitude == pytest.approx(lat)
    grid.geographic()


def test_bad_coordinates_duplicate_ids_and_frozen_grid(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        Location(id="test", name="Fictional", latitude=100, longitude=0)
    location = Location(id="test", name="Fictional", latitude=0, longitude=0)
    with pytest.raises(ValidationError):
        Locations(sites=[location, location])
    path = tmp_path / "grid.json"
    first = freeze_grid(location, path)
    assert freeze_grid(location.model_copy(update={"name": "Renamed"}), path) == first
    assert freeze_grid(location.model_copy(update={"category": "Airfields"}), path) == first
    with pytest.raises(ValueError, match="new stable"):
        freeze_grid(location.model_copy(update={"longitude": 1}), path)


def test_unchanged_fixture_quiet_and_qualifying_patch_detected(
    monitor_config: MonitorConfig,
) -> None:
    cutouts = observations()
    comparison = compare(cutouts[-1], cutouts[:-1], monitor_config)
    assert comparison.coverage == 1
    assert int(detect(comparison, monitor_config).sum()) == 500
    cutouts[-1].pixels[:4] = cutouts[0].pixels[:4]
    assert not detect(compare(cutouts[-1], cutouts[:-1], monitor_config), monitor_config).any()


def test_patch_size_and_eight_connected_components() -> None:
    mask = np.zeros((100, 100), dtype=np.bool_)
    mask[10:13, 10:13] = True
    mask[40:42, 40:44] = True
    assert patches(mask, 9).sum() == 9


@pytest.mark.parametrize(
    "kind", ["cloud", "water", "missing", "snow", "few_baselines", "low_coverage"]
)
def test_bad_optical_data_is_insufficient(kind: str, monitor_config: MonitorConfig) -> None:
    cutouts = observations()
    earlier = cutouts[:-1]
    if kind == "few_baselines":
        earlier = earlier[:1]
    elif kind == "low_coverage":
        cutouts[-1].pixels[5, :31] = 0
    elif kind == "missing":
        cutouts[-1].pixels[5] = 0
    else:
        cutouts[-1].pixels[4] = {"cloud": 9, "water": 6, "snow": 11}[kind]
    comparison = compare(cutouts[-1], earlier, monitor_config)
    assert comparison.coverage < 0.7 and not detect(comparison, monitor_config).any()


def test_cloud_buffer_and_pixelwise_baseline_count(monitor_config: MonitorConfig) -> None:
    cutouts = observations()
    cutouts[-1].pixels[4, 50, 50] = 3
    valid = valid_pixels(cutouts[-1], monitor_config)
    assert not valid[49:52, 49:52].any() and valid[48, 48]
    for c in cutouts[:2]:
        c.pixels[5, :20] = 0
    comparison = compare(cutouts[-1], cutouts[:-1], monitor_config)
    assert not comparison.common[:20].any() and comparison.common[20:40].all()


def test_radar_is_refused_by_the_active_monitor(monitor_config: MonitorConfig) -> None:
    assert not any(key.startswith("radar_") for key in monitor_config.http.model_dump())
    cutouts = observations()
    cutouts[-1].acquisition = cutouts[-1].acquisition.model_copy(update={"sensor": "s1"})
    with pytest.raises(ProviderError, match="unsupported_sensor"):
        compare(cutouts[-1], [], monitor_config)


def test_future_duplicate_or_shifted_baselines_are_refused(monitor_config: MonitorConfig) -> None:
    cutouts = observations()
    with pytest.raises(ValueError, match="duplicate"):
        compare(cutouts[-1], [cutouts[0], cutouts[0]], monitor_config)
    with pytest.raises(ValueError, match="earlier"):
        compare(cutouts[0], [cutouts[-1]], monitor_config)
    cutouts[0].grid = cutouts[0].grid.model_copy(update={"epsg": 32632})
    with pytest.raises(ValueError, match="grids"):
        compare(cutouts[-1], cutouts[:-1], monitor_config)
