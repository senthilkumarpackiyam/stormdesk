"""The review as a LangGraph graph.

    gather ──┬── resolution ──┐
             ├── process ─────┼── follow_up ── judge
             └── experience ──┘

The three reviewers run in parallel. If one fails (Nebius down, a malformed answer), its error is recorded
and the others carry on; if the judge fails, a scorecard is still built from the rule checks. A review is
never lost completely."""

import json
import logging
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from stormdesk.review import casefile, reviewers
from stormdesk.review.reviewers import (ExperienceReview, FollowUpPlan, ProcessReview, ResolutionReview,
                                        Scorecard)

log = logging.getLogger(__name__)


class ReviewState(TypedDict, total=False):
    conversation: dict          # ElevenLabs' record of the call
    model: str | None
    case_text: str
    facts: dict
    resolution: dict
    process: dict
    experience: dict
    follow_up: dict
    scorecard: dict
    errors: Annotated[list[str], operator.add]  # parallel reviewers may each add one


def gather(state: ReviewState) -> dict:
    case = casefile.build(state["conversation"])
    return {"case_text": case.text(), "facts": case.facts(), "errors": []}


async def _review(state: ReviewState, key: str, schema, rubric: str, extra: str = "") -> dict:
    try:
        answer = await reviewers.ask(schema, rubric, state["case_text"] + extra, state.get("model"))
        return {key: answer.model_dump()}
    except Exception as exc:  # keep the other reviewers' work
        log.warning("reviewer %s failed: %s", key, exc)
        return {key: {"error": f"{type(exc).__name__}: {exc}"[:300]}, "errors": [f"{key} reviewer failed"]}


async def resolution(state: ReviewState) -> dict:
    return await _review(state, "resolution", ResolutionReview, reviewers.RESOLUTION)


async def process(state: ReviewState) -> dict:
    return await _review(state, "process", ProcessReview, reviewers.PROCESS)


async def experience(state: ReviewState) -> dict:
    return await _review(state, "experience", ExperienceReview, reviewers.EXPERIENCE)


def _findings(state: ReviewState, *keys: str) -> str:
    return "\n\nREVIEWERS' FINDINGS\n" + "\n".join(f"{k.upper()}: {json.dumps(state.get(k, {}))}" for k in keys)


async def follow_up(state: ReviewState) -> dict:
    return await _review(state, "follow_up", FollowUpPlan, reviewers.FOLLOW_UP,
                         _findings(state, "resolution", "process"))


def _rules_scorecard(state: ReviewState, reason: str) -> dict:
    """When the judge can't run: a cautious scorecard from the rule checks alone."""
    failed = [c["label"] for c in state["facts"]["rule_checks"] if c["result"] == "fail"]
    return {"verdict": "fail" if failed else "attention",
            "headline": f"Automatic review incomplete ({reason}). Rule checks: "
                        + (f"failed: {'; '.join(failed)}." if failed else "no rule failures."),
            "resolution_score": None, "process_score": None, "experience_score": None,
            "flags": ["Review needs a person: the AI judge did not complete."], "coaching": []}


def apply_guardrails(card: dict, facts: dict, process_review: dict) -> dict:
    """A hard rule failure can't be graded 'pass', whatever the model says."""
    failed = [c["label"] for c in facts["rule_checks"] if c["result"] == "fail"]
    violations = process_review.get("violations") or []
    if card["verdict"] == "pass" and (failed or violations):
        card["verdict"] = "attention"
        card["flags"] = list(card.get("flags") or []) + ["Verdict lowered: " + "; ".join(failed + violations)]
    return card


async def judge(state: ReviewState) -> dict:
    if state.get("errors") and all("error" in state.get(k, {}) for k in ("resolution", "process", "experience")):
        return {"scorecard": _rules_scorecard(state, "all reviewers failed")}
    result = await _review(state, "scorecard", Scorecard, reviewers.JUDGE,
                           _findings(state, "resolution", "process", "experience", "follow_up"))
    card = result["scorecard"]
    if "error" in card:
        return {"scorecard": _rules_scorecard(state, "judge failed"), "errors": result.get("errors", [])}
    return {"scorecard": apply_guardrails(card, state["facts"], state.get("process", {}))}


def build() -> StateGraph:
    graph = StateGraph(ReviewState)
    for name, node in [("gather", gather), ("resolution", resolution), ("process", process),
                       ("experience", experience), ("follow_up", follow_up), ("judge", judge)]:
        graph.add_node(name, node)
    graph.add_edge(START, "gather")
    for reviewer in ("resolution", "process", "experience"):
        graph.add_edge("gather", reviewer)
        graph.add_edge(reviewer, "follow_up")
    graph.add_edge("follow_up", "judge")
    graph.add_edge("judge", END)
    return graph


review_graph = build().compile()
