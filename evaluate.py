"""
evaluate.py
-----------
Scores agent predictions against reference answers.

Usage:
  python evaluate.py                                          # defaults
  python evaluate.py output.csv dataset/expected_output.csv  # custom paths
"""

import sys
from datetime import date

import pandas as pd


def _date_diff_ok(pred: str, exp: str, tolerance_days: int = 7) -> bool:
    try:
        return abs((date.fromisoformat(str(pred)) - date.fromisoformat(str(exp))).days) <= tolerance_days
    except Exception:
        return False


def _amount_ok(pred: float, exp: float, tolerance_pct: float = 0.05) -> bool:
    if exp == 0:
        return pred == 0
    return abs(pred - exp) / abs(exp) <= tolerance_pct


def evaluate(predictions_path: str, expected_path: str) -> None:
    try:
        pred = pd.read_csv(predictions_path)
        exp  = pd.read_csv(expected_path)
    except FileNotFoundError as e:
        print(f"File not found: {e}")
        return

    merged = pred.merge(exp, on="request_id", suffixes=("_pred", "_exp"))

    if merged.empty:
        print("No matching request_ids found between prediction and expected files.")
        print(f"  Predictions : {len(pred)} rows  ({predictions_path})")
        print(f"  Expected    : {len(exp)} rows  ({expected_path})")
        return

    n = len(merged)

    # ── Field-level metrics ───────────────────────────────────────────────────

    status_acc = (
        merged["affordability_status_pred"] == merged["affordability_status_exp"]
    ).mean()

    method_acc = (
        merged["recommended_payment_method_pred"] == merged["recommended_payment_method_exp"]
    ).mean()

    amount_acc = merged.apply(
        lambda r: _amount_ok(
            float(r["amount_safe_to_pay_pred"]),
            float(r["amount_safe_to_pay_exp"]),
        ),
        axis=1,
    ).mean()

    date_acc = merged.apply(
        lambda r: _date_diff_ok(
            r["earliest_date_for_full_payment_pred"],
            r["earliest_date_for_full_payment_exp"],
        ),
        axis=1,
    ).mean()

    overall = (status_acc + method_acc + amount_acc + date_acc) / 4

    # ── Print report ──────────────────────────────────────────────────────────

    bar = "═" * 45
    print(f"\n{bar}")
    print(f"  SmartSpend Evaluation Report")
    print(bar)
    print(f"  Requests evaluated           : {n}")
    print(f"  affordability_status  match  : {status_acc:>6.1%}")
    print(f"  recommended_method    match  : {method_acc:>6.1%}")
    print(f"  amount_safe_to_pay    (±5%)  : {amount_acc:>6.1%}")
    print(f"  earliest_full_date   (±7d)   : {date_acc:>6.1%}")
    print(f"  ── Overall score             : {overall:>6.1%}")
    print(bar)

    # ── Per-request breakdown for mismatches ──────────────────────────────────
    mismatches = merged[
        (merged["affordability_status_pred"] != merged["affordability_status_exp"])
        | (merged["recommended_payment_method_pred"] != merged["recommended_payment_method_exp"])
    ]
    if not mismatches.empty:
        print(f"\n  Mismatches ({len(mismatches)}):")
        for _, row in mismatches.iterrows():
            print(
                f"    {row['request_id']:<14}  "
                f"status: {row['affordability_status_pred']} vs {row['affordability_status_exp']}  |  "
                f"method: {row['recommended_payment_method_pred']} vs {row['recommended_payment_method_exp']}"
            )

    # ── Unmatched predictions (no expected answer — for manual review) ────────
    unmatched_ids = set(pred["request_id"]) - set(exp["request_id"])
    if unmatched_ids:
        print(f"\n  Unmatched predictions (no expected answer — manual review):")
        for rid in sorted(unmatched_ids):
            row = pred[pred["request_id"] == rid].iloc[0]
            print(
                f"    {rid:<14}  {row['affordability_status']:<22}  "
                f"{row['recommended_payment_method']:<16}  "
                f"safe={row['amount_safe_to_pay']:,.2f}"
            )

    print()


if __name__ == "__main__":
    pred_path = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    exp_path  = sys.argv[2] if len(sys.argv) > 2 else "dataset/expected_output.csv"
    evaluate(pred_path, exp_path)
