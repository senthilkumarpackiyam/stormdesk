"""Ticket system backed by the local SQLite database (the practice company's ServiceNow stand-in)."""

import json
import sqlite3

from stormdesk import chaos, timeutil
from stormdesk.store.db import connect, dicts

CLOSED_STATES = ("resolved", "closed")


class TicketSystemDown(Exception):
    """The ticket system can't take writes right now (timeout, outage, or the itsm_down drill)."""


def _next_number(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(CAST(SUBSTR(number, 4) AS INTEGER)) FROM incidents").fetchone()
    return f"INC{(row[0] or 10000) + 1:07d}"


def insert_incident(conn: sqlite3.Connection, *, employee_id: str | None, short_description: str, category: str,
                    service: str | None, location: str | None, priority: int, state: str = "new",
                    created_at: str | None = None, **optional) -> str:
    """Raw insert shared by the seed script and LocalITSM. `optional`: description, impact, urgency,
    kb_id, is_major, parent_number, channel, conversation_id."""
    number = _next_number(conn)
    created_at = created_at or timeutil.now_iso()
    fields = {
        "number": number, "employee_id": employee_id, "short_description": short_description,
        "category": category, "service": service, "location": location, "priority": priority, "state": state,
        "created_at": created_at, "updated_at": created_at,
        "resolved_at": created_at if state in CLOSED_STATES else None,
        **optional,
    }
    conn.execute(
        f"INSERT INTO incidents ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
        tuple(fields.values()),
    )
    return number


class LocalITSM:
    # --- reads ---

    def get_employee(self, employee_id: str) -> dict | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,)).fetchone()
        return dict(row) if row else None

    def get_devices(self, employee_id: str) -> list[dict]:
        with connect() as conn:
            return dicts(conn.execute("SELECT * FROM devices WHERE employee_id = ? ORDER BY kind", (employee_id,)))

    def get_incident(self, number: str) -> dict | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM incidents WHERE number = ?", (number,)).fetchone()
            if not row:
                return None
            incident = dict(row)
            incident["notes"] = dicts(conn.execute(
                "SELECT author, note, created_at FROM work_notes WHERE number = ? ORDER BY id", (number,)))
        return incident

    def incident_history(self, employee_id: str, limit: int = 5) -> list[dict]:
        with connect() as conn:
            return dicts(
                conn.execute(
                    "SELECT * FROM incidents WHERE employee_id = ? ORDER BY created_at DESC LIMIT ?",
                    (employee_id, limit),
                )
            )

    def list_incidents(self, open_only: bool = False, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM incidents"
        if open_only:
            query += f" WHERE state NOT IN {CLOSED_STATES}"
        with connect() as conn:
            return dicts(conn.execute(query + " ORDER BY created_at DESC LIMIT ?", (limit,)))

    def open_reports(
        self, service: str, since: str, location: str | None = None, exclude_employee: str | None = None
    ) -> list[dict]:
        """Open, non-major incidents (not requests) for one service opened since `since`, newest first."""
        query = (
            "SELECT * FROM incidents WHERE service = ? AND is_major = 0 AND ticket_type = 'incident'"
            f" AND created_at >= ? AND state NOT IN {CLOSED_STATES}"
        )
        params: list = [service, since]
        if location:
            query += " AND location = ?"
            params.append(location)
        if exclude_employee:
            query += " AND (employee_id IS NULL OR employee_id != ?)"
            params.append(exclude_employee)
        with connect() as conn:
            return dicts(conn.execute(query + " ORDER BY created_at DESC", params))

    def open_major_incident(self, service: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE service = ? AND is_major = 1"
                f" AND state NOT IN {CLOSED_STATES} ORDER BY created_at DESC LIMIT 1",
                (service,),
            ).fetchone()
        return dict(row) if row else None

    def children_of(self, number: str, open_only: bool = True) -> list[dict]:
        query = "SELECT * FROM incidents WHERE parent_number = ?"
        if open_only:
            query += f" AND state NOT IN {CLOSED_STATES}"
        with connect() as conn:
            return dicts(conn.execute(query + " ORDER BY created_at", (number,)))

    def list_employees(self, department: str | None = None) -> list[dict]:
        query, params = "SELECT * FROM employees", ()
        if department:
            query, params = query + " WHERE department = ?", (department,)
        with connect() as conn:
            return dicts(conn.execute(query + " ORDER BY employee_id", params))

    def kb_articles(self) -> list[dict]:
        with connect() as conn:
            rows = dicts(conn.execute("SELECT * FROM kb_articles ORDER BY kb_id"))
        for row in rows:
            row["steps"] = json.loads(row["steps"])
        return rows

    # --- writes: each one can fail like a real remote ticket system would ---

    def _check_up(self) -> None:
        if chaos.is_on("itsm_down"):
            raise TicketSystemDown("ticket system unavailable (itsm_down drill)")

    def create_incident(self, **fields) -> str:
        self._check_up()
        with connect() as conn:
            return insert_incident(conn, **fields)

    def add_note(self, number: str, author: str, note: str) -> None:
        self._check_up()
        with connect() as conn:
            conn.execute(
                "INSERT INTO work_notes (number, author, note, created_at) VALUES (?, ?, ?, ?)",
                (number, author, note, timeutil.now_iso()),
            )
            conn.execute("UPDATE incidents SET updated_at = ? WHERE number = ?", (timeutil.now_iso(), number))

    def set_state(self, number: str, state: str) -> None:
        self._check_up()
        now = timeutil.now_iso()
        with connect() as conn:
            conn.execute(
                "UPDATE incidents SET state = ?, updated_at = ?, resolved_at = ? WHERE number = ?",
                (state, now, now if state in CLOSED_STATES else None, number),
            )

    def link_to_parent(self, numbers: list[str], parent_number: str) -> None:
        self._check_up()
        with connect() as conn:
            conn.executemany(
                "UPDATE incidents SET parent_number = ?, updated_at = ? WHERE number = ?",
                [(parent_number, timeutil.now_iso(), n) for n in numbers],
            )
