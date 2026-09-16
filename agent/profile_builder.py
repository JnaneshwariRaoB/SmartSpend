from __future__ import annotations

"""
profile_builder.py
------------------
Analyses raw Plaid transaction data and builds a structured financial profile.

Detects:
  - Recurring income  (salary, freelance payments, etc.)
  - Recurring expenses split into essential vs flexible
  - Minimum balance preference (inferred if not provided)
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Optional


# ── Category helpers ─────────────────────────────────────────────────────────

ESSENTIAL_KEYWORDS = {
    "rent", "mortgage", "utilities", "electric", "gas", "water",
    "internet", "mobile", "phone", "insurance", "loan", "emi",
    "grocery", "groceries", "supermarket", "medical", "healthcare",
    "hospital", "pharmacy", "transfer", "payment",
}

FLEXIBLE_KEYWORDS = {
    "netflix", "spotify", "amazon prime", "hulu", "disney",
    "gym", "fitness", "restaurant", "dining", "cafe", "coffee",
    "entertainment", "shopping", "clothing", "travel", "hotel",
    "uber", "lyft", "delivery",
}


def is_essential(category: str, merchant: str = "") -> bool:
    text = (category + " " + merchant).lower()
    return any(k in text for k in ESSENTIAL_KEYWORDS)


# ── Frequency helpers ─────────────────────────────────────────────────────────

def _detect_frequency(avg_gap_days: float) -> tuple[str, float]:
    """Returns (frequency_label, monthly_multiplier)."""
    if avg_gap_days <= 8:
        return "weekly", 4.33
    if avg_gap_days <= 18:
        return "biweekly", 2.17
    return "monthly", 1.0


# ── Income detection ─────────────────────────────────────────────────────────

def _detect_income(transactions: list[dict]) -> list[dict]:
    """
    Credits in Plaid have negative amounts (money coming IN).
    We look for recurring credits above a significance threshold.
    """
    credits = [t for t in transactions if t["amount"] < 0]

    # Group by merchant name prefix
    groups: dict[str, list] = defaultdict(list)
    for t in credits:
        key = (t["merchant"] or t["description"])[:25].lower()
        groups[key].append(t)

    income_sources = []
    for source, txns in groups.items():
        amounts = [abs(t["amount"]) for t in txns]

        # Only consider significant recurring credits
        if len(txns) < 2 or mean(amounts) < 200:
            continue

        # Consistent amounts → likely payroll / freelance
        if len(amounts) >= 3 and stdev(amounts) / mean(amounts) > 0.4:
            continue

        sorted_dates = sorted(t["date"] for t in txns)
        gaps = [
            (date.fromisoformat(sorted_dates[i + 1]) - date.fromisoformat(sorted_dates[i])).days
            for i in range(len(sorted_dates) - 1)
        ]
        avg_gap   = mean(gaps)
        frequency, multiplier = _detect_frequency(avg_gap)
        avg_amt   = mean(amounts)
        last_date = date.fromisoformat(sorted_dates[-1])
        next_date = last_date + timedelta(days=int(avg_gap))

        income_sources.append(
            {
                "source":         source,
                "amount":         round(avg_amt, 2),
                "frequency":      frequency,
                "monthly_amount": round(avg_amt * multiplier, 2),
                "next_date":      str(next_date),
                "avg_gap_days":   int(avg_gap),
            }
        )

    return income_sources


# ── Expense detection ─────────────────────────────────────────────────────────

def _detect_recurring_expenses(transactions: list[dict]) -> list[dict]:
    """
    Debits in Plaid have positive amounts (money going OUT).
    Group by merchant; flag as recurring if it appears ≥ 2× with consistent amounts.
    """
    debits = [t for t in transactions if t["amount"] > 0]

    groups: dict[str, list] = defaultdict(list)
    for t in debits:
        key = (t["merchant"] or t["description"])[:25].lower()
        groups[key].append(t)

    recurring = []
    for merchant, txns in groups.items():
        if len(txns) < 2:
            continue

        amounts = [t["amount"] for t in txns]
        avg_amt = mean(amounts)

        # Skip if amounts vary wildly (one-time variable spend like groceries)
        variability = stdev(amounts) / avg_amt if len(amounts) >= 3 else 0
        if variability > 0.35:
            continue

        sorted_dates = sorted(t["date"] for t in txns)
        gaps = [
            (date.fromisoformat(sorted_dates[i + 1]) - date.fromisoformat(sorted_dates[i])).days
            for i in range(len(sorted_dates) - 1)
        ]
        avg_gap = mean(gaps)

        # Only count monthly-or-more-frequent patterns
        if avg_gap > 35:
            continue

        frequency, multiplier = _detect_frequency(avg_gap)
        last_date = date.fromisoformat(sorted_dates[-1])
        next_due  = last_date + timedelta(days=int(avg_gap))
        essential = is_essential(txns[0]["category"], merchant)

        recurring.append(
            {
                "merchant":       merchant,
                "category":       txns[0]["category"],
                "amount":         round(avg_amt, 2),
                "frequency":      frequency,
                "monthly_amount": round(avg_amt * multiplier, 2),
                "next_due":       str(next_due),
                "due_day":        last_date.day,
                "essential":      essential,
            }
        )

    return recurring


# ── Public function ───────────────────────────────────────────────────────────

def build_profile(raw_data: dict, min_balance_pref: Optional[float] = None) -> dict:
    """
    Converts raw Plaid data into a structured financial profile ready for the
    cash-flow forecaster and decision engine.
    """
    balance      = raw_data["balance"]
    currency     = raw_data["currency"]
    transactions = raw_data["transactions"]

    income   = _detect_income(transactions)
    expenses = _detect_recurring_expenses(transactions)

    essential = [e for e in expenses if e["essential"]]
    flexible  = [e for e in expenses if not e["essential"]]

    monthly_income     = sum(i["monthly_amount"] for i in income)
    monthly_essential  = sum(e["monthly_amount"] for e in essential)
    monthly_flexible   = sum(e["monthly_amount"] for e in flexible)

    # Infer minimum balance if user hasn't set one:
    # 10% of monthly income, at least the equivalent of one month's essentials / 4
    if min_balance_pref is None:
        min_balance_pref = max(
            round(monthly_income * 0.10, 2),
            round(monthly_essential / 4, 2),
            100.0,
        )

    return {
        "balance":                    balance,
        "currency":                   currency,
        "minimum_balance_preference": min_balance_pref,
        "income":                     income,
        "essential_expenses":         essential,
        "flexible_expenses":          flexible,
        "recurring_expenses":         expenses,
        "monthly_income":             round(monthly_income, 2),
        "monthly_essential_expenses": round(monthly_essential, 2),
        "monthly_flexible_expenses":  round(monthly_flexible, 2),
    }
