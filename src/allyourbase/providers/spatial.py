"""Split geographic AOIs for discovery without querying a near-global bounding box."""

import math
from typing import Any

from shapely.affinity import translate
from shapely.geometry import box, mapping

from allyourbase.models.geometry import Geometry, anchor_of, shape_on_anchor


def query_parts(geometry: Geometry) -> list[dict[str, Any]]:
    shape = shape_on_anchor(geometry, anchor_of(geometry))
    min_x, _, max_x, _ = shape.bounds
    first = math.floor((min_x + 180) / 360)
    last = math.floor((max_x + 180) / 360)
    parts = []
    for band in range(first, last + 1):
        clipped = shape.intersection(box(-180 + band * 360, -90, 180 + band * 360, 90))
        if not clipped.is_empty and clipped.area > 0:
            parts.append(dict(mapping(translate(clipped, xoff=-360 * band))))
    return parts
