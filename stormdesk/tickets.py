"""Filing tickets: priority from the impact x urgency matrix, duplicate checks, one retry, and the
outbox when the ticket system is down."""

import asyncio
import re

from stormdesk import outbox, timeutil
from stormdesk.itsm import itsm
from stormdesk.itsm.local import CLOSED_STATES, TicketSystemDown

RETRY_DELAY_S = 0.2
DUPLICATE_WINDOW_DAYS = 7

IMPACTS = ("just_me", "team", "site", "company")
URGENCIES = ("can_work", "slowed", "blocked")
# Standard ITIL-style matrix: rows are impact, columns are urgency (can_work, slowed, blocked).
_PRIORITY = {"just_me": (4, 3, 3), "team": (3, 3, 2), "site": (3, 2, 1), "company": (2, 1, 1)}

CATEGORY_BY_SERVICE = {
    "vpn": "network", "wifi": "network", "gmail": "email", "sso": "account", "printing": "hardware",
    "slack": "collaboration", "zoom": "collaboration", "google_meet": "collaboration",
    "google_drive": "collaboration", "google_calendar": "collaboration", "google_docs": "collaboration",
    "github": "application", "jira": "application", "confluence": "application", "figma": "application",
    "notion": "application", "chatgpt": "application",
}


def priority_for(impact: str, urgency: str, vip: bool) -> int:
    priority = _PRIORITY[impact][URGENCIES.index(urgency)]
    # VIPs move up one level, but a single person alone never makes a P1.
    return max(2, priority - 1) if vip and priority > 2 else priority


def normalize_number(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    return f"INC{int(digits):07d}" if digits else None


def spoken(number: str) -> str:
    """'INC0010013' -> 'I N C 1 0 0 1 3': how to say it clearly on a phone line."""
    return "I N C " + " ".join(str(int(number[3:])))


def find_duplicate(employee_id: str, service: str | None) -> dict | None:
    if not service:
        return None
    since = timeutil.ago_iso(days=DUPLICATE_WINDOW_DAYS)
    for ticket in itsm.incident_history(employee_id, limit=20):
        if (ticket["service"] == service and ticket["ticket_type"] == "incident"
                and ticket["state"] not in CLOSED_STATES and ticket["created_at"] >= since):
            return ticket
    return None


async def _with_retry(write):
    try:
        return write()
    except TicketSystemDown:
        await asyncio.sleep(RETRY_DELAY_S)
        return write()


async def file(payload: dict) -> dict:
    """{"number": ..., "queued": False}, or {"reference": "PEND-0001", "queued": True} if the system is down."""
    try:
        return {"number": await _with_retry(lambda: itsm.create_incident(**payload)), "queued": False}
    except TicketSystemDown as exc:
        return {"reference": outbox.enqueue("incident", payload, str(exc)), "queued": True}


async def note(number: str, author: str, text: str, resolve: bool = False) -> dict:
    def write():
        itsm.add_note(number, author, text)
        if resolve:
            itsm.set_state(number, "resolved")

    try:
        await _with_retry(write)
        return {"number": number, "queued": False}
    except TicketSystemDown as exc:
        payload = {"number": number, "author": author, "note": text, "resolve": resolve}
        return {"number": number, "reference": outbox.enqueue("note", payload, str(exc)), "queued": True}
