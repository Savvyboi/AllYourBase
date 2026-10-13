from datetime import UTC, date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from allyourbase.weeks import ISOWeek, week_range


@pytest.mark.parametrize(
    ("label", "monday"),
    [
        ("2020-W53", date(2020, 12, 28)),
        ("2021-W01", date(2021, 1, 4)),
        ("2026-W01", date(2025, 12, 29)),
    ],
)
def test_iso_year_edges(label: str, monday: date) -> None:
    week = ISOWeek.parse(label)
    assert week.monday == monday
    assert str(week) == label
    assert week.start.tzinfo == UTC
    assert week.end - week.start == timedelta(days=7)


@pytest.mark.parametrize("label", ["2021-W53", "2026-W00", "2026-W54", "2026-W1", "bad"])
def test_invalid_week(label: str) -> None:
    with pytest.raises(ValueError):
        ISOWeek.parse(label)


def test_inclusive_range_across_week_53() -> None:
    weeks = week_range(ISOWeek.parse("2020-W52"), ISOWeek.parse("2021-W02"))
    assert list(map(str, weeks)) == ["2020-W52", "2020-W53", "2021-W01", "2021-W02"]
    assert weeks[0].end == weeks[1].start


def test_reversed_range() -> None:
    with pytest.raises(ValueError, match="before start"):
        week_range(ISOWeek.parse("2021-W02"), ISOWeek.parse("2021-W01"))


@given(st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)))
def test_week_roundtrip(day: date) -> None:
    week = ISOWeek.containing(day)
    assert ISOWeek.parse(str(week)) == week
    assert week.monday <= day < week.monday + timedelta(days=7)
