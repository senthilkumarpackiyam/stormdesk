import json

from stormdesk import timeutil
from stormdesk.store.db import connect, dicts


def _decode(row) -> dict:
    review = dict(row)
    review["report"] = json.loads(review["report"] or "{}")
    return review


def get(conversation_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE conversation_id = ?", (conversation_id,)).fetchone()
    return _decode(row) if row else None


def list_reviews(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM reviews ORDER BY COALESCE(call_started_at, created_at) DESC LIMIT ?",
                            (limit,)).fetchall()
    return [_decode(r) for r in rows]


def start(conversation_id: str, source: str, model: str) -> None:
    now = timeutil.now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT INTO reviews (conversation_id, status, source, model, attempts, created_at)"
            " VALUES (?, 'running', ?, ?, 1, ?)"
            " ON CONFLICT(conversation_id) DO UPDATE SET status = 'running', source = excluded.source,"
            " model = excluded.model, attempts = reviews.attempts + 1, error = NULL",
            (conversation_id, source, model, now),
        )


def finish(conversation_id: str, state: dict) -> dict:
    card = state.get("scorecard") or {}
    facts = state.get("facts") or {}
    report = {k: state.get(k) for k in ("scorecard", "resolution", "process", "experience", "follow_up")}
    report["rule_checks"] = facts.get("rule_checks", [])
    report["metrics"] = facts.get("metrics", {})
    report["desks"] = facts.get("desks", [])
    report["elevenlabs_opinion"] = facts.get("elevenlabs_opinion", {})
    report["errors"] = state.get("errors") or []
    employee = facts.get("employee") or {}
    with connect() as conn:
        conn.execute(
            "UPDATE reviews SET status = ?, employee_id = ?, verdict = ?, headline = ?, report = ?,"
            " call_started_at = ?, completed_at = ?, error = ? WHERE conversation_id = ?",
            ("partial" if report["errors"] else "done", employee.get("employee_id"), card.get("verdict"),
             card.get("headline"), json.dumps(report, default=str), facts.get("started_at"), timeutil.now_iso(),
             "; ".join(report["errors"]) or None, conversation_id),
        )
    return get(conversation_id)


def fail(conversation_id: str, error: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE reviews SET status = 'failed', error = ?, completed_at = ? WHERE conversation_id = ?",
                     (error[:500], timeutil.now_iso(), conversation_id))


def set_follow_up_ticket(conversation_id: str, index: int, number: str) -> None:
    review = get(conversation_id)
    items = ((review or {}).get("report", {}).get("follow_up") or {}).get("items") or []
    items[index]["ticket"] = number
    with connect() as conn:
        conn.execute("UPDATE reviews SET report = ? WHERE conversation_id = ?",
                     (json.dumps(review["report"], default=str), conversation_id))


def counts() -> dict:
    with connect() as conn:
        rows = dicts(conn.execute("SELECT verdict, COUNT(*) AS n FROM reviews WHERE verdict IS NOT NULL GROUP BY verdict"))
    return {row["verdict"]: row["n"] for row in rows}
