"""Mask numeric observations and compare them with earlier, matching baselines."""

import warnings
from dataclasses import dataclass
from itertools import combinations
from typing import cast

import numpy as np
from numpy.typing import NDArray

from allyourbase.monitor.config import MonitorConfig
from allyourbase.monitor.fetch import Cutout, require_optical, same_observation


@dataclass
class Comparison:
    current: Cutout
    baseline_scenes: list[Cutout]
    baseline: NDArray[np.float32]
    common: NDArray[np.bool_]
    difference: NDArray[np.float32]
    coverage: float


def valid_pixels(cutout: Cutout, config: MonitorConfig) -> NDArray[np.bool_]:
    data = cutout.pixels
    require_optical(cutout.acquisition)
    valid = np.isfinite(data[:4]).all(axis=0) & (data[5] == 1) & np.isin(data[4], [4, 5])
    cloudy = np.isin(data[4], [3, 8, 9, 10])
    radius = config.cloud_buffer_cells
    padded = np.pad(cloudy, radius)
    buffer = np.zeros_like(cloudy)
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            buffer |= padded[dy : dy + 100, dx : dx + 100]
    return cast(NDArray[np.bool_], valid & ~buffer)


def compare(current: Cutout, earlier: list[Cutout], config: MonitorConfig) -> Comparison:
    sensor = current.acquisition.sensor
    if any(other.grid != current.grid for other in earlier):
        raise ValueError("comparison grids differ")
    if any(
        other.acquisition.sensor != sensor
        or other.acquisition.acquired_at >= current.acquisition.acquired_at
        for other in earlier
    ):
        raise ValueError("baseline must contain only earlier observations of the same sensor")
    require_optical(current.acquisition)
    # A duplicated product is not an independent baseline observation.
    if len({c.acquisition.scene_id for c in earlier}) != len(earlier) or any(
        same_observation(left.acquisition, right.acquisition)
        for left, right in combinations(earlier, 2)
    ):
        raise ValueError("duplicate baseline acquisition")
    count = 4
    valid = valid_pixels(current, config)
    if earlier:
        masks = np.stack([valid_pixels(other, config) for other in earlier])
        stack = np.stack(
            [
                np.where(mask[None], other.pixels[:count], np.nan)
                for other, mask in zip(earlier, masks, strict=True)
            ]
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            baseline = np.nanmedian(stack, axis=0).astype(np.float32)
        valid &= masks.sum(axis=0) >= config.minimum_baseline_observations
    else:
        baseline = np.full((count, 100, 100), np.nan, dtype=np.float32)
        valid[:] = False
    valid &= np.isfinite(baseline).all(axis=0)
    difference = np.mean(np.abs(current.pixels[:4] - baseline), axis=0)
    difference = np.where(valid, difference, 0).astype(np.float32)
    return Comparison(current, earlier, baseline, valid, difference, float(valid.mean()))
