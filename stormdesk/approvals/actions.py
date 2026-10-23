"""What actually happens once a technician says yes (or no).

The identity system is simulated: approved changes are recorded in identity_changes and the
employee is told through a fixed-template text or email."""

import secrets
from collections import Counter

from stormdesk import chaos, messaging, timeutil
from stormdesk.itsm import itsm
from stormdesk.itsm.local import TicketSystemDown
from stormdesk.policy import SENSITIVE_ACTIONS
from stormdesk.sources.vendor_status import SERVICES
from stormdesk.store.db import connect


class IdentitySystemDown(Exception):
    pass


def _label(approval: dict) -> str:
    return SENSITIVE_ACTIONS.get(approval["kind"], approval["kind"]).lower()


def _note(number: str | None, text: str) -> None:
    if not number:
        return
    try:
        itsm.add_note(number, "StormDesk approvals", text)
    except TicketSystemDown:
        pass  # the approval record and audit log still hold it


def _tell(employee_id: str | None, channel: str, body: str) -> None:
    employee = itsm.get_employee(employee_id) if employee_id else None
    if not employee:
        return
    try:
        messaging.send(employee, channel, body)
    except messaging.MessagingDown:
        pass


def execute(approval: dict, decision: dict) -> dict:
    if approval["kind"] == "major_incident":
        return _declare_major_incident(approval, decision)
    if chaos.is_on("identity_down"):
        raise IdentitySystemDown("identity system unavailable (identity_down drill)")

    with connect() as conn:
        conn.execute(
            "INSERT INTO identity_changes (employee_id, action, approval_id, performed_by, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (approval["employee_id"], approval["kind"], approval["approval_id"], decision["technician_id"],
             timeutil.now_iso()),
        )
    number = approval["incident_number"]
    resource = approval["details"].get("resource")
    if approval["kind"] == "mfa_reset":
        _tell(approval["employee_id"], "email",
              "Acme IT: your MFA reset was approved. On your new phone, open Okta Verify and use this one-time "
              f"setup link: https://enroll.acme.example/{secrets.token_urlsafe(8)} (valid 24 hours). "
              "Didn't ask for this? Call the service desk straight away.")
    elif approval["kind"] == "account_unlock":
        _tell(approval["employee_id"], "sms",
              "Acme IT: your account is unlocked. Sign in on one device first. Didn't ask for this? "
              "Call the service desk.")
    else:
        _tell(approval["employee_id"], "email",
              f"Acme IT: your access to {resource} was approved. It can take 15 minutes to appear.")
    _note(number, f"{SENSITIVE_ACTIONS[approval['kind']]} approved by {decision['technician_name']} "
                  f"({decision['technician_id']}) under {approval['approval_id']}, and applied.")
    if number:
        try:
            itsm.set_state(number, "resolved")
        except TicketSystemDown:
            pass
    return {"applied": approval["kind"], "resource": resource}


def _declare_major_incident(approval: dict, decision: dict) -> dict:
    service = SERVICES[approval["service"]]
    reports = itsm.open_reports(service.key, approval["details"]["since"])
    locations = Counter(r["location"] for r in reports if r["location"])
    where = ", ".join(loc for loc, _ in locations.most_common()) or "several sites"
    number = itsm.create_incident(
        employee_id=None, short_description=f"{service.name} outage: {len(reports)} reports from {where}",
        description="\n".join(approval["details"].get("evidence", [])), category="major incident",
        service=service.key, location=next(iter(locations)) if len(locations) == 1 else "Multiple",
        priority=1, state="in_progress", is_major=1, channel="system",
    )
    itsm.link_to_parent([r["number"] for r in reports], number)
    itsm.add_note(number, "StormDesk approvals",
                  f"Declared by {decision['technician_name']} ({decision['technician_id']}) "
                  f"under {approval['approval_id']}. {len(reports)} reports linked.")
    notified = sorted({r["employee_id"] for r in reports if r["employee_id"]})
    for employee_id in notified:
        _tell(employee_id, "sms",
              f"Acme IT: we know about the {service.name} problem and are working on it (major incident "
              f"{number}). No need to call again: we'll text you when it's fixed.")
    return {"major_incident": number, "linked": [r["number"] for r in reports], "notified": len(notified)}


def notify_unapproved(approval: dict, status: str) -> None:
    if approval["kind"] == "major_incident":
        return
    number = approval["incident_number"] or approval["details"].get("ticket_reference") or ""
    if status == "expired":
        body = (f"Acme IT: your request ({_label(approval)}) wasn't reviewed in time. A technician will contact "
                f"you about ticket {number}.")
        _note(approval["incident_number"], f"{approval['approval_id']} expired without a decision.")
    else:
        body = f"Acme IT: your request ({_label(approval)}) was not approved. A technician will follow up on {number}."
        _note(approval["incident_number"], f"{approval['approval_id']} rejected by {approval['decided_by']}: "
                                           f"{approval['decision_note'] or 'no note'}.")
    _tell(approval["employee_id"], "sms", body)


def note_failure(approval: dict, error: str) -> None:
    _note(approval["incident_number"], f"{approval['approval_id']} was approved but could not be applied: {error}. "
                                       "Needs a technician to finish by hand.")
