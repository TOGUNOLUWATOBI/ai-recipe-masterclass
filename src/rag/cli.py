"""Interactive CLI for the recipe RAG pipeline.

Usage:
    python -m rag.cli                  # interactive loop
    python -m rag.cli "norwegian ribbe"  # single query
    python -m rag.cli --rebuild        # force re-embed/re-index before querying

Run from inside src/ so the `rag` package resolves, e.g.:
    cd "AI Recipe Masterclass/src" && python -m rag.cli
"""

import argparse
import logging

from rag.config import RecipeRAGConfig
from rag.pipeline import RecipeRAGPipeline

logging.basicConfig(level=logging.WARNING)  # keep noisy library logs quiet in interactive mode


def main():
    parser = argparse.ArgumentParser(description="Query the recipe RAG pipeline")
    parser.add_argument("question", nargs="?", help="Ask a single question and exit")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of the vector index")
    parser.add_argument("--top-k", type=int, default=None, help="Number of reference recipes to retrieve")
    parser.add_argument("--show-context", action="store_true", help="Print retrieved reference recipe(s) before the answer")
    args = parser.parse_args()

    config = RecipeRAGConfig()
    pipeline = RecipeRAGPipeline(config)

    print("Building/loading recipe index...")
    pipeline.build_index(force_rebuild=args.rebuild)
    pipeline.initialize_generator()
    print(f"Ready — model '{config.LLM_MODEL}' at {config.OLLAMA_BASE_URL}\n")

    def ask(question: str):
        for event in pipeline.run_query_stream(question, top_k=args.top_k):
            if event["type"] == "meta" and args.show_context:
                titles = [r["payload"].get("title") for r in event["grounded"]]
                summary = titles if titles else "(none - using model's own knowledge)"
                print(f"--- grounded on: {summary} ---")
            elif event["type"] == "chunk":
                print(event["text"], end="", flush=True)
            elif event["type"] == "error":
                print(f"[Generation failed: {event['error']}]")
            elif event["type"] == "done":
                print(f"\n\n[{event['elapsed']:.1f}s]")

    if args.question:
        ask(args.question)
        return

    print("Type a dish or ingredient request ('exit' to quit).")
    while True:
        try:
            question = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break
        ask(question)


if __name__ == "__main__":
    main()
