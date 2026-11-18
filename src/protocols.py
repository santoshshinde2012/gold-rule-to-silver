"""Small contracts for reports and the versioned change store."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

import pandas as pd

ReportInput = TypeVar("ReportInput", contravariant=True)
ReportValue = TypeVar("ReportValue", covariant=True)


class Report(Protocol[ReportInput, ReportValue]):
    """One answer per order, with explicit input and answer types."""

    @property
    def name(self) -> str: ...

    def answer(self, source: ReportInput) -> Mapping[int, ReportValue]: ...


class ChangeStore(Protocol):
    """Only the versioned storage operations the scenario needs."""

    def replace(self, rows: list[dict[str, Any]]) -> int: ...

    def append(self, rows: list[dict[str, Any]]) -> int: ...

    def read(self, version: int | None = None) -> pd.DataFrame: ...
