from __future__ import annotations

"""
decision_engine.py
------------------
Applies safety rules and produces the final affordability decision.

Decision priority (checked in order):
  1. Can pay in full today?              → pay_in_full
  2. Partial today + rest later?         → pay_partial   (only if allows_partial)
  3. Wait for income, then pay in full?  → wait
  4. Installments across income dates?   → installments
  5. Cut flexible spending and retry 1-4 → affordable_with_plan
  6. Still can't?                        → do_not_proceed
"""

from datetime import date, timedelta
from typing import Optional

from agent.cash_flow_forecaster import (
    forecast_cash_flow,
    max_safe_payment,
    earliest_full_payment_date,
)

FULL_TOLERANCE = 0.01  # treat as "full" if within 1%


# ── Instalment helpers ────────────────────────────────────────────────────────

def _future_income_dates(profile: dict, from_date: date, to_date: date) -> list[date]:
    freq_gap = {"monthly": 30, "biweekly": 14, "weekly": 7}
    dates: set[date] = set()
    for inc in profile["income"]:
        gap    = freq_gap.get(inc["frequency"], 30)
        anchor = date.fromisoformat(inc["next_date"])
        d = anchor
        while d <= to_date:
            if d > from_date:
                dates.add(d)
            d += timedelta(days=gap)
    return sorted(dates)


def _build_installment_plan(
    profile: dict,
    remaining: float,
    from_date: date,
    deadline: date,
) -> list[dict]:
    income_dates = _future_income_dates(profile, from_date, deadline)
    if not income_dates:
        return [{"date": str(deadline), "amount": round(remaining, 2)}]
    per = remaining / len(income_dates)
    return [{"date": str(d), "amount": round(per, 2)} for d in income_dates]


def _spending_cuts(profile: dict) -> list[dict]:
    cuts = []
    for exp in profile.get("flexible_expenses", []):
        if exp["monthly_amount"] >= 5:
            action = "stop" if exp["monthly_amount"] <= 50 else "reduce"
            cuts.append({"category": exp["category"], "action": action})
    return cuts


def _apply_cuts(profile: dict, cuts: list[dict]) -> dict:
    cut_cats = {c["category"] for c in cuts}
    p = dict(profile)
    p["flexible_expenses"] = [e for e in profile["flexible_expenses"] if e["category"] not in cut_cats]
    p["monthly_flexible_expenses"] = sum(e["monthly_amount"] for e in p["flexible_expenses"])
    return p


# ── Main decision function ────────────────────────────────────────────────────

def make_decision(
    profile: dict,
    requested_amount: float,
    request_date: date,
    deadline: date,
    allows_partial: bool,
    request_type: str,
) -> dict:
    """
    Returns a decision dict with all output fields except decision_explanation.
    """

    # ── Attempt 1: original profile ───────────────────────────────────────────
    result = _evaluate(profile, requested_amount, request_date, deadline, allows_partial)
    if result["affordability_status"] != "not_affordable":
        return result

    # ── Attempt 2: cut flexible spending and retry ────────────────────────────
    cuts = _spending_cuts(profile)
    if cuts:
        trimmed = _apply_cuts(profile, cuts)
        result  = _evaluate(trimmed, requested_amount, request_date, deadline, allows_partial)
        result["spending_changes_needed"] = cuts
        return result

    # Truly cannot afford
    return result


def _evaluate(
    profile: dict,
    requested_amount: float,
    request_date: date,
    deadline: date,
    allows_partial: bool,
) -> dict:
    forecast  = forecast_cash_flow(profile, request_date, deadline)
    safe_now  = max_safe_payment(profile, forecast)
    min_bal   = profile["minimum_balance_preference"]
    earliest  = earliest_full_payment_date(profile, requested_amount, request_date, deadline)
    earliest_d = date.fromisoformat(earliest)

    # ── Case 1: pay in full today ─────────────────────────────────────────────
    if safe_now >= requested_amount * (1 - FULL_TOLERANCE):
        return {
            "amount_safe_to_pay":            round(requested_amount, 2),
            "affordability_status":          "affordable_now",
            "recommended_payment_method":    "pay_in_full",
            "payment_plan":                  [],
            "earliest_date_for_full_payment": str(request_date),
            "spending_changes_needed":       [],
        }

    # ── Case 2: wait — full amount safe on a future date within deadline ──────
    if earliest_d <= deadline and safe_now < requested_amount * 0.05:
        return {
            "amount_safe_to_pay":            round(safe_now, 2),
            "affordability_status":          "affordable_later",
            "recommended_payment_method":    "wait",
            "payment_plan":                  [{"date": earliest, "amount": round(requested_amount, 2)}],
            "earliest_date_for_full_payment": earliest,
            "spending_changes_needed":       [],
        }

    # ── Case 3: partial today + installments for the rest ────────────────────
    if earliest_d <= deadline and allows_partial and safe_now > 0:
        remaining = requested_amount - safe_now
        plan = _build_installment_plan(profile, remaining, request_date, deadline)
        return {
            "amount_safe_to_pay":            round(safe_now, 2),
            "affordability_status":          "affordable_with_plan",
            "recommended_payment_method":    "pay_partial",
            "payment_plan":                  [{"date": str(request_date), "amount": round(safe_now, 2)}] + plan,
            "earliest_date_for_full_payment": earliest,
            "spending_changes_needed":       [],
        }

    # ── Case 4: installments (no upfront partial) ─────────────────────────────
    if earliest_d <= deadline:
        plan = _build_installment_plan(profile, requested_amount, request_date, deadline)
        return {
            "amount_safe_to_pay":            round(safe_now, 2),
            "affordability_status":          "affordable_with_plan",
            "recommended_payment_method":    "installments",
            "payment_plan":                  plan,
            "earliest_date_for_full_payment": earliest,
            "spending_changes_needed":       [],
        }

    # ── Case 5: not affordable within deadline ────────────────────────────────
    return {
        "amount_safe_to_pay":            round(max(safe_now, 0), 2),
        "affordability_status":          "not_affordable",
        "recommended_payment_method":    "do_not_proceed",
        "payment_plan":                  [],
        "earliest_date_for_full_payment": earliest,
        "spending_changes_needed":       [],
    }
