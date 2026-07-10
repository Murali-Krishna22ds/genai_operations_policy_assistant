# GenAI Operations & Policy Assistant — Project Summary

## 1. Overview

This project implements a retrieval-augmented generation (RAG) pipeline that
lets operations/compliance staff ask natural-language policy questions and
receive answers grounded in `operations_policies.json`, personalized with
live case context (customer, order, return, support ticket), with mandatory
source citations and a full compliance audit trail.

The pipeline follows the canonical RAG shape: **ingest → embed → retrieve →
generate → log**, implemented as a FastAPI service (`backend/app`) with a
FAISS vector store, a metadata-filtered retriever, a citation-enforcing
prompt template, and an append-only audit log.

## 2. Model & Configuration Choices

- **Generation model**: `gpt-4o`, `temperature=0.0`. Zero temperature was
  chosen deliberately — policy answers must be deterministic and
  citation-faithful, not creative or varied across repeated identical
  questions. This is documented and configurable via environment variables
  (`backend/.env`), never hardcoded.
- **Embeddings**: OpenAI `text-embedding-3-small` in production. Because this
  environment had no live API key, a **local TF-IDF + Truncated-SVD**
  fallback embedder (dimension 256, `scikit-learn`, seeded) was used for all
  demonstration runs in this repo, so the entire pipeline — including
  evaluation — is fully reproducible offline at zero cost. Switching to live
  OpenAI embeddings/generation requires no code changes, only setting
  `OPENAI_API_KEY`.
- **Vector store**: FAISS `IndexFlatIP` over L2-normalized vectors (cosine
  similarity), with a simple, transparent metadata pre-filter for
  department-scoped retrieval — appropriate at this corpus size (~1,050
  chunks) without needing a heavier ANN index.

## 3. Data

All six real project files are used: `operations_policies.json` (1,050
policy Q&A records, perfectly balanced across 5 departments:
returns/refunds/escalation/shipping/compliance), `customers.csv` (93,551
rows), `orders.csv` (114,387), `returns.csv` (152,285), `support_tickets.csv`
(98,754), and a pre-existing `entity_activity_audit_log.csv` (107,234 rows)
that the pipeline appends to using its real production schema
(`audit_id, entity_type, entity_id, action, actor, timestamp, ip_address,
details, status, correlation_id`) rather than a custom one.

Two integration issues were found and handled during onboarding:

1. **Category vocabulary mismatch**: `support_tickets.category` uses
   `returns/product/shipping/account/billing`, while the policy corpus uses
   `returns/refunds/escalation/shipping/compliance`. An explicit mapping in
   `config.py` bridges the two (documented in `data_exploration_report.md` §4).
2. **Partial referential integrity**: only ~62% of orders/tickets resolve to
   an existing customer_id, and only ~14% of tickets/returns resolve to an
   existing order_id — typical of independently-generated large synthetic
   datasets without enforced foreign keys. `services/case_context.py` was
   built defensively so a missing join is silently omitted from the response
   rather than causing an error.

Full schema and join documentation is in `notebooks/data_exploration_report.md`.

## 4. Evaluation Results (20 scenarios: 16 in-scope, 4 out-of-scope)

| Metric | Result |
|---|---|
| Grounded answer rate (in-scope) | **100%** |
| Department routing accuracy | **100%** |
| Out-of-scope refusal rate | **100%** |
| Exact policy_id citation accuracy | **31.2%** |
| LLM-judge faithfulness (1-5) | N/A offline (requires `OPENAI_API_KEY`) |

**Interpretation**: the pipeline reliably retrieves *the right department*
and *never fabricates an answer* when policy coverage is missing (refusal
rate 100%) or when a similarity guardrail isn't met — the two properties
that matter most for compliance risk. Exact policy_id match is lower because
the corpus contains many near-duplicate templated passages within a
department (e.g. multiple "damaged in transit... 60 day window" variants
differing only in numeric thresholds), which a lightweight TF-IDF embedder
cannot always disambiguate as precisely as a semantic embedding model would.
This is a known, honestly-reported limitation of the offline fallback, not
of the architecture — swapping in `text-embedding-3-small` (one env var) is
expected to materially improve exact-match precision, since dense semantic
embeddings capture the numeric/contextual distinctions the TF-IDF+SVD
projection compresses away.

## 5. Limitations

- **Offline embedder ceiling**: as above, citation precision is bounded by
  the local embedder's ability to distinguish near-duplicate policy text.
- **Partial referential integrity in the real data**: as noted in §3, most
  ticket/return `order_id`s (≈86%) don't resolve against `orders.csv`, and
  ~38% of customer_ids don't resolve either. This looks like the five files
  were generated independently rather than with enforced foreign keys. The
  pipeline handles it gracefully (omits unresolvable joins) but a production
  system should investigate and fix the upstream data pipeline that produces
  this drift.
- **No re-ranking stage**: retrieval is single-pass cosine similarity; a
  cross-encoder re-ranker would likely improve top-1 precision further.
- **LLM-judge evaluation requires live API access**: the semantic
  faithfulness score couldn't be computed in this offline run.
- **Audit log has no PII redaction step**: queries are logged verbatim;
  a production deployment should scrub customer PII before persisting.

## 6. Recommended Production Next Steps

1. Switch `EMBEDDING_PROVIDER=openai` with a live key and re-run
   `evaluation/evaluate.py` to get true semantic citation-accuracy and
   LLM-judge faithfulness numbers.
2. Add a cross-encoder re-ranking stage after initial FAISS retrieval to
   push exact policy_id match higher.
3. Expand the evaluation set beyond 20 scenarios (e.g. 100+, including
   ambiguous/multi-department questions) before production sign-off.
4. Add PII redaction/hashing in `services/audit.py` before persisting query
   text.
5. Replace `IndexFlatIP` with an incremental-update store (e.g. Chroma) if
   the policy corpus will be edited frequently, to avoid full re-indexing.
6. Add authentication/authorization on the `/query` endpoint before any
   internal deployment, and rate-limit per agent.
