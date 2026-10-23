"""Post-call reviews from the command line.

    uv run python -m stormdesk.review run <conversation_id> [...]    # review specific calls, print scorecards
    uv run python -m stormdesk.review latest [-n 5]                  # review the agent's latest calls
    uv run python -m stormdesk.review compare -n 5 --models A B C    # same calls, several Nebius models

Reviews are stored in the database (and shown in the console's Reviews tab). Each run also appears in
LangSmith when LANGSMITH_API_KEY is set.
"""

import argparse
import asyncio
import sys
import time

from stormdesk.review import runner
from stormdesk.review.config import review_settings
from stormdesk.store.db import init_db
from stormdesk.voice.state import load_state

ICON = {"pass": "✅", "attention": "🟡", "fail": "❌", None: "⚪"}


def show(review: dict) -> None:
    report = review.get("report") or {}
    card = report.get("scorecard") or {}
    print(f"\n{ICON.get(review.get('verdict'))} {review['conversation_id']}  [{review['status']}]  "
          f"verdict: {review.get('verdict')}  · model {review.get('model')}")
    if review.get("error"):
        print(f"   note: {review['error']}")
    print(f"   {card.get('headline', '')}")
    scores = [f"{k.split('_')[0]} {card.get(k)}" for k in ("resolution_score", "process_score", "experience_score")]
    print(f"   scores: {' · '.join(scores)} · outcome: {(report.get('resolution') or {}).get('outcome')}"
          f" · desks: {' -> '.join(report.get('desks') or [])}")
    for check in report.get("rule_checks", []):
        if check["result"] != "n/a":
            print(f"   rule [{check['result']:<4}] {check['label']}" + (f" ({check['detail']})" if check["detail"] else ""))
    for flag in card.get("flags") or []:
        print(f"   flag: {flag}")
    for item in ((report.get("follow_up") or {}).get("items") or []):
        print(f"   follow-up ({item['owner']}, {item['urgency']}): {item['action']}")
    for tip in card.get("coaching") or []:
        print(f"   coaching: {tip}")


def _latest_ids(n: int) -> list[str]:
    agent_id = load_state().get("agent_id")
    if not agent_id:
        sys.exit("No agent deployed yet (data/elevenlabs.json is missing).")
    recent = runner._elevenlabs().list_conversations(agent_id, n)
    return [c["conversation_id"] for c in recent if c.get("status") in runner.FINISHED]


async def _run(ids: list[str], model: str | None) -> list[dict]:
    return [await runner.review(cid, source="manual", model=model) for cid in ids]


async def _compare(ids: list[str], models: list[str]) -> dict:
    # One event loop for everything: the model client keeps connections that belong to the loop that opened them.
    table = {}
    for model in models:
        started = time.time()
        results = await _run(ids, model)
        table[model] = (results, (time.time() - started) / max(len(ids), 1))
    return table


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("ids", nargs="+")
    run.add_argument("--model")
    latest = sub.add_parser("latest")
    latest.add_argument("-n", type=int, default=5)
    latest.add_argument("--model")
    compare = sub.add_parser("compare")
    compare.add_argument("-n", type=int, default=5)
    compare.add_argument("--models", nargs="+", required=True)
    args = parser.parse_args()
    init_db()

    if args.command in ("run", "latest"):
        ids = args.ids if args.command == "run" else _latest_ids(args.n)
        for review in asyncio.run(_run(ids, args.model)):
            show(review)
        return

    ids = _latest_ids(args.n)
    table = asyncio.run(_compare(ids, args.models))
    for results, _ in table.values():
        for review in results:
            show(review)
    print("\nMODEL COMPARISON (same calls)")
    for model, (results, elapsed) in table.items():
        verdicts = " ".join(f"{(r.get('report') or {}).get('resolution', {}).get('outcome', 'error')}/{r.get('verdict')}"
                            for r in results)
        partial = sum(r["status"] != "done" for r in results)
        print(f"  {model:<40} {elapsed:5.1f} s/call · incomplete {partial} · {verdicts}")
    print(f"\n(the stored review is the last model's; default model is {review_settings.stormdesk_review_model})")


if __name__ == "__main__":
    main()
