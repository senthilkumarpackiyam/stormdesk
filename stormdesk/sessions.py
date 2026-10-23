"""What StormDesk remembers about the current call, keyed by the ElevenLabs conversation id.

Rows are kept after the call ends, which is also how it remembers earlier calls from the same person."""

from stormdesk import timeutil
from stormdesk.store.db import connect, dicts


def get(conversation_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE conversation_id = ?", (conversation_id,)).fetchone()
    return dict(row) if row else None


def ensure(conversation_id: str) -> dict:
    now = timeutil.now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (conversation_id, created_at, updated_at) VALUES (?, ?, ?)",
            (conversation_id, now, now),
        )
    return get(conversation_id)


def _update(conversation_id: str, assignments: str, params: tuple = ()) -> None:
    ensure(conversation_id)
    with connect() as conn:
        conn.execute(
            f"UPDATE sessions SET {assignments}, updated_at = ? WHERE conversation_id = ?",
            (*params, timeutil.now_iso(), conversation_id),
        )


def identify(conversation_id: str, employee_id: str) -> None:
    _update(conversation_id, "employee_id = ?, identified_at = ?", (employee_id, timeutil.now_iso()))


def note_lookup_failure(conversation_id: str) -> int:
    _update(conversation_id, "lookup_failures = lookup_failures + 1")
    return get(conversation_id)["lookup_failures"]


def note_code_failure(conversation_id: str) -> int:
    _update(conversation_id, "code_failures = code_failures + 1")
    return get(conversation_id)["code_failures"]


def mark_verified(conversation_id: str) -> None:
    _update(conversation_id, "verified_at = ?", (timeutil.now_iso(),))


def lock(conversation_id: str) -> None:
    _update(conversation_id, "locked = 1")


def set_last_ticket(conversation_id: str, number: str) -> None:
    _update(conversation_id, "last_ticket = ?", (number,))


def recent(limit: int = 30) -> list[dict]:
    with connect() as conn:
        return dicts(conn.execute(
            "SELECT s.*, e.full_name FROM sessions s LEFT JOIN employees e ON e.employee_id = s.employee_id"
            " ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        ))


def previous_calls(employee_id: str, exclude: str | None, days: int = 7) -> list[dict]:
    with connect() as conn:
        return dicts(conn.execute(
            "SELECT * FROM sessions WHERE employee_id = ? AND conversation_id != ? AND created_at >= ?"
            " ORDER BY created_at DESC",
            (employee_id, exclude or "", timeutil.ago_iso(days=days)),
        ))
