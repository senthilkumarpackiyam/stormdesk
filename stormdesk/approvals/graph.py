"""The approval process as a LangGraph state machine.

    assess_risk -> human_review (PAUSES until a technician decides) -> apply_change   -> end
                                                                    -> close_unapproved -> end

`interrupt()` in human_review stops the graph and saves its state to SQLite (the checkpointer).
Nothing runs while it waits; the server can even restart. When a technician decides in the console,
`Command(resume=decision)` picks the same approval up exactly where it stopped."""

import logging
import sqlite3
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from stormdesk import timeutil
from stormdesk.approvals import actions, risk, store
from stormdesk.config import settings

log = logging.getLogger(__name__)


class ApprovalState(TypedDict, total=False):
    approval_id: str
    risk_level: str
    risk_notes: list[str]
    decision: dict
    outcome: str


def assess_risk(state: ApprovalState) -> dict:
    approval = store.get(state["approval_id"])
    level, notes = risk.assess(approval)
    store.update(state["approval_id"], risk_level=level, risk_notes=notes)
    return {"risk_level": level, "risk_notes": notes}


def human_review(state: ApprovalState) -> dict:
    # Everything before interrupt() re-runs on resume, so this node must stay free of side effects.
    decision = interrupt({"approval_id": state["approval_id"], "risk_level": state["risk_level"],
                          "risk_notes": state["risk_notes"]})
    return {"decision": decision}


def after_review(state: ApprovalState) -> str:
    return "apply_change" if state["decision"].get("approve") else "close_unapproved"


def apply_change(state: ApprovalState) -> dict:
    approval = store.get(state["approval_id"])
    try:
        result = actions.execute(approval, state["decision"])
    except Exception as exc:
        log.warning("approval %s approved but failed: %s", approval["approval_id"], exc)
        store.update(approval["approval_id"], status="failed", result={"error": str(exc)},
                     completed_at=timeutil.now_iso())
        actions.note_failure(approval, str(exc))
        return {"outcome": "failed"}
    store.update(approval["approval_id"], status="executed", result=result, completed_at=timeutil.now_iso())
    return {"outcome": "executed"}


def close_unapproved(state: ApprovalState) -> dict:
    status = "expired" if state["decision"].get("expired") else "rejected"
    store.update(state["approval_id"], status=status, completed_at=timeutil.now_iso())
    actions.notify_unapproved(store.get(state["approval_id"]), status)
    return {"outcome": status}


def _build() -> StateGraph:
    builder = StateGraph(ApprovalState)
    builder.add_node("assess_risk", assess_risk)
    builder.add_node("human_review", human_review)
    builder.add_node("apply_change", apply_change)
    builder.add_node("close_unapproved", close_unapproved)
    builder.add_edge(START, "assess_risk")
    builder.add_edge("assess_risk", "human_review")
    builder.add_conditional_edges("human_review", after_review, ["apply_change", "close_unapproved"])
    builder.add_edge("apply_change", END)
    builder.add_edge("close_unapproved", END)
    return builder


_compiled: dict[str, tuple] = {}


def graph():
    path = str(settings.checkpoint_path)
    if path not in _compiled:
        settings.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        _compiled[path] = (conn, _build().compile(checkpointer=SqliteSaver(conn)))
    return _compiled[path][1]


def forget_compiled() -> None:
    """Drop the in-memory graph, as a server restart would. Saved checkpoints stay on disk."""
    for conn, _ in _compiled.values():
        conn.close()
    _compiled.clear()


def clear_checkpoints() -> None:
    forget_compiled()
    if not settings.checkpoint_path.exists():
        return
    conn = sqlite3.connect(settings.checkpoint_path)
    try:
        for table in ("checkpoints", "writes"):
            try:
                conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass  # tables not created yet
        conn.commit()
    finally:
        conn.close()


def config(approval_id: str) -> dict:
    return {"configurable": {"thread_id": approval_id}}


def start(approval_id: str) -> None:
    graph().invoke({"approval_id": approval_id}, config(approval_id))


def is_waiting(approval_id: str) -> bool:
    return "human_review" in graph().get_state(config(approval_id)).next


def resume(approval_id: str, decision: dict) -> None:
    graph().invoke(Command(resume=decision), config(approval_id))
