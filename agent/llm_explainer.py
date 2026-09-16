from __future__ import annotations

"""
llm_explainer.py
----------------
Uses GPT-4o to write a personalised, number-specific explanation for the decision.

The prompt forces the model to:
  - Reference actual figures from the user's profile
  - Not be generic
  - Be direct and concise (2-4 sentences)
"""

from openai import OpenAI
import config

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def generate_explanation(
    profile: dict,
    requested_amount: float,
    decision: dict,
    request_text: str,
    currency: str,
) -> str:
    """
    Generates a 2-4 sentence plain-English explanation for the decision.
    References real numbers so it reads as personalised advice.
    """

    cuts_text = (
        ", ".join(f"{c['category']} ({c['action']})" for c in decision["spending_changes_needed"])
        if decision["spending_changes_needed"]
        else "none required"
    )

    plan_text = (
        " → ".join(f"{p['date']}: {currency} {p['amount']:,.2f}" for p in decision["payment_plan"])
        if decision["payment_plan"]
        else "single payment"
    )

    prompt = f"""You are a personal finance advisor. Write a direct, personalised explanation (2-4 sentences) for the decision below.

RULES:
- You MUST reference the actual numbers provided — do not be vague.
- Do NOT start with "Based on..." or "Given that..."
- Do NOT say "I recommend..." — state it as fact.
- Be conversational but professional.
- Mention specific upcoming bills or income dates if they are the reason for the decision.

USER'S FINANCIAL SNAPSHOT:
  Currency              : {currency}
  Current balance       : {profile['balance']:,.2f}
  Minimum balance buffer: {profile['minimum_balance_preference']:,.2f}
  Monthly income        : {profile['monthly_income']:,.2f}
  Monthly essential bills: {profile['monthly_essential_expenses']:,.2f}
  Monthly flexible spend : {profile['monthly_flexible_expenses']:,.2f}

REQUEST:
  "{request_text}"
  Amount requested: {currency} {requested_amount:,.2f}

DECISION:
  Status          : {decision['affordability_status']}
  Safe to pay now : {currency} {decision['amount_safe_to_pay']:,.2f}
  Method          : {decision['recommended_payment_method']}
  Payment plan    : {plan_text}
  Earliest full   : {decision['earliest_date_for_full_payment']}
  Spending cuts   : {cuts_text}

Write the explanation now:"""

    response = _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=220,
    )
    return response.choices[0].message.content.strip()
