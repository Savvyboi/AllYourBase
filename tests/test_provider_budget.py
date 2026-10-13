import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from allyourbase.models.settings import Settings
from allyourbase.providers.budget import BudgetLedger
from allyourbase.providers.contracts import ProviderError


def test_unknown_charges_stay_reserved(tmp_path: Path, settings: Settings) -> None:
    settings.budgets.monthly_processing_units = 100
    settings.budgets.stop_optional_at_fraction = 1
    settings.access.radar_request_reservation_pu = 60
    ledger = BudgetLedger(tmp_path, settings)
    reservation = ledger.reserve("test", "synthetic-scene")
    ledger.finish(reservation, None, "network_error")
    with pytest.raises(ProviderError, match="monthly_budget_limit"):
        ledger.reserve("test", "second-scene")
    record = json.loads(ledger.path.read_text())[0]
    assert record["actual_pu"] is None
    assert record["reserved_pu"] == 60


def test_measured_charge_replaces_reservation(tmp_path: Path, settings: Settings) -> None:
    settings.budgets.monthly_processing_units = 100
    settings.budgets.stop_optional_at_fraction = 1
    settings.access.radar_request_reservation_pu = 60
    ledger = BudgetLedger(tmp_path, settings)
    reservation = ledger.reserve("test", "synthetic-scene")
    ledger.finish(reservation, 1.5, "ok")
    ledger.reserve("test", "second-scene")
    assert len(json.loads(ledger.path.read_text())) == 2


def test_month_is_utc_and_previous_month_not_counted(tmp_path: Path, settings: Settings) -> None:
    settings.budgets.monthly_processing_units = 60
    settings.budgets.stop_optional_at_fraction = 1
    settings.access.radar_request_reservation_pu = 60
    ledger = BudgetLedger(tmp_path, settings)
    ledger.reserve("test", "old", datetime(2026, 9, 30, 23, 59, tzinfo=UTC))
    ledger.reserve("test", "new", datetime(2026, 10, 1, tzinfo=UTC))
    assert [r["month"] for r in json.loads(ledger.path.read_text())] == ["2026-09", "2026-10"]


def test_corrupt_ledger_fails_closed(tmp_path: Path, settings: Settings) -> None:
    ledger = BudgetLedger(tmp_path, settings)
    ledger.directory.mkdir()
    ledger.path.write_text('[{"month": "2026-10", "reserved_pu": -1, "actual_pu": null}]')
    with pytest.raises(ProviderError, match="invalid_budget_ledger"):
        ledger.reserve("test", "synthetic-scene")


def test_busy_ledger_never_starts_request(tmp_path: Path, settings: Settings) -> None:
    ledger = BudgetLedger(tmp_path, settings)
    ledger.directory.mkdir()
    (ledger.directory / "radar-budget.lock").write_text("already-running")
    with pytest.raises(ProviderError, match="budget_ledger_locked"):
        ledger.reserve("test", "synthetic-scene")
    assert not ledger.path.exists()
