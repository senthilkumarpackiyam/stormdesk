"""Risk signals shown to the technician next to each request.

Plain rules, no AI: a technician must be able to see exactly why a request was flagged."""

from stormdesk import sessions
from stormdesk.approvals import store
from stormdesk.itsm import itsm


def assess(approval: dict) -> tuple[str, list[str]]:
    if approval["kind"] == "major_incident":
        return "n/a", approval["details"].get("evidence", [])

    notes, score = [], 0
    session = sessions.get(approval["conversation_id"]) if approval.get("conversation_id") else None
    if session and session["code_failures"]:
        notes.append(f"Caller needed {session['code_failures'] + 1} tries to enter the verification code.")
        score += 1
    if session and session["lookup_failures"]:
        notes.append("Caller gave a wrong employee ID or name earlier in the call.")
        score += 1
    employee = itsm.get_employee(approval["employee_id"])
    if employee and employee["vip"]:
        notes.append("VIP account: executives are frequent impersonation targets.")
        score += 1
    recent = store.recent_identity_changes(approval["employee_id"])
    if recent:
        notes.append(f"Another account change in the last 24 hours ({recent[0]['action']}).")
        score += 2
    if approval["kind"] == "mfa_reset":
        notes.append("MFA resets are the usual goal of help-desk impersonation. If anything feels off, "
                     "call back on the number on file before approving.")

    level = "high" if score >= 3 else "medium" if score >= 1 else "low"
    if score == 0:
        notes.insert(0, "No risk signals: verified by one-time code on the first try.")
    return level, notes
