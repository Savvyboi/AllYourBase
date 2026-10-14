"""Durable reservations; ambiguous charges remain reserved rather than becoming zero."""

import json
import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from allyourbase.models.settings import Settings
from allyourbase.providers.contracts import ProviderError


class BudgetLedger:
    def __init__(self, workspace: Path, settings: Settings) -> None:
        self.directory = workspace / "usage"
        self.path = self.directory / "radar-budget.json"
        self.settings = settings

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = self.directory / "radar-budget.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ProviderError("budget_ledger_locked", "radar") from None
        try:
            os.write(descriptor, str(os.getpid()).encode())
            os.close(descriptor)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                raise ValueError
            for record in records:
                if not isinstance(record, dict) or not isinstance(record.get("month"), str):
                    raise ValueError
                reserved = record["reserved_pu"]
                actual = record["actual_pu"]
                if (
                    not isinstance(reserved, (int, float))
                    or not math.isfinite(reserved)
                    or reserved <= 0
                ):
                    raise ValueError
                if actual is not None and (
                    not isinstance(actual, (int, float)) or not math.isfinite(actual) or actual < 0
                ):
                    raise ValueError
            return records
        except (OSError, ValueError, KeyError, TypeError):
            raise ProviderError("invalid_budget_ledger", "radar") from None

    def _write(self, records: list[dict[str, Any]]) -> None:
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(records, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.path)

    def reserve(self, provider: str, scene_id: str, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        month = now.astimezone(UTC).strftime("%Y-%m")
        reservation = self.settings.access.radar_request_reservation_pu
        limit = (
            self.settings.budgets.monthly_processing_units
            * self.settings.budgets.stop_optional_at_fraction
        )
        with self._lock():
            records = self._read()
            used = sum(
                r["actual_pu"] if r["actual_pu"] is not None else r["reserved_pu"]
                for r in records
                if r["month"] == month
            )
            if used + reservation > limit:
                raise ProviderError("monthly_budget_limit", provider)
            identifier = uuid4().hex
            records.append(
                {
                    "id": identifier,
                    "provider": provider,
                    "scene_id": scene_id,
                    "month": month,
                    "requested_at": now.isoformat(),
                    "reserved_pu": reservation,
                    "actual_pu": None,
                    "status": "reserved",
                }
            )
            self._write(records)
        return identifier

    def finish(self, identifier: str, actual_pu: float | None, status: str) -> None:
        if actual_pu is not None and (not math.isfinite(actual_pu) or actual_pu < 0):
            raise ValueError("processing units must be finite and nonnegative")
        with self._lock():
            records = self._read()
            matching = [r for r in records if r["id"] == identifier]
            if len(matching) != 1:
                raise ProviderError("unknown_budget_reservation", "radar")
            matching[0]["actual_pu"] = actual_pu
            matching[0]["status"] = status
            self._write(records)
