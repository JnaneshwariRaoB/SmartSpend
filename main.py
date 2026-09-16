"""
main.py
-------
Entry point for SmartSpend.

Usage:
  # Single interactive request (uses Plaid sandbox demo user)
  python main.py

  # Batch mode — processes every row in a CSV
  python main.py --csv dataset/requests.csv

  # Specify custom output file
  python main.py --csv dataset/requests.csv --out output.csv
"""

import argparse
import json
import logging
import sys
from datetime import date

import pandas as pd

import config
from agent.data_fetcher  import fetch_user_data, create_sandbox_token, get_plaid_client
from agent.profile_builder  import build_profile
from agent.decision_engine  import make_decision
from agent.llm_explainer    import generate_explanation

# ── Logging (writes to log.txt AND console) ───────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("log.txt", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("smartspend")

# ── Token cache (one Plaid token per user_id in the session) ──────────────────
_token_cache: dict[str, str] = {}


def _get_access_token(user_id: str) -> str:
    if user_id not in _token_cache:
        if config.DATA_SOURCE == "plaid_sandbox":
            client = get_plaid_client()
            token  = create_sandbox_token(client)
            _token_cache[user_id] = token
            log.info(f"[{user_id}] Sandbox token created")
        else:
            raise ValueError(f"Unsupported DATA_SOURCE: {config.DATA_SOURCE!r}")
    return _token_cache[user_id]


# ── Debug view ───────────────────────────────────────────────────────────────

def _print_profile_summary(raw_data: dict, profile: dict) -> None:
    cur = raw_data["currency"]
    sep = "─" * 50

    print(f"\n{sep}")
    print("  WHAT PLAID RETURNED (raw bank data)")
    print(sep)
    print(f"  Balance now   : {cur} {raw_data['balance']:,.2f}")
    print(f"  Transactions  : {len(raw_data['transactions'])} entries (last 90 days)")
    print(f"\n  Last 10 transactions:")
    for t in raw_data["transactions"][:10]:
        sign   = "-" if t["amount"] > 0 else "+"
        symbol = "OUT" if t["amount"] > 0 else " IN"
        print(f"    {t['date']}  {symbol}  {cur} {abs(t['amount']):>9,.2f}  {t['merchant'][:30]}")

    print(f"\n{sep}")
    print("  WHAT OUR CODE FIGURED OUT (from those transactions)")
    print(sep)

    print(f"\n  Minimum safety buffer  : {cur} {profile['minimum_balance_preference']:,.2f}")

    print(f"\n  Detected income sources:")
    if profile["income"]:
        for inc in profile["income"]:
            print(f"    + {cur} {inc['amount']:>9,.2f}  every {inc['frequency']:<10}  "
                  f"next: {inc['next_date']}  source: {inc['source']}")
    else:
        print("    (none detected)")

    print(f"\n  Recurring ESSENTIAL bills (rent, utilities, EMIs...):")
    if profile["essential_expenses"]:
        for exp in profile["essential_expenses"]:
            print(f"    - {cur} {exp['amount']:>9,.2f}  every {exp['frequency']:<10}  "
                  f"next due: {exp['next_due']}  [{exp['category']}]")
    else:
        print("    (none detected)")

    print(f"\n  Recurring FLEXIBLE spend (subscriptions, dining...):")
    if profile["flexible_expenses"]:
        for exp in profile["flexible_expenses"]:
            print(f"    - {cur} {exp['amount']:>9,.2f}  every {exp['frequency']:<10}  "
                  f"next due: {exp['next_due']}  [{exp['category']}]")
    else:
        print("    (none detected)")

    print(f"\n  Monthly summary:")
    print(f"    Income      : {cur} {profile['monthly_income']:>10,.2f}")
    print(f"    Essentials  : {cur} {profile['monthly_essential_expenses']:>10,.2f}")
    print(f"    Flexible    : {cur} {profile['monthly_flexible_expenses']:>10,.2f}")
    surplus = profile["monthly_income"] - profile["monthly_essential_expenses"] - profile["monthly_flexible_expenses"]
    print(f"    Net surplus : {cur} {surplus:>10,.2f}")
    print(sep)


# ── Core processing function ──────────────────────────────────────────────────

