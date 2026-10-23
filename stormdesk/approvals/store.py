"""The approvals table: what the console lists and what check_approval_status reads.

The LangGraph checkpoint holds where each approval is in its process; this table holds the facts
about it, so they can be queried without replaying the graph."""

import json

from stormdesk import timeutil
from stormdesk.store.db import connect, dicts

JSON_FIELDS = ("details", "risk_notes", "result")


def _decode(row) -> dict:
    approval = dict(row)
    for field in JSON_FIELDS:
        if approval.get(field):
            approval[field] = json.loads(approval[field])
    return approval


def create(kind: str, reason: str, *, employee_id: str | None = None, service: str | None = None,
           conversation_id: str | None = None, incident_number: str | None = None,
           details: dict | None = None) -> str:
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        approval_id = f"APR-{count + 1:04d}"
        conn.execute(
            "INSERT INTO approvals (approval_id, kind, status, employee_id, service, conversation_id,"
            " incident_number, reason, details, created_at) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
            (approval_id, kind, employee_id, service, conversation_id, incident_number, reason,
             json.dumps(details or {}), timeutil.now_iso()),
        )
    return approval_id


def get(approval_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    return _decode(row) if row else None


def update(approval_id: str, **fields) -> None:
    for field in JSON_FIELDS:
        if field in fields:
            fields[field] = json.dumps(fields[field])
    assignments = ", ".join(f"{name} = ?" for name in fields)
    with connect() as conn:
        conn.execute(f"UPDATE approvals SET {assignments} WHERE approval_id = ?", (*fields.values(), approval_id))


def list_approvals(status: str | None = None, limit: int = 50) -> list[dict]:
    query, params = "SELECT * FROM approvals", ()
    if status:
        query, params = query + " WHERE status = ?", (status,)
    with connect() as conn:
        rows = conn.execute(query + " ORDER BY created_at DESC LIMIT ?", (*params, limit)).fetchall()
    return [_decode(r) for r in rows]


def pending_for(kind: str, *, employee_id: str | None = None, service: str | None = None) -> dict | None:
    query, params = "SELECT * FROM approvals WHERE kind = ? AND status = 'pending'", [kind]
    if employee_id:
        query += " AND employee_id = ?"
        params.append(employee_id)
    if service:
        query += " AND service = ?"
        params.append(service)
    with connect() as conn:
        row = conn.execute(query + " ORDER BY created_at DESC LIMIT 1", params).fetchone()
    return _decode(row) if row else None


def recent_identity_changes(employee_id: str, hours: int = 24) -> list[dict]:
    with connect() as conn:
        return dicts(conn.execute(
            "SELECT * FROM identity_changes WHERE employee_id = ? AND created_at >= ? ORDER BY created_at DESC",
            (employee_id, timeutil.ago_iso(minutes=hours * 60)),
        ))
