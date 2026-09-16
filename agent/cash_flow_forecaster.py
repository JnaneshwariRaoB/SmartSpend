from __future__ import annotations

"""
cash_flow_forecaster.py
-----------------------
Projects the user's account balance day-by-day over a forecast window.

For each day it applies:
  + income events
  - essential expense events
  - flexible expense events (unless cut)

Returns a list of daily snapshots that the decision engine uses to find the
safest payment amount and earliest feasible date.
"""

from datetime import date, timedelta
from typing import Optional


# ── Event scheduling ──────────────────────────────────────────────────────────

def _hits_today(item: dict, check_date: date, key_next: str, key_gap: str = "avg_gap_days") -> bool:
    """Generic check: does this recurring item fire on check_date?"""
    anchor = date.fromisoformat(item[key_next])
    gap    = item.get(key_gap) or 30  # default monthly

    if check_date < anchor:
        return False

    diff = (check_date - anchor).days
    return diff % max(gap, 1) == 0


def _income_hits(income: dict, check_date: date) -> bool:
    freq_gap = {"monthly": 30, "biweekly": 14, "weekly": 7}
    gap = freq_gap.get(income["frequency"], 30)
    anchor = date.fromisoformat(income["next_date"])
    if check_date < anchor:
        return False
    return (check_date - anchor).days % gap == 0


def _expense_hits(expense: dict, check_date: date) -> bool:
    freq_gap = {"monthly": 30, "biweekly": 14, "weekly": 7}
    gap = freq_gap.get(expense.get("frequency", "monthly"), 30)
    anchor = date.fromisoformat(expense["next_due"])
    if check_date < anchor:
        return False
    return (check_date - anchor).days % gap == 0


# ── Core forecaster ───────────────────────────────────────────────────────────

def forecast_cash_flow(
    profile: dict,
    from_date: date,
    to_date: date,
    exclude_flexible: bool = False,
) -> list[dict]:
    """
    Build a day-by-day balance projection.

    Args:
        profile:          Output of profile_builder.build_profile()
        from_date:        Start of forecast window (usually request_date)
        to_date:          End of forecast window (usually desired_completion_date)
        exclude_flexible: If True, flexible expenses are skipped (used to test
                          "what if the user cuts discretionary spending?")

    Returns:
        List of dicts: {date, balance, events, safe}
    """
    min_balance = profile["minimum_balance_preference"]
    running     = profile["balance"]
    forecast    = []

    days = (to_date - from_date).days + 1
    for offset in range(days):
        current_date = from_date + timedelta(days=offset)
        events: list[dict] = []

        # Income
        for inc in profile["income"]:
            if _income_hits(inc, current_date):
                running += inc["amount"]
                events.append({"type": "income", "source": inc["source"], "amount": inc["amount"]})

        # Essential expenses
        for exp in profile["essential_expenses"]:
            if _expense_hits(exp, current_date):
                running -= exp["amount"]
                events.append({"type": "essential", "category": exp["category"], "amount": exp["amount"]})

        # Flexible expenses (optionally skipped)
        if not exclude_flexible:
            for exp in profile["flexible_expenses"]:
                if _expense_hits(exp, current_date):
                    running -= exp["amount"]
                    events.append({"type": "flexible", "category": exp["category"], "amount": exp["amount"]})

        forecast.append(
            {
                "date":    str(current_date),
                "balance": round(running, 2),
                "events":  events,
                "safe":    running >= min_balance,
            }
        )

    return forecast


# ── Derived helpers ───────────────────────────────────────────────────────────

def max_safe_payment(profile: dict, forecast: list[dict]) -> float:
    """
    Maximum amount that can be paid TODAY without ever breaching min_balance.

    Logic:
      Paying X today reduces the balance by X on every subsequent day.
      So we need:  min(future balances) - X  >=  min_balance
      =>  X  <=  min(future balances) - min_balance
    """
    min_balance   = profile["minimum_balance_preference"]
    min_future    = min((d["balance"] for d in forecast), default=profile["balance"])
    # Also include today's starting balance before any scheduled events
    effective_min = min(min_future, profile["balance"])
    safe          = effective_min - min_balance
    return max(0.0, round(safe, 2))


def earliest_full_payment_date(
    profile: dict,
    requested_amount: float,
    from_date: date,
    deadline: date,
    search_days: int = 120,
) -> str:
    """
    Walk forward from from_date and return the first date on which the user
    can pay requested_amount without breaching min_balance on any later day.
    """
    horizon = max(deadline, from_date + timedelta(days=search_days))
    full_forecast = forecast_cash_flow(profile, from_date, horizon)

    n = len(full_forecast)
    for i, snapshot in enumerate(full_forecast):
        # After paying on day i, the minimum future balance drops by requested_amount
        future_min = min(d["balance"] for d in full_forecast[i:]) if i < n else snapshot["balance"]
        if future_min - requested_amount >= profile["minimum_balance_preference"]:
            return snapshot["date"]

    return str(horizon)  # Cannot find a safe date within search window
