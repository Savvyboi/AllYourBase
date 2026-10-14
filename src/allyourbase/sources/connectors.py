"""Allow-listed fields from public datasets; no source row becomes a catalogue fact."""

import csv
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from allyourbase.loading import InputError
from allyourbase.sources.contracts import Record, Snapshot


def alpha2(country: str) -> str:
    import pycountry

    result = pycountry.countries.get(alpha_3=country)
    if result is None:
        raise InputError("unknown ISO3 country")
    return str(result.alpha_2)


def text_stream(payload: Path, name: str) -> io.TextIOBase:
    if name.endswith(".zip"):
        with zipfile.ZipFile(payload) as archive:
            members = [i for i in archive.infolist() if i.filename.endswith(".txt")]
            if len(members) != 1 or members[0].file_size > 512_000_000:
                raise InputError("expected one bounded gazetteer text file in ZIP")
            return io.StringIO(archive.read(members[0]).decode("utf-8-sig"))
    return payload.open(encoding="utf-8-sig")


def parse_records(snapshot: Snapshot, payload: Path) -> Iterator[Record]:
    connector = snapshot.spec.connector
    country = snapshot.spec.country
    if connector in {"ourairports", "runways"}:
        with payload.open(encoding="utf-8-sig", newline="") as stream:
            for line, row in enumerate(csv.DictReader(stream), 2):
                if connector == "ourairports":
                    if row["iso_country"] != alpha2(country):
                        continue
                    yield Record(
                        kind="site",
                        external_id=row["ident"],
                        name=row["name"],
                        country=country,
                        locator=f"CSV row {line}; id {row['id']}",
                        longitude=float(row["longitude_deg"]),
                        latitude=float(row["latitude_deg"]),
                        region=row.get("iso_region"),
                        attributes={
                            "icao": row.get("icao_code") or row.get("gps_code"),
                            "airport_type": row["type"],
                            "municipality": row.get("municipality"),
                            "url": f"https://ourairports.com/airports/{row['ident']}/",
                        },
                    )
                else:
                    # Runway dumps are global; the join to an airport enforces country scope.
                    yield Record(
                        kind="runway",
                        external_id=row["id"],
                        name=row["airport_ident"],
                        country=country,
                        locator=f"CSV row {line}",
                        attributes={
                            key: row.get(key)
                            for key in (
                                "airport_ident",
                                "length_ft",
                                "width_ft",
                                "surface",
                                "closed",
                                "le_ident",
                                "le_latitude_deg",
                                "le_longitude_deg",
                                "he_ident",
                                "he_latitude_deg",
                                "he_longitude_deg",
                            )
                        },
                    )
    elif connector == "geonames":
        with text_stream(payload, snapshot.original_name) as stream:
            for line, fields in enumerate(csv.reader(stream, delimiter="\t"), 1):
                if len(fields) != 19:
                    raise InputError(f"GeoNames row {line}: expected 19 fields")
                if fields[8] != alpha2(country) or fields[6] != "P":
                    continue
                yield Record(
                    kind="place",
                    external_id=fields[0],
                    name=fields[1],
                    country=country,
                    aliases=[fields[2], *fields[3].split(",")],
                    region=fields[10],
                    latitude=float(fields[4]),
                    longitude=float(fields[5]),
                    locator=f"GeoNames row {line}; geonameid {fields[0]}",
                    attributes={"feature_code": fields[7], "modified": fields[18]},
                )
    elif connector == "osm":
        yield from osm_records(snapshot, payload)
    elif connector == "wikidata":
        data = json.loads(payload.read_text(encoding="utf-8"))
        for line, binding in enumerate(data["results"]["bindings"], 1):
            row = {k: v["value"] for k, v in binding.items()}
            kind = row.get("kind")
            if kind not in {"site", "unit", "equipment"}:
                raise InputError("SPARQL exports must bind kind to site, unit or equipment")
            identifier = row["item"].rsplit("/", 1)[-1]
            if not re.fullmatch(r"Q[1-9][0-9]*", identifier):
                raise InputError("invalid Wikidata entity id")
            if row.get("instance") == "http://www.wikidata.org/entity/Q5":
                continue
            values: dict[str, Any] = {}
            if row.get("coord"):
                match = re.fullmatch(r"Point\(([-+0-9.eE]+) ([-+0-9.eE]+)\)", row["coord"])
                if not match:
                    raise InputError("unsupported Wikidata coordinate format")
                values = {"longitude": float(match[1]), "latitude": float(match[2])}
            yield Record(
                kind=kind,
                external_id=identifier,
                name=row["itemLabel"],
                name_local=row.get("nameLocal"),
                country=country,
                locator=f"SPARQL binding {line}; {identifier}",
                **values,
                attributes={
                    k: row[k]
                    for k in (
                        "icao",
                        "designation",
                        "branch",
                        "town",
                        "region",
                        "garrison",
                        "equipment",
                        "as_of",
                    )
                    if k in row
                }
                | {"wikidata": identifier}
                | ({"site_type": row["siteType"]} if "siteType" in row else {}),
            )
    elif connector == "pdf":
        import pdfplumber

        with pdfplumber.open(payload) as document:
            for number, page in enumerate(document.pages, 1):
                text = page.extract_text() or ""
                if not text.strip():
                    continue
                for rule_index, pattern in enumerate(snapshot.spec.pdf_unit_patterns):
                    for match_index, match in enumerate(re.finditer(pattern, text)):
                        groups = {
                            key: value
                            for key, value in match.groupdict().items()
                            if value and key in {"designation", "town", "branch", "as_of"}
                        }
                        yield Record(
                            kind="unit",
                            external_id=f"page-{number}-rule-{rule_index}-match-{match_index}",
                            name=groups["designation"],
                            country=country,
                            locator=f"page {number}; rule {rule_index}; match {match_index}",
                            attributes=groups | {"page": number, "excerpt": match.group(0)[:240]},
                        )
                # Local evidence only. Human reviewers supply the structured dated claims.
                yield Record(
                    kind="document",
                    external_id=f"page-{number}",
                    name=f"{snapshot.spec.source.title} page {number}",
                    country=country,
                    locator=f"page {number}",
                    attributes={"page": number, "text": text},
                )
    else:
        data = json.loads(payload.read_text(encoding="utf-8"))
        for row in data["records"]:
            record = Record.model_validate(row)
            if record.country != country:
                raise InputError("manual record country differs from the source spec")
            yield record