def process_request(row: dict) -> dict:
    request_id   = row["request_id"]
    user_id      = row["user_id"]
    request_date = date.fromisoformat(str(row["request_date"]))
    deadline     = date.fromisoformat(str(row["desired_completion_date"]))
    amount       = float(row["requested_amount"])
    allows_part  = str(row["allows_partial_payment"]).strip().lower() == "true"
    req_type     = str(row["request_type"])
    req_text     = str(row["request_text"])

    log.info(f"[{request_id}] {req_type.upper()}  {amount:,.2f}  deadline={deadline}")

    # 1. Fetch data from Plaid
    token    = _get_access_token(user_id)
    raw_data = fetch_user_data(token)
    log.info(f"[{request_id}] Balance={raw_data['currency']} {raw_data['balance']:,.2f}  "
             f"Transactions={len(raw_data['transactions'])}")

    # 2. Build financial profile
    profile = build_profile(raw_data)
    log.info(f"[{request_id}] Income={profile['monthly_income']:,.2f}/mo  "
             f"Essentials={profile['monthly_essential_expenses']:,.2f}/mo  "
             f"Flexible={profile['monthly_flexible_expenses']:,.2f}/mo  "
             f"MinBal={profile['minimum_balance_preference']:,.2f}")
    _print_profile_summary(raw_data, profile)

    # 3. Make affordability decision
    decision = make_decision(
        profile=profile,
        requested_amount=amount,
        request_date=request_date,
        deadline=deadline,
        allows_partial=allows_part,
        request_type=req_type,
    )
    log.info(f"[{request_id}] → {decision['affordability_status']}  "
             f"safe_now={decision['amount_safe_to_pay']:,.2f}  "
             f"method={decision['recommended_payment_method']}")

    # 4. Generate personalised explanation
    explanation = generate_explanation(
        profile=profile,
        requested_amount=amount,
        decision=decision,
        request_text=req_text,
        currency=raw_data["currency"],
    )

    return {
        "request_id":                    request_id,
        "user_id":                       user_id,
        "amount_safe_to_pay":            decision["amount_safe_to_pay"],
        "affordability_status":          decision["affordability_status"],
        "recommended_payment_method":    decision["recommended_payment_method"],
        "payment_plan":                  json.dumps(decision["payment_plan"]),
        "earliest_date_for_full_payment": decision["earliest_date_for_full_payment"],
        "spending_changes_needed":       json.dumps(decision["spending_changes_needed"]),
        "decision_explanation":          explanation,
    }


# ── Batch mode ────────────────────────────────────────────────────────────────

def run_batch(csv_path: str, output_path: str = "output.csv") -> None:
    df = pd.read_csv(csv_path)
    log.info(f"Batch mode: {len(df)} requests from {csv_path}")
    results = []

    for _, row in df.iterrows():
        try:
            result = process_request(row.to_dict())
        except Exception as exc:
            log.error(f"[{row['request_id']}] Failed: {exc}", exc_info=True)
            result = {
                "request_id":                    row["request_id"],
                "user_id":                       row["user_id"],
                "amount_safe_to_pay":            0.0,
                "affordability_status":          "not_affordable",
                "recommended_payment_method":    "do_not_proceed",
                "payment_plan":                  "[]",
                "earliest_date_for_full_payment": str(row["desired_completion_date"]),
                "spending_changes_needed":       "[]",
                "decision_explanation":          f"Processing error: {exc}",
            }
        results.append(result)

    out_df = pd.DataFrame(results)
    out_df.to_csv(output_path, index=False)
    log.info(f"Output written to {output_path}  ({len(results)} rows)")


# ── Interactive single-request demo ──────────────────────────────────────────

def run_interactive() -> None:
    print("\n=== SmartSpend — Affordability Check ===")
    text      = input("What do you want to buy/spend on? \n> ").strip()
    amount    = float(input("How much does it cost? \n> "))
    deadline  = input("Deadline (YYYY-MM-DD): ").strip() or str(date.today())
    req_type  = input("Type (purchase/travel/education/investment/housing/debt_repayment/family_transfer/emergency_expense): ").strip() or "purchase"

    row = {
        "request_id":              "interactive_001",
        "user_id":                 "demo_user",
        "request_date":            str(date.today()),
        "desired_completion_date": deadline,
        "requested_amount":        amount,
        "allows_partial_payment":  "true",
        "request_type":            req_type,
        "request_text":            text,
    }

    result = process_request(row)
    print("\n─────────────────────────────────────")
    print(f"  Status   : {result['affordability_status']}")
    print(f"  Method   : {result['recommended_payment_method']}")
    print(f"  Safe now : {result['amount_safe_to_pay']:,.2f}")
    print(f"  Plan     : {result['payment_plan']}")
    print(f"  Earliest : {result['earliest_date_for_full_payment']}")
    print(f"\n  {result['decision_explanation']}")
    print("─────────────────────────────────────\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartSpend financial affordability engine")
    parser.add_argument("--csv", metavar="PATH", help="Path to requests CSV for batch processing")
    parser.add_argument("--out", metavar="PATH", default="output.csv", help="Output CSV path (default: output.csv)")
    args = parser.parse_args()

    if args.csv:
        run_batch(args.csv, args.out)
    else:
        run_interactive()
