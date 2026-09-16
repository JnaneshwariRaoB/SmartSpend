import os
from dotenv import load_dotenv

load_dotenv()

# --- Data Source ---
# Options: "plaid_sandbox" | "setu" | "csv"
DATA_SOURCE = os.getenv("DATA_SOURCE", "plaid_sandbox")

# --- Plaid ---
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET    = os.getenv("PLAID_SECRET", "")
PLAID_ENV       = os.getenv("PLAID_ENV", "sandbox")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
