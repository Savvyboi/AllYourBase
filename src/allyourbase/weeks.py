"""ISO weeks as UTC half-open intervals, avoiding year-boundary ambiguity."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass(frozen=True, order=True)
class ISOWeek:
    monday: date

    def __post_init__(self) -> None:
        if self.monday.weekday() != 0:
            raise ValueError("ISOWeek must begin on Monday")

    @classmethod
    def parse(cls, value: str) -> "ISOWeek":
        if not re.fullmatch(r"\d{4}-W\d{2}", value):
            raise ValueError("week must use YYYY-Www, for example 2024-W01")
        return cls(date.fromisocalendar(int(value[:4]), int(value[6:]), 1))

    @classmethod
    def containing(cls, value: date) -> "ISOWeek":
        return cls(value - timedelta(days=value.weekday()))

    @property
    def start(self) -> datetime:
        return datetime.combine(self.monday, datetime.min.time(), UTC)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(weeks=1)

    def shift(self, weeks: int) -> "ISOWeek":
        return ISOWeek(self.monday + timedelta(weeks=weeks))

    def __str__(self) -> str:
        year, week, _ = self.monday.isocalendar()
        return f"{year:04d}-W{week:02d}"


def week_range(start: ISOWeek, end: ISOWeek) -> list[ISOWeek]:
    """Inclusive week labels; each individual interval is [Monday, next Monday)."""
    if end < start:
        raise ValueError("end week is before start week")
    weeks = (end.monday - start.monday).days // 7
    return [start.shift(offset) for offset in range(weeks + 1)]
