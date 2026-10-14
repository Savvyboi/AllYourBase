"""Convert native Overpass evidence while distinguishing footprints from source centres."""

from typing import Any, cast

from pydantic import TypeAdapter, ValidationError
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import polygonize_full, unary_union

from allyourbase.loading import InputError
from allyourbase.models.geometry import Geometry


def _unwrap(points: list[dict[str, float]], anchor: float) -> list[tuple[float, float]]:
    result = []
    previous = anchor
    for point in points:
        longitude = point["lon"]
        longitude += 360 * round((previous - longitude) / 360)
        result.append((longitude, point["lat"]))
        previous = longitude
    return result


def _wrap(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and all(isinstance(n, (int, float)) for n in value):
            return [((value[0] + 180) % 360) - 180, value[1]]
        return [_wrap(item) for item in value]
    return value


def _relation_geometry(element: dict[str, Any]) -> dict[str, Any]:
    members = [member for member in element.get("members", []) if member.get("type") == "way"]
    if not members or any(not member.get("geometry") for member in members):
        raise InputError("relation member geometry is incomplete")
    if any(member.get("role", "") not in {"outer", "inner", ""} for member in members):
        raise InputError("unsupported relation member role")
    anchor = members[0]["geometry"][0]["lon"]
    rings: dict[str, list[Any]] = {}
    for role in ("outer", "inner"):
        lines = [
            LineString(_unwrap(member["geometry"], anchor))
            for member in members
            if (member.get("role") or "outer") == role
        ]
        if not lines:
            rings[role] = []
            continue
        polygons, cuts, dangles, invalid = polygonize_full(lines)
        if polygons.is_empty or any(not part.is_empty for part in (cuts, dangles, invalid)):
            raise InputError("relation rings cannot be assembled from complete source ways")
        rings[role] = [Polygon(polygon.exterior.coords) for polygon in polygons.geoms]
    if not rings["outer"]:
        raise InputError("relation has no complete outer rings")
    holes: dict[int, list[Any]] = {index: [] for index in range(len(rings["outer"]))}
    for inner in rings["inner"]:
        containers = [
            (outer.area, index) for index, outer in enumerate(rings["outer"]) if outer.covers(inner)
        ]
        if not containers:
            raise InputError("relation inner ring lies outside its outer rings")
        _, index = min(containers)
        holes[index].append(inner.exterior.coords)
    # An outer island inside an inner ring remains a separate filled component.
    result = unary_union(
        [Polygon(outer.exterior.coords, holes[index]) for index, outer in enumerate(rings["outer"])]
    )
    geometry = dict(mapping(result))
    geometry["coordinates"] = _wrap(geometry["coordinates"])
    return geometry


def overpass_features(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("remark"):
        raise InputError("Overpass returned a partial/error result; it cannot be staged")
    if not isinstance(data.get("elements"), list):
        raise InputError("Overpass response must contain an elements list")
    features = []
    for element in data["elements"]:
        tags = element.get("tags", {})
        if not (
            tags.get("military")
            or tags.get("landuse") == "military"
            or tags.get("aeroway")
            or tags.get("man_made") == "pier"
            or tags.get("amenity") == "parking"
            or tags.get("natural") == "water"
        ):
            continue
        kind = element["type"]
        if kind not in {"node", "way", "relation"}:
            continue
        properties = dict(tags)
        properties["@type"], properties["@id"] = kind, element["id"]
        geometry: dict[str, Any] | None = None
        issue = None
        if kind == "node" and "lon" in element and "lat" in element:
            geometry = {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
            properties["geometry_role"] = "mapped_point"
        elif kind in {"way", "relation"} and (element.get("geometry") or element.get("members")):
            try:
                if kind == "way":
                    points = element["geometry"]
                    geometry = {
                        "type": "Polygon",
                        "coordinates": [[[point["lon"], point["lat"]] for point in points]],
                    }
                else:
                    if tags.get("type") not in {"multipolygon", "boundary"}:
                        raise InputError("relation is not a source area")
                    geometry = _relation_geometry(element)
                TypeAdapter[Any](cast(Any, Geometry)).validate_python(geometry)
                properties["geometry_role"] = "source_polygon"
            except (InputError, ValidationError, KeyError, TypeError, ValueError):
                geometry = None
                issue = "incomplete_or_invalid_source_area"
        if geometry is None:
            center = element.get("center")
            if center is None:
                raise InputError("OSM feature lacks usable geometry or an explicit source centre")
            geometry = {"type": "Point", "coordinates": [center["lon"], center["lat"]]}
            properties["geometry_role"] = "bbox_center"
            properties["geometry_issue"] = issue or "footprint_not_requested"
        features.append(
            {
                "type": "Feature",
                "id": f"{kind}/{element['id']}",
                "geometry": geometry,
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}
