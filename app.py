"""
app.py
------
Flask web server for SmartSpend UI.

Run:  python3 app.py
Open: http://localhost:5000
"""

import json
import logging
import sys
from datetime import date

from flask import Flask, jsonify, render_template, request

import config
from agent.data_fetcher   import create_sandbox_token, fetch_user_data, get_plaid_client
from agent.profile_builder import build_profile
from agent.decision_engine import make_decision
from agent.llm_explainer   import generate_explanation

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("log.txt", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("smartspend")

_token_cache: dict = {}


def _get_token(user_id: str = "demo_user") -> str:
    if user_id not in _token_cache:
        client = get_plaid_client()
        _token_cache[user_id] = create_sandbox_token(client)
        log.info(f"[{user_id}] Sandbox token created")
    return _token_cache[user_id]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/profile")
def api_profile():
    """Returns raw bank data + analysed profile for the sidebar panels."""
    try:
        token    = _get_token()
        raw_data = fetch_user_data(token)
        profile  = build_profile(raw_data)

        return jsonify({
            "ok": True,
            "raw": {
                "balance":      raw_data["balance"],
                "currency":     raw_data["currency"],
                "tx_count":     len(raw_data["transactions"]),
                "transactions": raw_data["transactions"][:10],
            },
            "profile": {
                "minimum_balance":        profile["minimum_balance_preference"],
                "monthly_income":         profile["monthly_income"],
                "monthly_essential":      profile["monthly_essential_expenses"],
                "monthly_flexible":       profile["monthly_flexible_expenses"],
                "monthly_surplus":        round(
                    profile["monthly_income"]
                    - profile["monthly_essential_expenses"]
                    - profile["monthly_flexible_expenses"], 2
                ),
                "income":    profile["income"],
                "essential": profile["essential_expenses"],
                "flexible":  profile["flexible_expenses"],
            },
        })
    except Exception as exc:
        log.error(f"/api/profile error: {exc}", exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/analyse", methods=["POST"])
def api_analyse():
    """Runs the affordability engine and returns the decision."""
    body = request.get_json()
    try:
        req_date  = date.today()
        deadline  = date.fromisoformat(body["deadline"])
        amount    = float(body["amount"])
        req_type  = body.get("request_type", "purchase")
        req_text  = body.get("request_text", "")
        allows_p  = body.get("allows_partial", True)

        token    = _get_token()
        raw_data = fetch_user_data(token)
        profile  = build_profile(raw_data)

        decision = make_decision(
            profile=profile,
            requested_amount=amount,
            request_date=req_date,
            deadline=deadline,
            allows_partial=allows_p,
            request_type=req_type,
        )

        explanation = generate_explanation(
            profile=profile,
            requested_amount=amount,
            decision=decision,
            request_text=req_text,
            currency=raw_data["currency"],
        )

        return jsonify({
            "ok":                          True,
            "currency":                    raw_data["currency"],
            "amount_safe_to_pay":          decision["amount_safe_to_pay"],
            "affordability_status":        decision["affordability_status"],
            "recommended_payment_method":  decision["recommended_payment_method"],
            "payment_plan":                decision["payment_plan"],
            "earliest_date":               decision["earliest_date_for_full_payment"],
            "spending_changes_needed":     decision["spending_changes_needed"],
            "explanation":                 explanation,
        })
    except Exception as exc:
        log.error(f"/api/analyse error: {exc}", exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
