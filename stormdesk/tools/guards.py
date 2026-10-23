"""Who is on the line, and what they're allowed to do. Every write tool starts here.

The employee a tool acts for always comes from the call's session, never from what the AI passes
in, so the agent cannot be talked into acting for someone else."""

from stormdesk import sessions
from stormdesk.identity import normalize_employee_id
from stormdesk.itsm import itsm

LOCKED_HINT = (
    "Verification failed too many times on this call. Don't look up records or help with anything "
    "account-related. Say politely that you can't verify them by phone, and that a text with next steps has "
    "been sent to the mobile number on file. Don't suggest anyone is suspected of anything."
)
NOT_IDENTIFIED_HINT = "Identify the caller first: ask for their employee ID and full name, then call lookup_employee."
INACTIVE_HINT = (
    "This account is not active. Don't troubleshoot, look anything up, or create requests for it. "
    "Say you can't help with this account by phone; the next step is visiting the IT desk in person or asking "
    "their manager to raise a request."
)
NOT_VERIFIED_HINT = (
    "This needs a verified identity. Call send_verification_code, ask the caller to read out the code "
    "they receive, then call check_verification_code."
)
OTHER_EMPLOYEE_HINT = (
    "You can only look at the caller's own records. Never share or look up another employee's information."
)


def refusal(error: str, hint: str) -> dict:
    return {"ok": False, "error": error, "agent_hint": hint}


def current_caller(conversation_id: str | None, *, verified: bool = False) -> tuple[dict | None, dict | None]:
    """(employee, None) if this call may proceed, else (None, refusal to return to the agent)."""
    if not conversation_id:
        return None, refusal("no_conversation", NOT_IDENTIFIED_HINT)
    session = sessions.get(conversation_id)
    if session and session["locked"]:
        return None, refusal("session_locked", LOCKED_HINT)
    if not session or not session["employee_id"]:
        return None, refusal("not_identified", NOT_IDENTIFIED_HINT)
    employee = itsm.get_employee(session["employee_id"])
    if not employee or employee["status"] != "active":
        return None, refusal("account_inactive", INACTIVE_HINT)
    if verified and not session["verified_at"]:
        return None, refusal("not_verified", NOT_VERIFIED_HINT)
    return employee, None


def caller_scope(employee_id: str, conversation_id: str | None) -> tuple[dict | None, dict | None]:
    """For read tools that take an employee_id. On a live call it must be the caller's own ID.
    Without a conversation id (the console, local testing) any active employee is allowed."""
    if conversation_id:
        employee, refused = current_caller(conversation_id)
        if refused:
            return None, refused
        if normalize_employee_id(employee_id) != employee["employee_id"]:
            return None, refusal("not_the_caller", OTHER_EMPLOYEE_HINT)
        return employee, None
    normalized = normalize_employee_id(employee_id)
    employee = itsm.get_employee(normalized) if normalized else None
    if not employee or employee["status"] != "active":
        return None, refusal("unknown_employee",
                             "No active employee with that ID. Run lookup_employee first and use the ID it returns.")
    return employee, None
