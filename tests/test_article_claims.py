"""Lock every result the article quotes from the local run."""

from __future__ import annotations

WINS = "cancelled by the source; source order wins over arrival"
HELD = "conflict at the same source position; held for review"


def test_copied_rules_give_two_answers_for_the_same_order(result):
    assert result["order_2_before"] == {"sales": 60, "operations": "cancelled 60"}
    assert result["order_4_before"] == {"sales": 45, "operations": "accepted 40"}


def test_shared_current_state(result):
    assert result["current_state"] == {1: "accepted 100", 2: "cancelled 60", 3: "accepted 70"}
    assert result["exceptions"] == [4]


def test_sales_total_and_change_log(result):
    assert result["sales_total"] == {"before": 275, "after": 170}
    assert result["change_log"] == [
        ("sales", 2, 60, None, WINS),
        ("sales", 4, 45, None, HELD),
        ("operations", 4, "accepted 40", None, HELD),
    ]


def test_unpinned_comparison_adds_a_change_that_is_not_a_rule_change(result):
    assert result["unpinned_sales_changes"] == [(2, WINS), (4, HELD), (6, "new in Silver")]


def test_report_filter_stays_in_gold(result):
    assert result["cancelled_in_operations"] == {"filter in Gold": 1, "filter moved to Silver": 0}
