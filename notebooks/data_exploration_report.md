# Data Exploration Report

*Updated: now reflects the real uploaded datasets (customers.csv, orders.csv,
returns.csv, support_tickets.csv, entity_activity_audit_log.csv,
operations_policies.json), replacing the earlier synthetic placeholders.*

## 1. Files & Schemas

| File | Rows | Columns |
|---|---|---|
| `operations_policies.json` | 1,050 | `id, question, answer, category, source` |
| `customers.csv` | 93,551 | `customer_id, email, name, first_name, last_name, country, state, city, street_address, postal_code, signup_date, age, gender, occupation, marital_status, household_size, segment, lifetime_value, loyalty_points, preferred_channel, preferred_language, phone, account_status, referral_source, email_opt_in, sms_opt_in, last_login_date, created_at` |
| `orders.csv` | 114,387 | `order_id, customer_id, order_date, channel, total_amount, subtotal, tax_amount, shipping_cost, discount_amount, status, payment_method, payment_last4, shipping_country, shipping_state, shipping_city, shipping_address, billing_city, carrier, tracking_number, promo_code, is_gift, fulfillment_center, delivery_date` |
| `returns.csv` | 152,285 | `return_id, order_id, customer_id, reason, status, request_date, resolution_type, refund_amount, agent_notes` |
| `support_tickets.csv` | 98,754 | `ticket_id, customer_id, order_id, category, priority, status, subject, description, created_date, resolution_time_hours` |
| `entity_activity_audit_log.csv` | 107,234 (pre-existing) | `audit_id, entity_type, entity_id, action, actor, timestamp, ip_address, details, status, correlation_id` |

No missing values were found in any of the CSVs (all key/categorical/date fields fully populated).

## 2. Category & Status Distributions

**`support_tickets.category`** (5 values, ~19.6-19.9k each — well balanced):
`returns`, `product`, `shipping`, `account`, `billing`

**`operations_policies.category`** (5 values, 210 each — perfectly balanced):
`returns`, `refunds`, `escalation`, `shipping`, `compliance`

⚠️ **These two vocabularies don't match 1:1.** `support_tickets.csv` has no
`refunds`, `escalation`, or `compliance` category, and the policy corpus has
no `product` or `account` category. The pipeline resolves this with an
explicit routing table (`config.TICKET_TO_POLICY_CATEGORY`):

| Ticket category | Routes to policy department | Rationale |
|---|---|---|
| `returns` | `returns` | direct match |
| `shipping` | `shipping` | direct match |
| `billing` | `refunds` | billing disputes are governed by refund policy |
| `account` | `escalation` | account-standing issues route to escalation policy |
| `product` | `returns` | product defect/quality complaints route to returns policy |

**`returns.reason`**: `wrong_item`, `damaged`, `changed_mind`, `defective`, `late_delivery` (~30.2-30.7k each)
**`returns.status`**: `pending`, `denied`, `approved`, `escalated` (~38k each)
**`orders.status`**: `completed`, `pending`, `returned`, `cancelled`, `shipped` (~22.7-23.1k each)

## 3. ⚠️ Referential Integrity Finding (important)

The five relational files were evidently generated **independently**, not
with enforced foreign keys. Measured overlap:

| Join | % of rows that resolve |
|---|---|
| `support_tickets.order_id` → `orders.order_id` | **14.5%** |
| `support_tickets.customer_id` → `customers.customer_id` | **62.4%** |
| `returns.order_id` → `orders.order_id` | **14.2%** |
| `returns.customer_id` → `customers.customer_id` | **62.4%** |
| `orders.customer_id` → `customers.customer_id` | **62.5%** |

**Implication**: for any given ticket, don't assume its `order_id` will find
a matching order — roughly 6 in 7 won't. The pipeline (`case_context.py`)
already handles this gracefully: it includes whichever of
`ticket`/`order`/`return`/`customer` actually resolve and simply omits the
rest, rather than erroring. This is documented rather than "fixed," since
enforcing artificial consistency would misrepresent data quality issues a
real production system would also need to handle.

A ticket where the **full chain resolves** (ticket → order → return →
customer) for testing/demo purposes: **`T0000004`** (order `O00075875`,
return `R0088336`, customer `C056793`).

## 4. Join Diagram

```
customers.csv (customer_id) ─┬── orders.csv (customer_id → order_id)     [62.5% resolve]
                              │        │
                              │        └── returns.csv (order_id)         [14.2% resolve]
                              │
                              └── support_tickets.csv (customer_id, order_id)
                                       [customer: 62.4% / order: 14.5% resolve]

support_tickets.category ──► TICKET_TO_POLICY_CATEGORY map ──► operations_policies.category filter
```

## 5. Policy Corpus Notes

- `operations_policies.json` content is unchanged from the earlier
  placeholder version reviewed before real data was uploaded — it was
  already the authoritative, provided corpus. Policy `answer` texts are
  templated (many near-duplicate passages within a department, differing
  mainly in numeric thresholds), which affects exact-citation-ID scoring
  under the offline embedder (see `PROJECT_SUMMARY.md`).

## 6. Pre-existing Audit Log

`entity_activity_audit_log.csv` arrived with 107,234 historical rows
(`entity_type` ∈ `order/ticket/customer/claim`, `action` ∈
`create/update/delete/view/export`, `status` ∈ `success/failure/pending`).
The assistant's own query logging (`services/audit.py`) was written to
**match this exact schema** and appends new rows (`entity_type=policy_query`
by default, or the real entity type when a ticket/order/customer was
referenced) with auto-incrementing `AUD#########` IDs continuing from the
existing max, so the assistant's activity sits in the same audit trail as
every other system action rather than a separate log file.
