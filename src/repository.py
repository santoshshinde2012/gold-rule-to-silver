"""Silver order changes as a local Delta table (open-source `deltalake`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from .models import CHANGE_COLUMNS

SCHEMA = pa.schema(
    [
        ("order_id", pa.int64()),
        ("source_seq", pa.int64()),
        ("op", pa.string()),
        ("status", pa.string()),
        ("amount", pa.int64()),
        ("arrived_at", pa.string()),
    ]
)


class SilverOrderChanges:
    """Every change the source sent, appended in arrival order."""

    def __init__(self, root: Path) -> None:
        self.path = str(root / "silver_order_changes")

    def replace(self, rows: list[dict[str, Any]]) -> int:
        """Start a fresh demo snapshot without deleting the table or its history."""
        table = pa.Table.from_pylist(rows, schema=SCHEMA)
        write_deltalake(self.path, table, mode="overwrite")
        return self.version()

    def append(self, rows: list[dict[str, Any]]) -> int:
        table = pa.Table.from_pylist(rows, schema=SCHEMA)
        if Path(self.path).exists():
            write_deltalake(self.path, table, mode="append")
        else:
            write_deltalake(self.path, table, mode="overwrite")
        return self.version()

    def version(self) -> int:
        return DeltaTable(self.path).version()

    def read(self, version: int | None = None) -> pd.DataFrame:
        return DeltaTable(self.path, version=version).to_pandas()[CHANGE_COLUMNS]
