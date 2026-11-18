"""Export reproducible HTML and JSON evidence from existing versioned Delta rows."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import deltalake
import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable
from deltalake.exceptions import DeltaError

from .compare import change_log
from .models import CHANGE_COLUMNS, CurrentState
from .reports import OperationsAfter, OperationsBefore, SalesAfter, SalesBefore, cancelled_count
from .rules import current_state
from .silver_rule_demo import CODE_ROOT, report


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def inspect_related_lake(root: Path) -> dict[str, Any]:
    """Inspect the separate repair demo without importing it or writing to its lake.

    Versions are fixed before reading each table. Stop concurrent writers if a
    consistent snapshot across these independent tables is required.
    """
    tables: dict[str, Any] = {}
    frames: dict[str, pd.DataFrame] = {}
    for name, columns in (
        ("bronze_order_changes", ["order_id", "seq"]),
        ("silver_orders", ["order_id"]),
        ("gold_daily_order_totals", ["order_date", "status"]),
    ):
        table = DeltaTable(str(root / name))
        frame = table.to_pandas().sort_values(columns).reset_index(drop=True)
        frames[name] = frame
        tables[name] = {"version": table.version(), "row_count": len(frame), "records": _records(frame)}
    expected = (
        frames["silver_orders"]
        .groupby(["order_date", "status"])
        .size()
        .reset_index(name="orders")
        .sort_values(["order_date", "status"])
        .reset_index(drop=True)
    )
    gold = frames["gold_daily_order_totals"]
    return {
        "source": f"{root.parent.name}/{root.name}",
        "scope": "Separate repair demo; different schemas; read-only inspection",
        "tables": tables,
        "gold_matches_silver": _records(gold) == _records(expected),
        "gold_total_orders": int(gold["orders"].sum()),
    }


def inspect_lake(root: Path, pinned_version: int | None = None) -> dict[str, Any]:
    """Read existing Delta snapshots and compute both report paths on one version.

    The run manifest identifies the comparison version, which need not be zero
    after a rerun. An explicit version also supports lakes without a manifest.
    """
    manifest_file = root / "run.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    if pinned_version is None:
        pinned_version = manifest.get("versions", {}).get("pinned")
    if not isinstance(pinned_version, int) or pinned_version < 0:
        raise ValueError("Run the demo first, or supply a nonnegative --pinned-version.")
    table_path = root / "silver_order_changes"
    latest_table = DeltaTable(str(table_path))
    latest_version = latest_table.version()
    pinned = DeltaTable(str(table_path), version=pinned_version).to_pandas()[CHANGE_COLUMNS]
    latest = latest_table.to_pandas()[CHANGE_COLUMNS]
    state, latest_state = current_state(pinned), current_state(latest)
    sales_old, sales_new = SalesBefore().answer(pinned), SalesAfter().answer(state)
    ops_old, ops_new = OperationsBefore().answer(pinned), OperationsAfter().answer(state)
    changes = change_log("sales", sales_old, sales_new, state) + change_log("operations", ops_old, ops_new, state)
    unpinned = change_log("sales", sales_old, SalesAfter().answer(latest_state), latest_state)
    filtered_state = CurrentState(
        orders=[row for row in state.orders if row["status"] == "accepted"], exceptions=state.exceptions
    )
    orders = sorted(set(sales_old) | set(sales_new) | set(ops_old) | set(ops_new) | set(state.exceptions))
    comparison = [
        {
            "order_id": key,
            "sales_before": sales_old.get(key),
            "sales_after": sales_new.get(key),
            "operations_before": ops_old.get(key),
            "operations_after": ops_new.get(key),
            "disposition": "held for review" if key in state.exceptions else "current",
        }
        for key in orders
    ]
    # Sorting source rows makes the exported digest independent of Parquet file order.
    history = _records(pinned.sort_values(["order_id", "source_seq", "arrived_at"]))
    result = {
        "deltalake": deltalake.__version__,
        "order_2_before": {"sales": sales_old.get(2), "operations": ops_old.get(2)},
        "order_4_before": {"sales": sales_old.get(4), "operations": ops_old.get(4)},
        "current_state": {row["order_id"]: f"{row['status']} {int(row['amount'])}" for row in state.orders},
        "exceptions": state.exceptions,
        "sales_total": {"before": sum(sales_old.values()), "after": sum(sales_new.values())},
        "change_log": [(c.report, c.order_id, c.old, c.new, c.reason) for c in changes],
        "unpinned_sales_changes": [(c.order_id, c.reason) for c in unpinned],
        "cancelled_in_operations": {
            "filter in Gold": cancelled_count(ops_new),
            "filter moved to Silver": cancelled_count(OperationsAfter().answer(filtered_state)),
        },
    }
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": "Synthetic order events in a real local Delta table",
        "source": str(table_path.resolve().relative_to(CODE_ROOT))
        if table_path.resolve().is_relative_to(CODE_ROOT)
        else str(table_path.resolve()),
        "runtime": {
            "python": platform.python_version(),
            "deltalake": deltalake.__version__,
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
        },
        "versions": {"pinned": pinned_version, "latest": latest_version},
        "history": {
            "pinned_row_count": len(pinned),
            "latest_row_count": len(latest),
            "pinned_records": history,
            "latest_records": _records(latest.sort_values(["order_id", "source_seq", "arrived_at"])),
            "pinned_sha256": hashlib.sha256(json.dumps(history, sort_keys=True).encode()).hexdigest(),
        },
        "current_state": {
            "records": state.orders,
            "exceptions": state.exceptions,
            "deleted_orders": sorted(
                set(int(key) for key in pinned["order_id"])
                - {row["order_id"] for row in state.orders}
                - set(state.exceptions)
            ),
        },
        "new_order_ids": sorted(
            set(int(key) for key in latest["order_id"]) - set(int(key) for key in pinned["order_id"])
        ),
        "comparison": comparison,
        "changes": [asdict(change) for change in changes],
        "result": result,
    }


def _display(value: Any) -> str:
    """Present nullable whole-number amounts without pandas' decimal suffix."""
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    headings = "".join(f'<th scope="col">{html.escape(label)}</th>' for _, label in columns)
    rows = []
    for record in records:
        cells = "".join(f"<td>{html.escape(_display(record.get(key)))}</td>" for key, _ in columns)
        highlight = ' class="review"' if record.get("disposition") == "held for review" else ""
        rows.append(f"<tr{highlight}>{cells}</tr>")
    return f"<table><thead><tr>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_report(snapshot: dict[str, Any]) -> str:
    """Render the evidence sheet using exported rows, without external assets."""
    result, versions, history = snapshot["result"], snapshot["versions"], snapshot["history"]
    state = snapshot["current_state"]
    deleted = ", ".join(str(key) for key in state["deleted_orders"]) or "none"
    added = ", ".join(str(key) for key in snapshot["new_order_ids"]) or "none"
    shared = _table(
        state["records"],
        [("order_id", "Order"), ("source_seq", "Source seq"), ("status", "Status"), ("amount", "Amount")],
    )
    comparison = _table(
        snapshot["comparison"],
        [
            ("order_id", "Order"),
            ("sales_before", "Sales before"),
            ("sales_after", "Sales after"),
            ("operations_before", "Operations before"),
            ("operations_after", "Operations after"),
            ("disposition", "Decision"),
        ],
    )
    changes = _table(
        snapshot["changes"],
        [("report", "Report"), ("order_id", "Order"), ("old", "Before"), ("new", "After"), ("reason", "Reason")],
    )
    review = _table(
        [row for row in history["pinned_records"] if row["order_id"] in state["exceptions"]],
        [("order_id", "Order"), ("source_seq", "Seq"), ("amount", "Amount"), ("arrived_at", "Arrival")],
    )
    source = _table(history["pinned_records"], [(column, column) for column in CHANGE_COLUMNS])
    related = ""
    if "related_lake" in snapshot:
        lake = snapshot["related_lake"]
        rows = [
            {"table": name, "version": f"v{table['version']}", "rows": table["row_count"]}
            for name, table in lake["tables"].items()
        ]
        inventory = _table(rows, [("table", "Delta table"), ("version", "Version"), ("rows", "Rows")])
        match = "matches" if lake["gold_matches_silver"] else "DIFFERS FROM"
        related = f"""<section><div class="section-title"><h2>Related lake / separate repair example</h2>
<span>READ ONLY</span></div><p><code>{html.escape(lake["source"])}</code> uses different schemas.
Its Gold aggregation {match} its Silver rows and counts {lake["gold_total_orders"]} orders.</p>{inventory}</section>"""
    runtime = " · ".join(f"{key} {value}" for key, value in snapshot["runtime"].items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gold Rule to Silver — execution evidence</title><style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f7fa; color:#172d3c;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif; }}
main {{ max-width:1440px; padding:38px 48px 30px; margin:auto; }}
header {{ border-bottom:2px solid #172d3c; padding-bottom:20px; }}
.eyebrow,.section-title span {{ font:600 12px ui-monospace,Menlo,monospace; letter-spacing:1px; color:#466377; }}
.eyebrow {{ display:flex; justify-content:space-between; }}
h1 {{ font-size:39px; letter-spacing:-1.1px; margin:17px 0 10px; }}
p {{ color:#526777; font-size:14px; line-height:1.6; margin:8px 0 15px; }}
header p {{ font-size:16px; margin-bottom:0; }}
.metrics {{ display:grid; grid-template-columns:1.25fr 1fr 1fr 1.1fr; gap:16px; margin:22px 0; }}
.metric {{ border:1px solid #dbe3e9; background:white; padding:15px 20px; border-radius:7px; }}
.metric span {{ display:block; color:#526777; font-size:12px; margin-bottom:9px; }}
.metric strong {{ font-size:28px; color:#08685e; letter-spacing:-.6px; }}
.metric small {{ display:block; color:#526777; font-size:11px; margin-top:7px; }}
.metric.review strong {{ color:#9b5c13; }}
.grid {{ display:grid; grid-template-columns:1.12fr 1fr; gap:22px; }}
section {{ background:#fff; border:1px solid #dbe3e9; border-radius:7px; padding:20px 22px; margin-bottom:20px; }}
.section-title {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
h2 {{ font-size:19px; font-weight:650; letter-spacing:-.3px; margin:0; }}
table {{ width:100%; border-collapse:collapse; text-align:left; }}
th {{ font-size:11px; color:#526777; border-top:1px solid #aec0cc; border-bottom:1px solid #aec0cc; }}
td,th {{ padding:10px 11px; }}
td {{ font:13px ui-monospace,Menlo,monospace; border-bottom:1px solid #e4eaf0; line-height:1.45; }}
tr:last-child td {{ border-bottom:0; }}
tr.review td {{ background:#fff6e9; color:#875116; }}
.note {{ margin-bottom:0; font-size:12px; }}
code {{ font:12px ui-monospace,Menlo,monospace; }}
footer {{ padding-top:2px; color:#526777; font-size:11px; line-height:1.8; }}
details {{ margin:18px 0; }} summary {{ cursor:pointer; color:#08685e; font-size:13px; }}
details table {{ margin-top:16px; background:white; }}
a {{ color:#08685e; }}
@media(max-width:900px) {{ main {{ padding:24px; }} .grid,.metrics {{ grid-template-columns:1fr; }}
section {{ overflow-x:auto; }} h1 {{ font-size:30px; }} }}
</style></head><body><main>
<header><div class="eyebrow"><span>GOLD RULE TO SILVER / EXECUTION EVIDENCE</span>
<span>REAL DELTA ROWS · SYNTHETIC DATA</span></div><h1>One shared rule. Consistent report answers.</h1>
<p>Before and after computed from the same pinned Delta version.
The source history is persisted; current state and Gold reports are computed in pandas.</p></header>
<div class="metrics">
<div class="metric"><span>Accepted sales total</span>
<strong>{result["sales_total"]["before"]} → {result["sales_total"]["after"]}</strong>
<small>Rule correction on unchanged input</small></div>
<div class="metric"><span>Shared current state</span><strong>{len(state["records"])} orders</strong>
<small>Includes {result["cancelled_in_operations"]["filter in Gold"]} cancelled order for operations</small></div>
<div class="metric review"><span>Held for review</span><strong>{len(state["exceptions"])} order</strong>
<small>Conflicting source versions are withheld</small></div>
<div class="metric"><span>Pinned → latest history</span><strong>v{versions["pinned"]} → v{versions["latest"]}</strong>
<small>{history["pinned_row_count"]} → {history["latest_row_count"]} persisted change rows</small></div></div>
<div class="grid"><section><div class="section-title"><h2>Shared Silver current state</h2><span>COMPUTED</span></div>
<p>Exact repeats collapse; highest source position wins; deletes remove an order.</p>{shared}
<p class="note">The accepted-only sales filter stays in Gold. Operations retains cancellations.</p></section>
<section><div class="section-title"><h2>Review evidence</h2><span>WITHHELD</span></div>
<p>Source changes for the held order(s). Conflicts at the winning position require a decision.</p>{review}
<p class="note">Deleted order IDs: {deleted}.
Deleted orders are absent from the shared current state.</p></section></div>
<section><div class="section-title"><h2>Report answers / same pinned version</h2>
<span>v{versions["pinned"]}</span></div>
<p>“—” means the report has no answer for that order. Gold filters remain report specific.</p>{comparison}</section>
<section><div class="section-title"><h2>Migration change log</h2><span>KEY BY KEY</span></div>
<p>Every changed answer has an explanation derived from the shared state at the comparison version.</p>{changes}
<p class="note">New order IDs in v{versions["latest"]} relative to the pinned input: {added}.
Changes in input must not be counted as a rule change.</p></section>
{related}
<details><summary>Inspect all {history["pinned_row_count"]} persisted source rows
at pinned v{versions["pinned"]}</summary>{source}</details>
<footer>Captured {html.escape(snapshot["captured_at"])} · {html.escape(runtime)}<br>
Read-only export from <code>{html.escape(snapshot["source"])}</code> ·
<a href="tables.json">Full rows and provenance (JSON)</a> · <a href="demo.txt">Scenario output</a><br>
Pinned row SHA-256: <code>{history["pinned_sha256"]}</code></footer>
</main></body></html>"""


def export_report(
    root: Path, output: Path, pinned_version: int | None = None, related_lake: Path | None = None
) -> dict[str, Any]:
    """Finish all reads before writing artifacts; never modify either source lake."""
    if output.resolve().is_relative_to(root.resolve()) or (
        related_lake is not None and output.resolve().is_relative_to(related_lake.resolve())
    ):
        raise ValueError("Choose an output directory outside the source lakes to keep inspection read only.")
    snapshot = inspect_lake(root, pinned_version)
    if related_lake is not None:
        snapshot["related_lake"] = inspect_related_lake(related_lake)
    document = render_report(snapshot)
    output.mkdir(parents=True, exist_ok=True)
    (output / "tables.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    (output / "index.html").write_text(document, encoding="utf-8")
    (output / "demo.txt").write_text("\n".join(report(snapshot["result"])) + "\n", encoding="utf-8")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=CODE_ROOT / "lake", help="Existing lake; never recreated")
    parser.add_argument("--output", type=Path, default=CODE_ROOT / "docs" / "results")
    parser.add_argument("--pinned-version", type=int, help="Override the version recorded in lake/run.json")
    parser.add_argument("--related-lake", type=Path, help="Optional separate bronze-to-silver-repair lake (read only)")
    args = parser.parse_args()
    try:
        export_report(args.lake, args.output, args.pinned_version, args.related_lake)
    except (DeltaError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Cannot export results: {exc}\nRun the demo first or select an existing lake.\n")
    print(f"Exported read-only Delta evidence to {args.output}")


if __name__ == "__main__":
    main()
