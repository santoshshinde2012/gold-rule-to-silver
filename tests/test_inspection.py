"""Evidence must describe persisted snapshots without trusting cached answers or writing to the lake."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.inspection import export_report, inspect_lake, render_report
from src.silver_rule_demo import run


def _file_digests(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_export_reads_persisted_versions_and_preserves_every_source_file(tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    run(lake)
    result = run(lake)
    manifest_path = lake / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sales_total"] = {"before": -1, "after": -1}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = _file_digests(lake)

    output = tmp_path / "evidence"
    snapshot = export_report(lake, output)

    assert _file_digests(lake) == before
    assert snapshot["versions"] == result["versions"] == {"pinned": 2, "latest": 3}
    assert snapshot["history"]["pinned_row_count"] == 11
    assert snapshot["history"]["latest_row_count"] == 12
    assert snapshot["result"]["sales_total"] == {"before": 275, "after": 170}
    assert snapshot["result"]["change_log"] == result["change_log"]
    assert snapshot["current_state"]["deleted_orders"] == [5]
    assert snapshot["new_order_ids"] == [6]
    saved = json.loads((output / "tables.json").read_text(encoding="utf-8"))
    assert saved["history"]["pinned_records"] == snapshot["history"]["pinned_records"]
    assert "275 → 170" in (output / "index.html").read_text(encoding="utf-8")
    assert "held for review" in (output / "demo.txt").read_text(encoding="utf-8")


def test_explicit_pin_without_manifest_and_latest_pin_has_no_new_order(tmp_path: Path) -> None:
    result = run(tmp_path)
    (tmp_path / "run.json").unlink()
    with pytest.raises(ValueError, match="pinned-version"):
        inspect_lake(tmp_path)
    snapshot = inspect_lake(tmp_path, result["versions"]["latest"])
    assert snapshot["new_order_ids"] == []
    assert snapshot["result"]["sales_total"]["after"] == 260
    assert "relative to the pinned input: none" in render_report(snapshot)


def test_export_rejects_output_inside_either_read_only_lake(tmp_path: Path) -> None:
    lake, related = tmp_path / "lake", tmp_path / "related"
    with pytest.raises(ValueError, match="outside the source lakes"):
        export_report(lake, lake / "evidence")
    with pytest.raises(ValueError, match="outside the source lakes"):
        export_report(lake, related / "evidence", related_lake=related)
