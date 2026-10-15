"""Prototype possible-change patches; no cause, counts or confidence inferred."""

from collections import deque

import numpy as np
from numpy.typing import NDArray

from allyourbase.monitor.config import MonitorConfig
from allyourbase.monitor.prepare import Comparison


def patches(mask: NDArray[np.bool_], minimum: int) -> NDArray[np.bool_]:
    """Keep eight-connected components meeting the configured cell count."""
    visited = np.zeros_like(mask)
    kept = np.zeros_like(mask)
    height, width = mask.shape
    for y, x in zip(*np.where(mask), strict=True):
        if visited[y, x]:
            continue
        queue = deque([(int(y), int(x))])
        visited[y, x] = True
        component = []
        while queue:
            row, col = queue.popleft()
            component.append((row, col))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    r, c = row + dy, col + dx
                    if 0 <= r < height and 0 <= c < width and mask[r, c] and not visited[r, c]:
                        visited[r, c] = True
                        queue.append((r, c))
        if len(component) >= minimum:
            for row, col in component:
                kept[row, col] = True
    return kept


def detect(comparison: Comparison, config: MonitorConfig) -> NDArray[np.bool_]:
    if comparison.coverage < config.minimum_common_coverage:
        return np.zeros((100, 100), dtype=np.bool_)
    threshold = (
        config.optical_threshold
        if comparison.current.acquisition.sensor == "s2"
        else config.radar_threshold_db
    )
    return patches(
        comparison.common & (comparison.difference > threshold), config.minimum_patch_cells
    )
