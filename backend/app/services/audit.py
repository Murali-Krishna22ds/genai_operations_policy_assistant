"""
Compliance audit trail (Objective 5): every query + response is appended to
entity_activity_audit_log.csv, matching the REAL production schema found in
the uploaded file:

    audit_id, entity_type, entity_id, action, actor, timestamp,
    ip_address, details, status, correlation_id

`entity_type`/`entity_id` point at whichever real entity the query was about
(ticket/order/customer, per the existing convention in the log), falling back
to a new `policy_query` entity_type for standalone questions with no case
reference. `details` carries a compact JSON blob with the query, answer,
citation policy_ids, groundedness, and generation mode — kept in one field so
we don't have to alter the existing column set that other tooling may already
depend on.
"""
import csv
import json
import uuid
from datetime import datetime, timezone

from app import config

FIELDS = ["audit_id", "entity_type", "entity_id", "action", "actor",
          "timestamp", "ip_address", "details", "status", "correlation_id"]


def _next_audit_id() -> str:
    # Real IDs follow AUD%011d (e.g. AUD000000001). Keep counting up from
    # whatever's already in the file so ours don't collide with history.
    if not config.AUDIT_LOG_CSV.exists() or config.AUDIT_LOG_CSV.stat().st_size == 0:
        return "AUD000000001"
    try:
        with open(config.AUDIT_LOG_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            max_n = 0
            for row in reader:
                aid = row.get("audit_id", "")
                digits = "".join(ch for ch in aid if ch.isdigit())
                if digits:
                    max_n = max(max_n, int(digits))
            return f"AUD{max_n + 1:09d}"
    except Exception:
        return f"AUD{uuid.uuid4().int % 10**9:09d}"


def log_query(actor: str, query: str, answer: str, citation_ids: list,
              grounded: bool, mode: str, entity_id: str = "",
              entity_type: str = "policy_query", ip_address: str = "internal-api") -> str:
    audit_id = _next_audit_id()
    status = "success" if grounded or mode != "extractive_fallback_error" else "failure"

    row = {
        "audit_id": audit_id,
        "entity_type": entity_type,
        "entity_id": entity_id or audit_id,
        "action": "query",
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "ip_address": ip_address,
        "details": json.dumps({
            "query": query,
            "answer": answer,
            "citations": citation_ids,
            "grounded": grounded,
            "mode": mode,
        }, ensure_ascii=False),
        "status": status,
        "correlation_id": str(uuid.uuid4()),
    }

    file_exists = config.AUDIT_LOG_CSV.exists() and config.AUDIT_LOG_CSV.stat().st_size > 0
    with open(config.AUDIT_LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return audit_id
