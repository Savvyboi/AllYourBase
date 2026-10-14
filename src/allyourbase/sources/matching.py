"""Deterministic candidate ranking; alternatives remain available for human review."""

import math
import re
import unicodedata
from typing import Any

from pydantic import Field

from allyourbase.models.common import Contract
from allyourbase.sources.contracts import Record

CYRILLIC = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        [
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "yo",
            "zh",
            "z",
            "i",
            "y",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "kh",
            "ts",
            "ch",
            "sh",
            "shch",
            "'",
            "y",
            "'",
            "e",
            "yu",
            "ya",
        ],
        strict=True,
    )
)


class MatchSettings(Contract):
    site_distance_km: float = Field(default=3, gt=0)
    site_similarity: float = Field(default=0.85, ge=0, le=1)
    link_distance_km: float = Field(default=30, gt=0)
    designation_types: dict[str, str] = Field(default_factory=dict)
    honorifics: list[str] = Field(default_factory=list)
    branch_site_types: dict[str, list[str]] = Field(default_factory=dict)
    osm_site_type_hints: dict[str, str] = Field(default_factory=dict)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = "".join(CYRILLIC.get(character, character) for character in value)
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))


def designation(value: str, settings: MatchSettings) -> tuple[str, list[str]]:
    normalized = normalize(value)
    honors = [h for h in settings.honorifics if normalize(h) in normalized]
    for honor in honors:
        normalized = normalized.replace(normalize(honor), " ")
    for alias, canonical in sorted(settings.designation_types.items(), key=lambda p: -len(p[0])):
        normalized = re.sub(
            r"(?<!\w)" + re.escape(normalize(alias)) + r"(?!\w)", canonical, normalized
        )
    normalized = re.sub(r"\b([0-9]+)(st|nd|rd|th|ya|y|yy)\b", r"\1", normalized)
    return " ".join(normalized.split()), honors


def distance(left: Record, right: Record) -> float:
    if left.latitude is None or right.latitude is None:
        return math.inf
    assert left.longitude is not None and right.longitude is not None
    lat1, lat2 = math.radians(left.latitude), math.radians(right.latitude)
    delta = math.radians(right.longitude - left.longitude)
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def site_match(left: Record, right: Record, settings: MatchSettings) -> dict[str, Any] | None:
    from rapidfuzz.fuzz import ratio

    if left.country != right.country or left.kind != "site" or right.kind != "site":
        return None
    for key in ("wikidata", "icao", "osm_id"):
        value = left.attributes.get(key)
        if value and str(value).casefold() == str(right.attributes.get(key, "")).casefold():
            return {"reason": key, "score": 1.0, "distance_km": finite_distance(left, right)}
    similarity = ratio(normalize(left.name), normalize(right.name)) / 100
    separation = distance(left, right)
    if separation < settings.site_distance_km and similarity >= settings.site_similarity:
        return {"reason": "name_and_distance", "score": similarity, "distance_km": separation}
    return None


def finite_distance(left: Record, right: Record) -> float | None:
    value = distance(left, right)
    return value if math.isfinite(value) else None


def geocode(town: str, country: str, region: str | None, places: list[Record]) -> list[Record]:
    key = normalize(town)
    return [
        p
        for p in places
        if p.country == country
        and (region is None or p.region == region)
        and key in {normalize(n) for n in [p.name, *p.aliases]}
    ]


def unit_match(left: Record, right: Record, settings: MatchSettings) -> bool:
    if left.kind != "unit" or right.kind != "unit" or left.country != right.country:
        return False
    if left.attributes.get("wikidata") and left.attributes["wikidata"] == right.attributes.get(
        "wikidata"
    ):
        return True
    branch = left.attributes.get("branch")
    return bool(
        branch
        and branch == right.attributes.get("branch")
        and designation(str(left.attributes.get("designation", left.name)), settings)[0]
        == designation(str(right.attributes.get("designation", right.name)), settings)[0]
    )
