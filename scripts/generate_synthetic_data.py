"""
LEGACY / FALLBACK ONLY: the real customers/orders/returns/support_tickets
CSVs were supplied for this project and now live in backend/app/data/. This
script is kept only as a fallback for demoing the pipeline without the real
files (e.g. a fresh environment that only has operations_policies.json).
Running it will OVERWRITE backend/app/data/*.csv — do not run it against a
directory that already holds the real files unless that's what you intend.

Generate synthetic customers/orders/returns/support_tickets data.

The project brief lists customers.csv, orders.csv, returns.csv, and
support_tickets.csv as inputs but only operations_policies.json was supplied.
Per the brief's "Technical Notes" ("All data is synthetic and intended for
education... simulate tool calls against local files"), this script fabricates
small, internally-consistent CSVs so the RAG pipeline has live case context to
join against. Re-running is deterministic (fixed seed).
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
random.seed(SEED)

OUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_CUSTOMERS = 120
N_ORDERS = 300
N_RETURNS = 90
N_TICKETS = 150

FIRST_NAMES = ["Aisha", "Ravi", "Maria", "James", "Wei", "Fatima", "Diego", "Sara",
               "Liam", "Noor", "Carlos", "Yuki", "Omar", "Elena", "Tom", "Priya"]
LAST_NAMES = ["Sharma", "Khan", "Garcia", "Smith", "Chen", "Ahmed", "Rossi", "Lee",
              "Brown", "Patel", "Nguyen", "Kim", "Silva", "Muller", "Ivanov", "Diaz"]
TIERS = ["standard", "silver", "gold"]
CHANNELS = ["web", "mobile_app", "internal_wiki", "call_center", "marketplace"]
FULFILLMENT_STATUS = ["delivered", "shipped", "processing", "cancelled", "delayed"]
RETURN_REASONS = ["defective", "wrong_item", "no_longer_needed", "damaged_in_transit", "not_as_described"]
RETURN_STATUS = ["approved", "denied", "pending"]
RESOLUTION_TYPE = ["refund", "store_credit", "replacement", "none"]
TICKET_CATEGORIES = ["returns", "refunds", "escalation", "shipping", "compliance"]
TICKET_STATUS = ["open", "in_progress", "resolved", "escalated", "closed"]

def rand_date(start_days_ago=365, end_days_ago=0):
    days = random.randint(end_days_ago, start_days_ago)
    return (datetime(2026, 7, 9) - timedelta(days=days)).strftime("%Y-%m-%d")

# ---------- customers.csv ----------
customers = []
for i in range(1, N_CUSTOMERS + 1):
    cid = f"CUST-{i:05d}"
    fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
    customers.append({
        "customer_id": cid,
        "first_name": fn,
        "last_name": ln,
        "email": f"{fn.lower()}.{ln.lower()}{i}@example.com",
        "signup_date": rand_date(1000, 30),
        "customer_tier": random.choices(TIERS, weights=[0.6, 0.25, 0.15])[0],
        "region": random.choice(["APAC", "EMEA", "AMER"]),
        "account_status": random.choices(["active", "inactive", "suspended"], weights=[0.85, 0.1, 0.05])[0],
    })

with open(OUT_DIR / "customers.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(customers[0].keys()))
    w.writeheader()
    w.writerows(customers)

# ---------- orders.csv ----------
orders = []
for i in range(1, N_ORDERS + 1):
    oid = f"ORD-{i:06d}"
    cust = random.choice(customers)
    orders.append({
        "order_id": oid,
        "customer_id": cust["customer_id"],
        "order_date": rand_date(300, 1),
        "purchase_channel": random.choice(CHANNELS),
        "order_amount": round(random.uniform(15, 1500), 2),
        "fulfillment_status": random.choices(FULFILLMENT_STATUS, weights=[0.55, 0.2, 0.1, 0.05, 0.1])[0],
        "item_condition": random.choices(["new", "defective", "damaged"], weights=[0.85, 0.1, 0.05])[0],
    })

with open(OUT_DIR / "orders.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(orders[0].keys()))
    w.writeheader()
    w.writerows(orders)

# ---------- returns.csv ----------
returns = []
sampled_orders = random.sample(orders, N_RETURNS)
for i, order in enumerate(sampled_orders, start=1):
    rid = f"RET-{i:05d}"
    request_date = rand_date(60, 1)
    returns.append({
        "return_id": rid,
        "order_id": order["order_id"],
        "customer_id": order["customer_id"],
        "reason_code": random.choice(RETURN_REASONS),
        "approval_status": random.choices(RETURN_STATUS, weights=[0.55, 0.2, 0.25])[0],
        "resolution_type": random.choice(RESOLUTION_TYPE),
        "request_date": request_date,
        "fraud_score": random.randint(0, 100),
    })

with open(OUT_DIR / "returns.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(returns[0].keys()))
    w.writeheader()
    w.writerows(returns)

# ---------- support_tickets.csv ----------
tickets = []
for i in range(1, N_TICKETS + 1):
    tid = f"TCK-{i:05d}"
    cust = random.choice(customers)
    maybe_order = random.choice(orders) if random.random() < 0.7 else None
    category = random.choice(TICKET_CATEGORIES)
    tickets.append({
        "ticket_id": tid,
        "customer_id": cust["customer_id"],
        "order_id": maybe_order["order_id"] if maybe_order else "",
        "category": category,
        "subject": f"{category.title()} inquiry from {cust['first_name']}",
        "status": random.choice(TICKET_STATUS),
        "severity": random.choices(["low", "medium", "high"], weights=[0.5, 0.35, 0.15])[0],
        "created_at": rand_date(90, 0) + " " + f"{random.randint(0,23):02d}:{random.randint(0,59):02d}:00",
    })

with open(OUT_DIR / "support_tickets.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(tickets[0].keys()))
    w.writeheader()
    w.writerows(tickets)

# ---------- entity_activity_audit_log.csv (header only; app appends at runtime) ----------
audit_fields = ["log_id", "timestamp", "actor", "action", "entity_type", "entity_id", "details"]
with open(OUT_DIR / "entity_activity_audit_log.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=audit_fields)
    w.writeheader()

print(f"Wrote {len(customers)} customers, {len(orders)} orders, {len(returns)} returns, "
      f"{len(tickets)} tickets to {OUT_DIR}")
