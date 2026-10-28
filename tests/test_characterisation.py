"""Characterisation tests for clean_rows and build_summary (exercise 03).

These record what the code does *today*, not what it should do. Tests marked
`# BUG?` pin down behaviour that looks wrong - expect them to change when the
ticket they mention is fixed.

All input rows are written by hand so every expected value can be checked
without looking at the real data files.
"""

import pytest

from kettle.report import build_summary
from kettle.transform import clean_rows

# --- clean_rows ---------------------------------------------------------------
# Leeds, York and Manchester rows: transaction_id, timestamp, till_id, product, quantity, unit_price
# Dublin rows:                     timestamp, product, unit_price, quantity, till_id, transaction_id


def test_leeds_row_is_cleaned():
    rows = [["LDS-1", "14/09/2026 08:15", "T1", " flat white ", "2", "3.40"]]

    assert clean_rows(rows, "leeds") == [
        {
            "transaction_id": "LDS-1",
            "branch": "leeds",
            "sold_at": "2026-09-14T08:15:00",
            "till_id": "T1",
            "product": "Flat White",
            "quantity": 2,
            "unit_price_pence": 340,
            "line_total_pence": 680,
        }
    ]


def test_york_uses_day_first_timestamps_like_leeds():
    rows = [["YRK-1", "01/02/2026 09:00", "T1", "Latte", "1", "3.50"]]

    [row] = clean_rows(rows, "york")

    assert row["sold_at"] == "2026-02-01T09:00:00"  # 1st Feb, not 2nd Jan
    assert row["unit_price_pence"] == 350


def test_manchester_prices_are_already_in_pence_and_timestamps_are_iso():
    rows = [["MAN-1", "2026-09-14T08:15:00", "T1", "Latte", "2", "350"]]

    [row] = clean_rows(rows, "manchester")

    assert row["sold_at"] == "2026-09-14T08:15:00"
    assert row["unit_price_pence"] == 350
    assert row["line_total_pence"] == 700


def test_dublin_columns_are_reordered_and_price_is_multiplied_by_rate():
    # 1 item at EUR 10.00, rate 1.25 (EUR per GBP, as in data/raw/exchange_rates).
    # BUG? see KC-101: EUR 10.00 / 1.25 = GBP 8.00 (800p), but the code multiplies
    # and records GBP 12.50 (1250p).
    rows = [["2026-09-14T08:15:00", "Latte", "10.00", "1", "T1", "DUB-1"]]

    assert clean_rows(rows, "dublin", eur_rate=1.25) == [
        {
            "transaction_id": "DUB-1",
            "branch": "dublin",
            "sold_at": "2026-09-14T08:15:00",
            "till_id": "T1",
            "product": "Latte",
            "quantity": 1,
            "unit_price_pence": 1250,
            "line_total_pence": 1250,
        }
    ]


def test_dublin_rows_are_silently_dropped_without_a_rate():
    rows = [["2026-09-14T08:15:00", "Latte", "10.00", "1", "T1", "DUB-1"]]

    assert clean_rows(rows, "dublin") == []


def test_negative_quantity_becomes_positive():
    # BUG? see KC-102: a refund of one GBP 3.50 latte should reduce revenue by
    # 350p, but abs() turns it into a sale of +350p.
    rows = [["LDS-1", "14/09/2026 08:15", "T1", "Latte", "-1", "3.50"]]

    [row] = clean_rows(rows, "leeds")

    assert row["quantity"] == 1
    assert row["line_total_pence"] == 350


def test_exact_duplicate_rows_are_dropped():
    row = ["LDS-1", "14/09/2026 08:15", "T1", "Latte", "1", "3.50"]

    assert len(clean_rows([row, row], "leeds")) == 1


def test_same_product_at_same_minute_in_different_transactions_is_dropped():
    # BUG? see KC-102: the de-duplication key is (branch, sold_at, product), so
    # two customers buying a latte in the same minute count as one sale.
    rows = [
        ["LDS-1", "14/09/2026 08:15", "T1", "Latte", "1", "3.50"],
        ["LDS-2", "14/09/2026 08:15", "T2", "Latte", "1", "3.50"],
    ]

    cleaned = clean_rows(rows, "leeds")

    assert [r["transaction_id"] for r in cleaned] == ["LDS-1"]


def test_product_names_are_stripped_and_title_cased_only():
    # Not matched against the catalogue (see KC-103).
    rows = [
        ["LDS-1", "14/09/2026 08:15", "T1", "flat-white", "1", "3.40"],
        ["LDS-2", "14/09/2026 08:16", "T1", "pain au chocolat", "1", "2.80"],
        ["LDS-3", "14/09/2026 08:17", "T1", "", "1", "3.00"],
    ]

    products = [r["product"] for r in clean_rows(rows, "leeds")]

    assert products == ["Flat-White", "Pain Au Chocolat", ""]


def test_blank_and_bad_rows_are_silently_skipped():
    good = ["LDS-1", "14/09/2026 08:15", "T1", "Latte", "1", "3.50"]
    rows = [
        [],                                                      # empty line
        ["", "14/09/2026 08:16", "T1", "Latte", "1", "3.50"],    # no transaction id
        ["LDS-2", "14/09/2026 08:17", "T1", "Latte", "1", "N/A"],  # bad price
        ["LDS-3", "2026-09-14T08:18:00", "T1", "Latte", "1", "3.50"],  # ISO date at Leeds
        ["LDS-4", "14/09/2026 08:19"],                           # too few columns
        good,
    ]

    assert [r["transaction_id"] for r in clean_rows(rows, "leeds")] == ["LDS-1"]


# --- build_summary ------------------------------------------------------------
# build_summary only reads these four keys from each cleaned row.


def sale(branch, transaction_id, quantity, line_total_pence):
    return {
        "branch": branch,
        "transaction_id": transaction_id,
        "quantity": quantity,
        "line_total_pence": line_total_pence,
    }


def test_summary_for_one_branch():
    rows = [
        sale("leeds", "LDS-1", 2, 680),
        sale("leeds", "LDS-1", 1, 300),
        sale("leeds", "LDS-2", 1, 350),
    ]

    assert build_summary(rows, "2026-09-14") == [
        {
            "date": "2026-09-14",
            "branch": "leeds",
            "transactions": 2,  # LDS-1 and LDS-2
            "items_sold": 4,  # 2 + 1 + 1
            "revenue_gbp": "13.30",  # 680 + 300 + 350 = 1330p
        }
    ]


def test_summary_has_one_row_per_branch_in_order_first_seen():
    rows = [
        sale("york", "YRK-1", 1, 450),
        sale("leeds", "LDS-1", 1, 300),
        sale("york", "YRK-2", 2, 700),
    ]

    summary = build_summary(rows, "2026-09-14")

    assert [s["branch"] for s in summary] == ["york", "leeds"]
    assert summary[0]["transactions"] == 2
    assert summary[0]["revenue_gbp"] == "11.50"  # 450 + 700 = 1150p


def test_summary_of_no_rows_is_empty():
    assert build_summary([], "2026-09-14") == []


@pytest.mark.parametrize(
    "pence, expected",
    [
        (0, "0.00"),
        (5, "0.05"),
        (340, "3.40"),
        (1000, "10.00"),
    ],
)
def test_revenue_is_formatted_as_pounds_without_a_symbol(pence, expected):
    [row] = build_summary([sale("leeds", "LDS-1", 1, pence)], "2026-09-14")

    assert row["revenue_gbp"] == expected
