# GenAI Operations & Policy Assistant

A retrieval-augmented generation (RAG) pipeline that grounds operations/compliance
policy Q&A in `operations_policies.json`, personalizes guidance with live case
context from orders/returns/support tickets, enforces mandatory source
citations, and writes every query to a compliance audit log.

> ⚠️ **A note on API keys**: this project never hardcodes credentials. Set
> `OPENAI_API_KEY` in a local `.env` file (copy `.env.example`) or as an
> environment variable. If it's unset, the pipeline automatically runs in a
> fully offline **extractive fallback** mode (local TF-IDF embeddings +
> closest-passage answers) so you can build/test/evaluate everything without
> any API access or cost. If you ever paste a real key into a chat or commit
> it to a repo, treat it as compromised and rotate it immediately.

## Architecture

```
operations_policies.json ──► ingestion.py ──► embeddings.py ──► FAISS vector store
                                                                        │
support_tickets/orders/returns/customers.csv ──► case_context.py       │
                                     │                                  │
                                     ▼                                 ▼
                            routers/query.py ──► retrieval.py (metadata-filtered top-k)
                                     │                                  │
                                     ▼                                  ▼
                            generation.py (mandatory-citation prompt, GPT-4o or extractive fallback)
                                     │
                                     ▼
                            audit.py ──► entity_activity_audit_log.csv
```

## Data

Real project data is used throughout (not synthetic placeholders):
`operations_policies.json` (1,050 records), `customers.csv` (93,551),
`orders.csv` (114,387), `returns.csv` (152,285), `support_tickets.csv`
(98,754), and a pre-existing `entity_activity_audit_log.csv` (107,234 rows)
that the API appends to using its exact real schema. Full schema, join
diagram, and a data-quality note about partial referential integrity between
tables (~62% customer↔order match, ~14% ticket/return↔order match — the
pipeline handles this gracefully) are in `notebooks/data_exploration_report.md`.

## Objective → Implementation Map

| Objective | Where |
|---|---|
| 1. Foundation model selection, temperature | `backend/app/config.py` (`GENERATION_MODEL=gpt-4o`, `GENERATION_TEMPERATURE=0.0` — deterministic, low-hallucination) + `services/generation.py` |
| 2. Index by department/title/policy_id, chunk-level embeddings + metadata | `services/ingestion.py`, `services/vectorstore.py`, `services/embeddings.py` |
| 3. RAG prompt with mandatory citations, cross-referencing returns/orders | `services/generation.py` (`SYSTEM_PROMPT`), `services/case_context.py` |
| 4. Ticket-category-based retrieval routing | `config.TICKET_TO_POLICY_CATEGORY`, `services/case_context.py`, `routers/query.py` |
| 5. Audit logging + 20-scenario evaluation | `services/audit.py`, `evaluation/build_scenarios.py`, `evaluation/evaluate.py` |
| 6. Deployed pipeline (ingest → embed → retrieve → generate) | `backend/app/main.py` (FastAPI), documented below |

## Streamlit UI

A browser-based UI (`streamlit_app.py`) lets staff interact with the
assistant without calling the API directly. It talks to the pipeline
in-process — no need to also run `uvicorn` — and works in both live-GPT-4o
and offline-fallback modes.

```bash
pip install -r backend/requirements.txt   # includes streamlit
PYTHONPATH=backend streamlit run streamlit_app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501). Features:

- **Sidebar**: live system status (generation mode, model, embedder,
  chunk count) and an optional ticket/order/customer ID lookup to pull real
  case context into your question — includes a one-click button to load
  `T0000004`, a ticket whose full order→return→customer chain resolves.
- **Main panel**: ask a question, see the grounded answer, an expandable
  citations table (policy_id/department/source/relevance/text), and the
  resolved case context.
- **Audit trail**: every question asked in the UI is appended to
  `entity_activity_audit_log.csv` exactly like API calls are; the last 15
  entries are viewable at the bottom of the page.

## API Setup (optional — only needed if you want the REST endpoint too)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # then edit .env and add OPENAI_API_KEY for live GPT-4 mode
```

`backend/app/data/` already contains the real project files (customers,
orders, returns, support_tickets, entity_activity_audit_log,
operations_policies.json). If you ever need to regenerate placeholder data
instead (e.g. for a quick demo without the real files), run
`python3 scripts/generate_synthetic_data.py` — but note this will overwrite
the real CSVs, so only do this in a scratch copy.

Build the vector index:

```bash
PYTHONPATH=. python3 -m app.services.ingestion
```

Run the API:

```bash
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

## Example request

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Can this customer get a refund for a defective item they returned?",
    "ticket_id": "T0000004",
    "actor": "agent_maria"
  }'
```

(`T0000004` is a real ticket whose order/return/customer chain all resolve —
see `notebooks/data_exploration_report.md` §3 for why most tickets in this
dataset only partially resolve, and how the pipeline handles that.)

Response includes: a citation-grounded `answer`, the retrieved `citations`
(policy_id/department/source/score), the joined `case_context`, a `grounded`
flag, the `mode` used (`live_llm` or `extractive_fallback`), and an
`audit_log_id` you can look up in `entity_activity_audit_log.csv`.

## Evaluation

```bash
cd evaluation
python3 build_scenarios.py   # regenerate the 20-scenario eval set (deterministic, seed=7)
python3 evaluate.py          # runs the pipeline over all 20 and scores it
```

Outputs `eval_results.csv` (per-scenario detail) and `eval_summary.md`
(aggregate metrics: grounded answer rate, policy_id citation accuracy,
department routing accuracy, out-of-scope refusal rate, and — if
`OPENAI_API_KEY` is set — an LLM-judge faithfulness score 1-5).

## Safety guardrails documented

- System prompt forbids answering from parametric knowledge — grounding is
  mandatory; the model is instructed to refuse when retrieved context is
  insufficient (see `services/generation.py::SYSTEM_PROMPT`).
- A similarity-score guardrail (`score < 0.15`) triggers refusal in
  extractive-fallback mode too, so a low-quality nearest match isn't
  presented as authoritative.
- All queries/answers/citations are appended to the audit CSV — nothing is
  answered "off the record."
- `.env` is git-ignored; no secrets are ever written to source files.

## Reproducibility

- Synthetic data generation, TF-IDF embedding, and evaluation scenario
  sampling are all seeded (`seed=42` / `seed=7`) for reproducible results.
- `services/embeddings.py` documents the exact embedding model/version in
  every persisted index (`embedder_desc`), so index provenance is always
  inspectable via `/health`.
