"""
data_fetcher.py
---------------
Fetches live financial data from Plaid sandbox.

In production swap DATA_SOURCE in config.py to "setu" or "csv"
and only this file needs to change — everything else stays the same.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products

import config


def get_plaid_client() -> plaid_api.PlaidApi:
    env_map = {
        "sandbox":    plaid.Environment.Sandbox,
        "production": plaid.Environment.Production,
    }
    configuration = plaid.Configuration(
        host=env_map.get(config.PLAID_ENV, plaid.Environment.Sandbox),
        api_key={
            "clientId": config.PLAID_CLIENT_ID,
            "secret":   config.PLAID_SECRET,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def create_sandbox_token(client: plaid_api.PlaidApi, institution_id: str = "ins_109508") -> str:
    """
    Create a sandbox access token for a fake institution.
    ins_109508 = First Platypus Bank (Plaid's default sandbox bank).
    Call once per user session; cache the result.
    """
    pt_resp = client.sandbox_public_token_create(
        SandboxPublicTokenCreateRequest(
            institution_id=institution_id,
            initial_products=[Products("transactions")],
        )
    )
    exchange_resp = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=pt_resp.public_token)
    )
    return exchange_resp.access_token


def fetch_user_data(access_token: str, days_back: int = 90) -> dict:
    """
    Returns a normalised dict with balance + transactions.
    This is the ONLY function that knows about Plaid.
    Everything downstream works with this plain dict.
    """
    client = get_plaid_client()

    # ── balance ──────────────────────────────────────────────────────────────
    accounts_resp = client.accounts_get(
        AccountsGetRequest(access_token=access_token)
    )
    accounts = accounts_resp.accounts

    # Prefer the first depository (checking/savings) account
    primary = next(
        (a for a in accounts if a.type.value == "depository"),
        accounts[0],
    )
    balance  = primary.balances.current or 0.0
    currency = primary.balances.iso_currency_code or "USD"

    # ── transactions ─────────────────────────────────────────────────────────
    start = date.today() - timedelta(days=days_back)
    end   = date.today()

    # Plaid sandbox needs a few seconds to generate transaction data after
    # token creation. Retry up to 5 times with increasing wait.
    tx_resp = None
    for attempt in range(5):
        try:
            tx_resp = client.transactions_get(
                TransactionsGetRequest(
                    access_token=access_token,
                    start_date=start,
                    end_date=end,
                    options=TransactionsGetRequestOptions(count=500),
                )
            )
            break
        except plaid.exceptions.ApiException as exc:
            if "PRODUCT_NOT_READY" in str(exc) and attempt < 4:
                wait = (attempt + 1) * 3  # 3s, 6s, 9s, 12s
                print(f"  Plaid data not ready yet, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    transactions = [
        {
            # Plaid convention: positive amount = money OUT (debit)
            #                   negative amount = money IN  (credit)
            "date":        str(t.date),
            "amount":      t.amount,
            "category":    (t.category[0] if t.category else "other").lower(),
            "description": t.name,
            "merchant":    (t.merchant_name or t.name or "").strip(),
        }
        for t in tx_resp.transactions
    ]

    return {
        "balance":      balance,
        "currency":     currency,
        "transactions": transactions,
    }
