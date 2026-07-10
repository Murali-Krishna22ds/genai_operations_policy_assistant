"""
Builds a 20-scenario evaluation set:
  - 16 in-scope questions sampled from operations_policies.json (across all
    5 departments) where we know the expected policy_id, department, and a
    gold answer (the corpus's own "answer" field) to check citation/accuracy.
  - 4 deliberately out-of-scope questions (unrelated to any policy in the
    corpus) to test refusal behavior (Objective 5: "refusal on out-of-scope asks").
"""
import json
import random
from pathlib import Path

random.seed(7)

DATA_PATH = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "operations_policies.json"
OUT_PATH = Path(__file__).resolve().parent / "scenarios.json"

OUT_OF_SCOPE_QUESTIONS = [
    "What is the current federal minimum wage in California?",
    "Can you recommend a good project management tool for our team?",
    "What's the weather forecast for our warehouse city tomorrow?",
    "How do I reset my personal home Wi-Fi router?",
]


def main():
    with open(DATA_PATH) as f:
        records = json.load(f)

    by_dept = {}
    for r in records:
        by_dept.setdefault(r["category"], []).append(r)

    # Distribute 16 in-scope scenarios evenly across all 5 departments so
    # every policy category is represented in the eval set.
    depts = list(by_dept.keys())
    per_dept_counts = [16 // len(depts)] * len(depts)
    for i in range(16 % len(depts)):
        per_dept_counts[i] += 1

    scenarios = []
    sid = 1
    for dept, n in zip(depts, per_dept_counts):
        sample = random.sample(by_dept[dept], min(n, len(by_dept[dept])))
        for r in sample:
            q = r["question"].split("]", 1)[-1].strip()
            scenarios.append({
                "scenario_id": f"S{sid:02d}",
                "type": "in_scope",
                "query": q,
                "expected_department": dept,
                "expected_policy_id": r["id"],
                "gold_answer": r["answer"],
            })
            sid += 1

    for q in OUT_OF_SCOPE_QUESTIONS:
        scenarios.append({
            "scenario_id": f"S{sid:02d}",
            "type": "out_of_scope",
            "query": q,
            "expected_department": None,
            "expected_policy_id": None,
            "gold_answer": None,
        })
        sid += 1

    with open(OUT_PATH, "w") as f:
        json.dump(scenarios, f, indent=2)

    print(f"Wrote {len(scenarios)} scenarios to {OUT_PATH}")


if __name__ == "__main__":
    main()
