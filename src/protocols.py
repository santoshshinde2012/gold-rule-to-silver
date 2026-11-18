"""The interface every Gold report implements. The scenario treats reports only through it."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class Report(Protocol):
    """A Gold report. It returns one answer per order it reports on."""

    @property
    def name(self) -> str: ...

    def answer(self, changes: pd.DataFrame) -> dict[int, int | str]: ...
