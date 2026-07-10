"""
Streamlit front-end for the GenAI Operations & Policy Assistant.

Talks directly to the pipeline in-process (ingestion/retrieval/generation/
case_context/audit) -- no need to run the FastAPI server separately. Run with:

    cd project
    PYTHONPATH=backend streamlit run streamlit_app.py

If OPENAI_API_KEY is set (backend/.env), answers use live GPT-4o. Otherwise
the app runs in the same offline extractive-fallback mode as the API.
"""
import sys
import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

# Make the backend package importable regardless of the working directory
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import config
from app.services import ingestion, retrieval, generation, case_context as case_ctx_service, audit

st.set_page_config(page_title="Ops & Policy Assistant", page_icon="📋", layout="wide")


@st.cache_resource(show_spinner="Loading policy index...")
def load_pipeline():
    store, embedder_desc, embedder = ingestion.load_persisted_index()
    if embedder is None:
        from app.services.embeddings import get_embedder
        embedder, _ = get_embedder()
    return store, embedder_desc, embedder


store, embedder_desc, embedder = load_pipeline()

if "history" not in st.session_state:
    st.session_state.history = []

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("📋 System Status")
    mode = "🟢 Live GPT-4o" if config.using_live_llm() else "🟡 Offline extractive fallback"
    st.markdown(f"**Generation mode:** {mode}")
    st.markdown(f"**Model:** `{config.GENERATION_MODEL}` (temp={config.GENERATION_TEMPERATURE})")
    st.markdown(f"**Embedder:** `{embedder_desc}`")
    st.markdown(f"**Policy chunks indexed:** {len(store.chunks)}")
    if not config.using_live_llm():
        st.info("No `OPENAI_API_KEY` set — running fully offline at zero cost. "
                 "Add a key to `backend/.env` for live GPT-4o answers.", icon="ℹ️")

    st.divider()
    st.header("🔎 Live Case Lookup (optional)")
    st.caption("Pull real order/return/customer context into your question. "
               "Note: most tickets in this dataset only *partially* resolve "
               "(~14% have a matching order, ~62% a matching customer) — "
               "that's a real data-quality property, not a bug.")
    ticket_id = st.text_input("Ticket ID", placeholder="e.g. T0000004")
    order_id = st.text_input("Order ID (optional)", placeholder="e.g. O00075875")
    customer_id = st.text_input("Customer ID (optional)", placeholder="e.g. C056793")
    actor = st.text_input("Your agent name/ID", value="agent_demo")

    if st.button("Use known fully-resolving demo ticket (T0000004)"):
        st.session_state["_prefill_ticket"] = "T0000004"
        st.rerun()

if st.session_state.get("_prefill_ticket"):
    ticket_id = st.session_state.pop("_prefill_ticket")

# ---------------- Main ----------------
st.title("Operations & Policy Assistant")
st.caption("Ask a policy question grounded in `operations_policies.json`, with live case context and mandatory citations.")

query = st.text_area(
    "Staff question",
    placeholder="e.g. Can this customer get a refund for a defective item they returned?",
    height=90,
)

col1, col2 = st.columns([1, 5])
with col1:
    submitted = st.button("Ask", type="primary", use_container_width=True)

if submitted:
    if not query.strip():
        st.warning("Enter a question first.")
    else:
        with st.spinner("Retrieving policy context and generating answer..."):
            case_context = case_ctx_service.get_case_context(
                ticket_id=ticket_id or None,
                order_id=order_id or None,
                customer_id=customer_id or None,
            )
            department = case_context.get("routed_policy_department")
            results = retrieval.retrieve(store, embedder, query, department=department)
            answer, mode_used = generation.generate_answer(query, results, case_context)
            grounded = len(results) > 0 and "I don't have a policy on file" not in answer

            citation_ids = [c.policy_id for c, _ in results]
            log_id = audit.log_query(
                actor=actor or "unknown_agent", query=query, answer=answer,
                citation_ids=citation_ids, grounded=grounded, mode=mode_used,
                entity_id=ticket_id or order_id or customer_id or "",
            )

        st.session_state.history.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "query": query,
            "answer": answer,
            "citations": results,
            "case_context": case_context,
            "grounded": grounded,
            "mode": mode_used,
            "audit_log_id": log_id,
        })

# ---------------- Render history (most recent first) ----------------
if not st.session_state.history:
    st.info("No questions asked yet this session. Try the sidebar's demo ticket button, then ask a question above.")

for i, turn in enumerate(st.session_state.history):
    badge = "✅ Grounded" if turn["grounded"] else "⚠️ Refused / not grounded"
    mode_badge = "🟢 live_llm" if turn["mode"] == "live_llm" else f"🟡 {turn['mode']}"

    with st.container(border=True):
        st.markdown(f"**Q ({turn['time']}):** {turn['query']}")
        st.markdown(f"**A:** {turn['answer']}")
        st.caption(f"{badge} · {mode_badge} · audit_log_id=`{turn['audit_log_id']}`")

        tab_cites, tab_case = st.tabs(["📚 Citations", "🗂️ Case Context"])

        with tab_cites:
            if turn["citations"]:
                df = pd.DataFrame([{
                    "policy_id": c.policy_id,
                    "department": c.department,
                    "source": c.source,
                    "relevance": round(score, 3),
                    "text": c.text,
                } for c, score in turn["citations"]])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.caption("No policy passages retrieved.")

        with tab_case:
            cc = turn["case_context"]
            if cc.get("routed_policy_department"):
                st.markdown(f"**Routed policy department:** `{cc['routed_policy_department']}`")
            found_any = False
            for key in ("ticket", "order", "return", "customer"):
                if cc.get(key):
                    found_any = True
                    st.markdown(f"**{key.title()}**")
                    st.json(cc[key], expanded=False)
            if not found_any:
                st.caption("No live case context resolved for the IDs provided.")

    if i < len(st.session_state.history) - 1:
        st.write("")

st.divider()
with st.expander("📜 Recent audit log entries (this session's actions appear here)"):
    try:
        audit_df = pd.read_csv(config.AUDIT_LOG_CSV, dtype=str)
        st.dataframe(audit_df.tail(15).iloc[::-1], use_container_width=True, hide_index=True)
    except Exception as e:
        st.caption(f"Could not load audit log: {e}")
