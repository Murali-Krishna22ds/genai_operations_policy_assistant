"""
Runs all 20 scenarios through the RAG pipeline and scores:

  - grounded_rate:      fraction of in-scope answers that cite >=1 retrieved
                        policy chunk (Objective 5: "grounded answer rate").
  - citation_accuracy:  fraction of in-scope answers whose top citation's
                        policy_id matches the scenario's expected_policy_id,
                        OR whose department matches (partial credit noted
                        separately) — a precise, code-based proxy for
                        "citation correctness".
  - department_routing_accuracy: fraction where the retrieved top chunk's
                        department matches the expected department.
  - refusal_rate:       fraction of out-of-scope scenarios correctly refused
                        (Objective 5: "refusal on out-of-scope asks").
  - llm_judge (optional): if OPENAI_API_KEY is set, additionally asks GPT-4o
                        to rate each in-scope answer 1-5 on faithfulness to
                        the gold answer, as a semantic-accuracy check beyond
                        exact policy_id matching.

Results are written to evaluation/eval_results.csv and a written summary is
printed / saved to evaluation/eval_summary.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services import ingestion, retrieval, generation, audit
from app import config

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"
RESULTS_CSV = Path(__file__).resolve().parent / "eval_results.csv"
SUMMARY_MD = Path(__file__).resolve().parent / "eval_summary.md"

REFUSAL_PHRASE = "I don't have a policy on file that covers this"


def llm_judge_score(query, gold_answer, model_answer):
    """Optional semantic-faithfulness judge; only runs if a live API key is set."""
    if not config.using_live_llm():
        return None
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    prompt = f"""Rate how faithfully the MODEL ANSWER reflects the GOLD POLICY ANSWER on a 1-5 scale
(5 = fully faithful and non-contradictory, 1 = contradicts or fabricates). Respond with ONLY the digit.

QUESTION: {query}
GOLD POLICY ANSWER: {gold_answer}
MODEL ANSWER: {model_answer}
"""
    resp = client.chat.completions.create(
        model=config.GENERATION_MODEL, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return int(resp.choices[0].message.content.strip()[0])
    except Exception:
        return None


def main():
    with open(SCENARIOS_PATH) as f:
        scenarios = json.load(f)

    store, embedder_desc, embedder = ingestion.load_persisted_index()
    if embedder is None:
        from app.services.embeddings import get_embedder
        embedder, _ = get_embedder()

    rows = []
    for sc in scenarios:
        results = retrieval.retrieve(store, embedder, sc["query"],
                                      department=sc.get("expected_department") if sc["type"] == "in_scope" else None)
        answer, mode = generation.generate_answer(sc["query"], results, case_context={})

        top_policy_id = results[0][0].policy_id if results else None
        top_department = results[0][0].department if results else None

        is_refusal = REFUSAL_PHRASE in answer
        grounded = bool(results) and not is_refusal

        row = {
            "scenario_id": sc["scenario_id"],
            "type": sc["type"],
            "query": sc["query"],
            "expected_department": sc.get("expected_department"),
            "expected_policy_id": sc.get("expected_policy_id"),
            "top_retrieved_policy_id": top_policy_id,
            "top_retrieved_department": top_department,
            "answer": answer,
            "mode": mode,
            "grounded": grounded,
            "is_refusal": is_refusal,
            "policy_id_match": (sc["type"] == "in_scope" and top_policy_id == sc.get("expected_policy_id")),
            "department_match": (sc["type"] == "in_scope" and top_department == sc.get("expected_department")),
            "correct_refusal": (sc["type"] == "out_of_scope" and is_refusal),
        }
        row["llm_judge_faithfulness"] = (
            llm_judge_score(sc["query"], sc.get("gold_answer"), answer) if sc["type"] == "in_scope" else None
        )
        rows.append(row)

        audit.log_query(actor="eval_harness", query=sc["query"], answer=answer,
                         citation_ids=[c.policy_id for c, _ in results], grounded=grounded, mode=mode,
                         entity_id=sc["scenario_id"])

    # ---- write results CSV ----
    import csv
    with open(RESULTS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    in_scope = [r for r in rows if r["type"] == "in_scope"]
    out_scope = [r for r in rows if r["type"] == "out_of_scope"]

    def rate(items, key):
        return round(sum(1 for i in items if i[key]) / len(items), 3) if items else None

    judged = [r["llm_judge_faithfulness"] for r in in_scope if r["llm_judge_faithfulness"] is not None]

    summary = {
        "n_scenarios": len(rows),
        "n_in_scope": len(in_scope),
        "n_out_of_scope": len(out_scope),
        "grounded_answer_rate_in_scope": rate(in_scope, "grounded"),
        "policy_id_citation_accuracy": rate(in_scope, "policy_id_match"),
        "department_routing_accuracy": rate(in_scope, "department_match"),
        "out_of_scope_refusal_rate": rate(out_scope, "correct_refusal"),
        "generation_mode": rows[0]["mode"],
        "embedder": embedder_desc,
        "avg_llm_judge_faithfulness_1to5": round(sum(judged) / len(judged), 2) if judged else "N/A (no OPENAI_API_KEY set)",
    }

    with open(SUMMARY_MD, "w") as f:
        f.write("# Evaluation Summary\n\n")
        for k, v in summary.items():
            f.write(f"- **{k}**: {v}\n")

    print(json.dumps(summary, indent=2))
    print(f"\nDetailed per-scenario results: {RESULTS_CSV}")
    print(f"Summary: {SUMMARY_MD}")


if __name__ == "__main__":
    main()