def osm_records(snapshot: Snapshot, payload: Path) -> Iterator[Record]:
    if snapshot.original_name.endswith((".pbf", ".osm")):
        executable = shutil.which("osmium")
        if not executable:
            raise InputError("PBF/XML ingestion needs osmium-tool; filtered GeoJSON also works")
        with tempfile.TemporaryDirectory() as temporary:
            filtered = Path(temporary) / "filtered.osm.pbf"
            exported = Path(temporary) / "features.geojson"
            # The input format is explicit because immutable payloads have no extension.
            input_format = "pbf" if snapshot.original_name.endswith(".pbf") else "osm"
            for command in (
                [
                    executable,
                    "tags-filter",
                    str(payload),
                    "--input-format",
                    input_format,
                    "nwr/military",
                    "w/landuse=military",
                    "wr/aeroway",
                    "-o",
                    str(filtered),
                ],
                [
                    executable,
                    "export",
                    str(filtered),
                    "-f",
                    "geojson",
                    "-a",
                    "type,id",
                    "-E",
                    "-o",
                    str(exported),
                ],
            ):
                result = subprocess.run(command, capture_output=True, check=False)
                if result.returncode:
                    raise InputError(
                        "osmium extraction failed; input must include referenced nodes"
                    )
            yield from _osm_geojson(snapshot, exported)
    else:
        yield from _osm_geojson(snapshot, payload)


def _osm_geojson(snapshot: Snapshot, path: Path) -> Iterator[Record]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for number, feature in enumerate(data["features"], 1):
        properties = feature["properties"]
        if not (
            properties.get("military")
            or properties.get("landuse") == "military"
            or properties.get("aeroway")
        ):
            continue
        geometry = feature["geometry"]
        identifier = str(feature.get("id") or properties.get("@id") or "")
        # osmium export uses numeric @id plus @type when configured; do not invent IDs.
        if not re.fullmatch(r"(node|way|relation)/[1-9][0-9]*", identifier):
            osm_type = properties.get("@type")
            if osm_type in {"node", "way", "relation"} and str(properties.get("@id", "")).isdigit():
                identifier = f"{osm_type}/{properties['@id']}"
            else:
                raise InputError("OSM GeoJSON needs stable IDs; use osmium --attributes type,id")
        values: dict[str, Any] = {}
        if geometry["type"] == "Point":
            values = {
                "longitude": geometry["coordinates"][0],
                "latitude": geometry["coordinates"][1],
            }
        elif geometry["type"] in {"Polygon", "MultiPolygon"}:
            from pydantic import TypeAdapter

            from allyourbase.models.geometry import Geometry, anchor_of, shape_on_anchor

            polygon: Geometry = TypeAdapter[Any](cast(Any, Geometry)).validate_python(geometry)
            center = shape_on_anchor(polygon, anchor_of(polygon)).centroid
            values = {
                "geometry": geometry,
                "longitude": (center.x + 180) % 360 - 180,
                "latitude": center.y,
            }
        else:
            continue
        yield Record(
            kind="site",
            external_id=identifier,
            name=properties.get("name:en") or properties.get("name") or identifier,
            name_local=properties.get("name"),
            country=snapshot.spec.country,
            locator=f"OSM {identifier}; feature {number}",
            **values,
            attributes={
                key: properties[key]
                for key in ("military", "aeroway", "landuse", "icao", "wikidata")
                if key in properties
            }
            | {"osm_id": identifier},
        )
