"""Texts and emails to employees.

Nothing really leaves the machine: messages land in the `messages` table, which the console shows
as each employee's phone and inbox. Messages only ever go to the contact details on file, and
their wording comes from fixed templates in code, never from the AI."""

from stormdesk import chaos, timeutil
from stormdesk.store.db import connect, dicts


class MessagingDown(Exception):
    pass


def send(employee: dict, channel: str, body: str) -> int:
    if channel == "sms" and chaos.is_on("sms_down"):
        raise MessagingDown("SMS gateway unavailable")
    to = employee["mobile"] if channel == "sms" else employee["email"]
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (employee_id, channel, to_address, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (employee["employee_id"], channel, to, body, timeutil.now_iso()),
        )
        return cur.lastrowid


def inbox(employee_id: str | None = None, limit: int = 50) -> list[dict]:
    query, params = "SELECT * FROM messages", []
    if employee_id:
        query += " WHERE employee_id = ?"
        params.append(employee_id)
    with connect() as conn:
        return dicts(conn.execute(query + " ORDER BY id DESC LIMIT ?", (*params, limit)))
