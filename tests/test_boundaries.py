"""Contracts at the core/storage and Silver/Gold boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.models import CHANGE_COLUMNS, CurrentState
from src.reports import OperationsAfter, SalesAfter
from src.repository import SilverOrderChanges
from src.scenario import run_scenario
from src.silver_rule_demo import run


class MemoryChanges:
    """A versioned fake with nonzero versions, requiring no Delta adapter."""

    def __init__(self) -> None:
        self.snapshots: dict[int, pd.DataFrame] = {}
        self.read_versions: list[int] = []

    def replace(self, rows: list[dict[str, Any]]) -> int:
        self.snapshots[7] = pd.DataFrame(rows, columns=CHANGE_COLUMNS)
        return 7

    def append(self, rows: list[dict[str, Any]]) -> int:
        self.snapshots[8] = pd.concat([self.snapshots[7], pd.DataFrame(rows)], ignore_index=True)
        return 8

    def read(self, version: int | None = None) -> pd.DataFrame:
        resolved = max(self.snapshots) if version is None else version
        self.read_versions.append(resolved)
        return self.snapshots[resolved].copy()


def test_core_uses_injected_store_and_explains_latest_data_from_latest_state() -> None:
    store = MemoryChanges()
    seed = {
        "first_load": [
            {"order_id": 1, "source_seq": 1, "op": "upsert", "status": "accepted", "amount": 10, "arrived_at": "09:00"}
        ],
        "later_arrival": [
            {
                "order_id": 1,
                "source_seq": 2,
                "op": "upsert",
                "status": "cancelled",
                "amount": 10,
                "arrived_at": "10:00",
            },
            {"order_id": 2, "source_seq": 1, "op": "upsert", "status": "accepted", "amount": 5, "arrived_at": "10:00"},
        ],
    }
    result = run_scenario(store, seed)
    assert result["versions"] == {"pinned": 7, "latest": 8}
    assert store.read_versions == [7, 8]
    assert result["sales_after"] == {1: 10}
    assert result["change_log"] == []
    assert result["unpinned_sales_changes"] == [
        (1, "cancelled by the source; source order wins over arrival"),
        (2, "new in Silver"),
    ]


def test_after_reports_consume_supplied_state_and_keep_their_own_filters() -> None:
    state = CurrentState(
        orders=[
            {"order_id": 1, "status": "accepted", "amount": 10},
            {"order_id": 2, "status": "cancelled", "amount": 7},
        ],
        exceptions=[3],
    )
    assert SalesAfter().answer(state) == {1: 10}
    assert OperationsAfter().answer(state) == {1: "accepted 10", 2: "cancelled 7"}
    assert SalesAfter().answer(CurrentState([], [])) == {}
    assert OperationsAfter().answer(CurrentState([], [])) == {}


def test_rerun_preserves_pinned_versions_and_unrelated_lake_files(tmp_path: Path) -> None:
    marker = tmp_path / "notes.txt"
    marker.write_text("Keep this file", encoding="utf-8")
    other_table = tmp_path / "bronze_order_changes"
    other_table.mkdir()
    other_marker = other_table / "unrelated.txt"
    other_marker.write_text("Keep this table", encoding="utf-8")

    first = run(tmp_path)
    store = SilverOrderChanges(tmp_path)
    pinned = store.read(first["versions"]["pinned"])
    latest = store.read(first["versions"]["latest"])
    assert len(pinned) == 11
    assert len(latest) == 12
    assert 6 not in set(pinned["order_id"])
    assert 6 in set(latest["order_id"])

    second = run(tmp_path)
    assert second["versions"]["pinned"] > first["versions"]["latest"]
    pd.testing.assert_frame_equal(store.read(first["versions"]["pinned"]), pinned)
    assert marker.read_text(encoding="utf-8") == "Keep this file"
    assert other_marker.read_text(encoding="utf-8") == "Keep this table"
    manifest = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert manifest["versions"] == second["versions"]
    assert len(manifest["seed_sha256"]) == 64
