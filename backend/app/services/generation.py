"""
Generation (Objective 1 & 3): builds a RAG prompt requiring the model to
(a) answer only from retrieved policy passages, (b) quote/attribute the
owning source for every claim, (c) refuse when the retrieved context does not
cover the question ("out-of-scope refusal", scored in evaluation).

Two modes:
  - live_llm: calls OpenAI chat completions (config.GENERATION_MODEL,
    temperature=config.GENERATION_TEMPERATURE — 0.0 by default for citation
    fidelity / low hallucination, per Objective 1).
  - extractive_fallback: used automatically when OPENAI_API_KEY is not set.
    Deterministically composes an answer from the top retrieved passage(s)
    with explicit source attribution, so the pipeline is fully testable
    without live API access or cost.
"""
from typing import List, Tuple
from app import config
from app.services.vectorstore import Chunk

SYSTEM_PROMPT = """You are an Operations & Compliance policy assistant for retail staff.

STRICT RULES:
1. Answer ONLY using the POLICY CONTEXT provided below. Never use outside/parametric knowledge.
2. Every factual claim must be attributable to a specific policy passage. Cite the policy_id
   and source in parentheses immediately after the claim, e.g. (policy_id: Q00042, source: Operations Policy Manual v2.1).
3. If the POLICY CONTEXT does not contain enough information to answer, respond exactly with:
   "I don't have a policy on file that covers this. Please escalate to the Policy Office."
   Do not guess or fabricate a policy.
4. If live case context (customer/order/return/ticket) is provided, incorporate it to personalize
   the guidance, but still ground every policy claim in the POLICY CONTEXT, not the case data.
5. Be concise: 2-5 sentences plus citations.
"""

def _format_context(chunks: List[Tuple[Chunk, float]]) -> str:
    lines = []
    for chunk, score in chunks:
        lines.append(f"- [policy_id: {chunk.policy_id} | department: {chunk.department} | "
                      f"source: {chunk.source} | relevance: {score:.3f}]\n  {chunk.text}")
    return "\n".join(lines) if lines else "(no relevant policy passages retrieved)"


def _format_case_context(case_context: dict) -> str:
    if not case_context or all(v is None for v in case_context.values()):
        return "(no live case context provided)"
    lines = []
    for key in ("ticket", "order", "return", "customer"):
        if case_context.get(key):
            lines.append(f"{key.upper()}: {case_context[key]}")
    if case_context.get("routed_policy_department"):
        lines.append(f"Routed policy department: {case_context['routed_policy_department']}")
    return "\n".join(lines) if lines else "(no live case context provided)"


def build_user_prompt(query: str, chunks: List[Tuple[Chunk, float]], case_context: dict) -> str:
    return f"""POLICY CONTEXT:
{_format_context(chunks)}

LIVE CASE CONTEXT:
{_format_case_context(case_context)}

STAFF QUESTION:
{query}
"""


def generate_live(query: str, chunks: List[Tuple[Chunk, float]], case_context: dict) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    user_prompt = build_user_prompt(query, chunks, case_context)
    resp = client.chat.completions.create(
        model=config.GENERATION_MODEL,
        temperature=config.GENERATION_TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content.strip()


def generate_extractive_fallback(query: str, chunks: List[Tuple[Chunk, float]], case_context: dict) -> str:
    if not chunks:
        return "I don't have a policy on file that covers this. Please escalate to the Policy Office."
    top_chunk, score = chunks[0]
    # Low-similarity guardrail: refuse rather than force an unrelated match.
    if score < 0.15:
        return "I don't have a policy on file that covers this. Please escalate to the Policy Office."
    routed = case_context.get("routed_policy_department") if case_context else None
    prefix = ""
    if routed and routed != top_chunk.department:
        prefix = f"[Note: routed department '{routed}' had no strong match; showing closest policy instead] "
    return (f"{prefix}{top_chunk.text} "
            f"(policy_id: {top_chunk.policy_id}, department: {top_chunk.department}, source: {top_chunk.source})")


def generate_answer(query: str, chunks: List[Tuple[Chunk, float]], case_context: dict) -> Tuple[str, str]:
    """Returns (answer, mode)."""
    if config.using_live_llm():
        try:
            return generate_live(query, chunks, case_context), "live_llm"
        except Exception as e:  # network/quota errors -> degrade gracefully
            fallback = generate_extractive_fallback(query, chunks, case_context)
            return f"[LLM call failed ({e}); extractive fallback used] {fallback}", "extractive_fallback_error"
    return generate_extractive_fallback(query, chunks, case_context), "extractive_fallback"
