"""Retrieval regression check — run this after any change to the corpus, embedding
model, or threshold to catch exactly the kind of regressions found interactively this
session (memorization bleed, threshold miscalibration, over-aggressive query correction).

Deliberately retrieval-only, not full generation — a generation call costs 15-40s each
against chat.bebs.dev, which would make this too slow to run routinely as a regression
check. Retrieval is where corpus/threshold/embedding-model changes actually bite.

Usage:
    cd "AI Recipe Masterclass/src" && python3 -m rag.run_eval
"""

import json
import logging
from pathlib import Path

from rag.config import RecipeRAGConfig
from rag.pipeline import RecipeRAGPipeline

logging.basicConfig(level=logging.WARNING)

EVAL_SET_PATH = Path(__file__).resolve().parent / "eval_set.json"


def run():
    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)
    pipeline.build_index(force_rebuild=False)

    eval_cases = json.loads(EVAL_SET_PATH.read_text())
    results = []

    for case in eval_cases:
        retrieved = pipeline.retrieve(case["query"], top_k=3)
        grounded = pipeline.filter_grounded(retrieved)

        if case["expect_match"]:
            keyword = case.get("expect_keyword")
            if keyword:
                passed = any(keyword.lower() in r["payload"].get("title", "").lower() for r in grounded)
            else:
                passed = len(grounded) > 0
        else:
            passed = len(grounded) == 0

        results.append({
            "query": case["query"],
            "category": case["category"],
            "passed": passed,
            "known_limitation": case.get("known_limitation"),
            "grounded_titles": [r["payload"].get("title") for r in grounded],
        })

    # A known-limitation failure is expected and already understood (see the case's note) —
    # counting it against the pass rate the same as an unexplained regression would make it
    # impossible to tell "this is the accepted tradeoff we already calibrated for" apart from
    # "something just broke," which defeats the point of a regression check.
    real_cases = [r for r in results if not r["known_limitation"]]
    passed_count = sum(r["passed"] for r in real_cases)
    print(f"\n{'='*80}\nRETRIEVAL EVAL: {passed_count}/{len(real_cases)} passed"
          f" ({sum(not r['passed'] for r in results if r['known_limitation'])} known limitations excluded)\n{'='*80}")

    by_category = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r)

    for category, cases in by_category.items():
        cat_passed = sum(bool(c["passed"] or c["known_limitation"]) for c in cases)
        print(f"\n[{category}] {cat_passed}/{len(cases)}")
        for c in cases:
            if c["known_limitation"] and not c["passed"]:
                status = "KNOWN"
            else:
                status = "PASS" if c["passed"] else "FAIL"
            print(f"  {status}  {c['query']!r} -> {c['grounded_titles']}")
            if status == "KNOWN":
                print(f"         ({c['known_limitation']})")

    unexpected_failures = [r for r in real_cases if not r["passed"]]
    if unexpected_failures:
        print(f"\n⚠️  {len(unexpected_failures)} unexpected failure(s) — investigate before shipping this change.")

    return results


if __name__ == "__main__":
    run()
