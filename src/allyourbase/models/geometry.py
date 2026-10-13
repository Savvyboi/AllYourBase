"""GeoJSON polygon sanity, including longitude unwrapping at the antimeridian."""

from itertools import combinations
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union
from shapely.validation import explain_validity

from allyourbase.models.common import Contract

Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Position = tuple[Longitude, Latitude]
Ring = Annotated[list[Position], Field(min_length=4)]
PolygonCoordinates = Annotated[list[Ring], Field(min_length=1)]


def unwrap_ring(ring: list[Position], anchor: float | None = None) -> list[Position]:
    """Use continuous longitudes; put holes/other polygons near the same anchor."""
    if ring[0] != ring[-1]:
        raise ValueError("polygon rings must be closed")
    if len(set(ring[:-1])) < 3:
        raise ValueError("polygon rings need at least three distinct vertices")
    unwrapped: list[Position] = []
    previous = ring[0][0] if anchor is None else anchor
    for longitude, latitude in ring:
        longitude += 360 * round((previous - longitude) / 360)
        unwrapped.append((longitude, latitude))
        previous = longitude
    if unwrapped[0] != unwrapped[-1]:
        raise ValueError("rings wrapping the globe need a split AOI")
    return unwrapped


def polygon_shape(coordinates: list[list[Position]], anchor: float | None = None) -> Any:
    exterior = unwrap_ring(coordinates[0], anchor)
    holes = [unwrap_ring(ring, exterior[0][0]) for ring in coordinates[1:]]
    return ShapelyPolygon(exterior, holes)


class Polygon(Contract):
    type: Literal["Polygon"]
    coordinates: PolygonCoordinates

    @model_validator(mode="after")
    def sane(self) -> "Polygon":
        geometry = polygon_shape(self.coordinates)
        if not geometry.is_valid or geometry.area == 0:
            raise ValueError(f"invalid polygon: {explain_validity(geometry)}")
        return self


class MultiPolygon(Contract):
    type: Literal["MultiPolygon"]
    coordinates: Annotated[list[PolygonCoordinates], Field(min_length=1)]

    @model_validator(mode="after")
    def sane(self) -> "MultiPolygon":
        anchor = self.coordinates[0][0][0][0]
        pieces = [polygon_shape(p, anchor) for p in self.coordinates]
        for piece in pieces:
            if not piece.is_valid or piece.area == 0:
                raise ValueError(f"invalid multipolygon part: {explain_validity(piece)}")
        for left, right in combinations(pieces, 2):
            intersection = left.intersection(right)
            if intersection.area > 0:
                raise ValueError("multipolygon parts overlap")
            if intersection.length > 0:
                min_x, _, max_x, _ = intersection.bounds
                if min_x != max_x or (min_x + 180) % 360 != 0:
                    raise ValueError("multipolygon parts share an edge away from the antimeridian")
        # A GeoJSON split at +/-180 is allowed to share its seam after unwrapping.
        geometry = unary_union(pieces)
        if not geometry.is_valid:
            raise ValueError(f"invalid multipolygon: {explain_validity(geometry)}")
        return self


Geometry = Annotated[Polygon | MultiPolygon, Field(discriminator="type")]


def shape_on_anchor(geometry: Geometry, anchor: float) -> Any:
    if isinstance(geometry, Polygon):
        return polygon_shape(geometry.coordinates, anchor)
    return unary_union([polygon_shape(p, anchor) for p in geometry.coordinates])


def anchor_of(geometry: Geometry) -> float:
    if isinstance(geometry, Polygon):
        return geometry.coordinates[0][0][0]
    return geometry.coordinates[0][0][0][0]
