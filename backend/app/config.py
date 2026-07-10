"""
Central configuration.

CRITICAL: never hardcode API keys. OPENAI_API_KEY is read from the environment
(or a local .env file, which is git-ignored) at process start. If it is
missing, the generation service automatically falls back to an extractive
(no-LLM) mode so the rest of the pipeline stays testable offline.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # loads backend/.env if present; never commit this file

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "index_store"
INDEX_DIR.mkdir(exist_ok=True)

# ---- Foundation model settings (Objective 1) ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gpt-4o")
GENERATION_TEMPERATURE = float(os.getenv("GENERATION_TEMPERATURE", "0.0"))
# Temperature 0.0 is deliberate: policy Q&A must be deterministic and
# citation-faithful, not creative. Documented per project objective 1.

# ---- Embedding settings (Objective 2) ----
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")  # "openai" or "tfidf"
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
TFIDF_DIM = int(os.getenv("TFIDF_DIM", "256"))  # dense projection size for local fallback

# ---- Retrieval settings ----
TOP_K = int(os.getenv("TOP_K", "4"))

# ---- Data files ----
POLICIES_JSON = DATA_DIR / "operations_policies.json"
CUSTOMERS_CSV = DATA_DIR / "customers.csv"
ORDERS_CSV = DATA_DIR / "orders.csv"
RETURNS_CSV = DATA_DIR / "returns.csv"
TICKETS_CSV = DATA_DIR / "support_tickets.csv"
AUDIT_LOG_CSV = DATA_DIR / "entity_activity_audit_log.csv"

# Ticket category -> policy category retrieval filter routing (Objective 4).
# The real support_tickets.csv uses 5 categories: returns, product, shipping,
# account, billing. The policy corpus uses a different 5: returns, refunds,
# escalation, shipping, compliance. Mapping is:
TICKET_TO_POLICY_CATEGORY = {
    "returns": "returns",       # direct match
    "shipping": "shipping",     # direct match
    "billing": "refunds",       # billing disputes/charges route to refunds policy
    "account": "escalation",    # account-level issues route to escalation policy
    "product": "returns",       # product defect/quality complaints route to returns policy
    # Pass-through in case a caller supplies a policy-native category directly:
    "refunds": "refunds",
    "escalation": "escalation",
    "compliance": "compliance",
}

def using_live_llm() -> bool:
    return bool(OPENAI_API_KEY)
