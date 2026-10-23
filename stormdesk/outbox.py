"""Ticket writes waiting for the ticket system to come back.

When ServiceNow (here: the itsm_down drill) refuses a write, the caller still gets a reference
straight away, like PEND-0003. Housekeeping retries every 30 seconds; once delivered, the employee
gets a text with their real ticket number."""

import json
import logging

from stormdesk import messaging, timeutil
from stormdesk.itsm import itsm
from stormdesk.itsm.local import TicketSystemDown
from stormdesk.store.db import connect, dicts

log = logging.getLogger(__name__)


def enqueue(kind: str, payload: dict, error: str) -> str:
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        ref = f"PEND-{count + 1:04d}"
        conn.execute(
            "INSERT INTO outbox (ref, kind, payload, attempts, last_error, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            (ref, kind, json.dumps(payload), error, timeutil.now_iso()),
        )
    log.warning("ticket system down; queued %s as %s", kind, ref)
    return ref


def entries(status: str | None = None) -> list[dict]:
    query, params = "SELECT * FROM outbox", ()
    if status:
        query, params = query + " WHERE status = ?", (status,)
    with connect() as conn:
        rows = dicts(conn.execute(query + " ORDER BY created_at", params))
    for row in rows:
        row["payload"] = json.loads(row["payload"])
    return rows


def _deliver(entry: dict) -> str:
    payload = entry["payload"]
    if entry["kind"] == "incident":
        if payload.get("service") and not payload.get("parent_number"):
            # A major incident may have been declared while this was waiting.
            major = itsm.open_major_incident(payload["service"])
            if major:
                payload["parent_number"] = major["number"]
        number = itsm.create_incident(**payload)
        try:
            itsm.add_note(number, "StormDesk", f"Logged late from {entry['ref']}: the ticket system was unavailable.")
        except TicketSystemDown:
            pass  # the ticket exists; never re-deliver it just because the note failed

        employee = itsm.get_employee(payload["employee_id"]) if payload.get("employee_id") else None
        if employee:
            try:
                messaging.send(employee, "sms", f"Acme IT: your request {entry['ref']} is now ticket {number}.")
            except messaging.MessagingDown:
                pass
        return number
    itsm.add_note(payload["number"], payload["author"], payload["note"])
    if payload.get("resolve"):
        itsm.set_state(payload["number"], "resolved")
    return payload["number"]


def flush() -> list[dict]:
    """Deliver what we can, oldest first. Stops at the first failure: the system is still down."""
    delivered = []
    for entry in entries("pending"):
        try:
            result = _deliver(entry)
        except TicketSystemDown as exc:
            with connect() as conn:
                conn.execute("UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE ref = ?",
                             (str(exc), entry["ref"]))
            break
        with connect() as conn:
            conn.execute("UPDATE outbox SET status = 'delivered', result = ?, delivered_at = ? WHERE ref = ?",
                         (result, timeutil.now_iso(), entry["ref"]))
        delivered.append({"ref": entry["ref"], "kind": entry["kind"], "result": result,
                          "service": entry["payload"].get("service")})
    return delivered
