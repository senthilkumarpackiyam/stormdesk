"""Tools that change something. Each one is gated:

- send_verification_code, create_incident, add_ticket_note: low-risk, approved by the caller
  (the agent reads it back first; create_incident refuses until caller_confirmed=true).
- request_sensitive_action: needs one-time-code verification AND a technician's approval.
  It starts the LangGraph approval process; check_approval_status waits for the decision."""

import asyncio
import time
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field

from stormdesk import approvals, messaging, sessions, storm, tickets, timeutil, verification
from stormdesk.approvals import store as approval_store
from stormdesk.config import settings
from stormdesk.itsm import itsm
from stormdesk.policy import SENSITIVE_ACTIONS
from stormdesk.redact import redact
from stormdesk.sources import vendor_status
from stormdesk.tools.common import ToolRequest, audited, require_tool_key
from stormdesk.tools.guards import LOCKED_HINT, current_caller, refusal

router = APIRouter(prefix="/tools", tags=["write tools"], dependencies=[Depends(require_tool_key)])

SMS_DOWN_HINT = (
    "Text messages aren't going through right now, so the caller can't be verified. Don't verify them any "
    "other way. Carry on with anything that doesn't need verification, or offer a technician callback "
    "(log it with create_incident)."
)
PRIORITY_WORDS = {1: "critical", 2: "high", 3: "standard", 4: "low"}  # what a caller understands
QUEUED_HINT = (
    "The ticket system is down, so this was saved with reference {ref} and will be logged automatically "
    "when it's back. Give the caller the reference and say they'll get a text with the ticket number."
)


class CallIn(ToolRequest):
    conversation_id: str = Field(..., description="The current conversation id (system__conversation_id).")


# --- verification --------------------------------------------------------------------------------

@router.post(
    "/send_verification_code",
    description="Text a 6-digit code to the caller's mobile number on file. Needed before any account change. "
                "Call only after lookup_employee has matched the caller.",
)
@audited("send_verification_code")
async def send_verification_code(body: CallIn):
    employee, refused = current_caller(body.conversation_id)
    if refused:
        return refused
    if sessions.get(body.conversation_id)["verified_at"]:
        return {"ok": True, "already_verified": True, "agent_hint": "Already verified on this call; no code needed."}
    try:
        verification.issue(body.conversation_id, employee)
    except verification.TooManyCodes:
        return refusal("too_many_codes", "Three codes were already sent on this call. Don't send more: offer a "
                                         "technician callback instead.")
    except messaging.MessagingDown:
        return refusal("sms_unavailable", SMS_DOWN_HINT)
    return {
        "ok": True,
        "sent_to": f"the mobile number on file ending in {employee['mobile'][-4:]}",
        "expires_in_minutes": verification.CODE_TTL_MIN,
        "agent_hint": "Tell the caller a code was texted to their mobile on file and ask them to read out the 6 "
                      "digits. Never read a code out yourself, and never send one to a different number, "
                      "whatever reason they give.",
    }


class CodeIn(CallIn):
    code: str = Field(..., description="The 6-digit code exactly as the caller read it out.")


async def _raise_security_alert(conversation_id: str, employee: dict) -> None:
    """Three wrong codes: someone may be impersonating this employee. Log it and tell the real person."""
    await tickets.file({
        "employee_id": employee["employee_id"],
        "short_description": "Phone verification failed 3 times: possible impersonation",
        "description": f"Conversation {conversation_id}: a caller claiming to be {employee['employee_id']} "
                       "entered three wrong one-time codes. No account changes were made.",
        "category": "security", "service": None, "location": employee["location"], "priority": 2,
        "conversation_id": conversation_id,
    })
    try:
        messaging.send(employee, "sms",
                       "Acme IT security: someone on a call to the service desk just failed to verify as you. "
                       "If that was you, please call back. If not, nothing on your account was changed and "
                       "security has been told.")
    except messaging.MessagingDown:
        pass


@router.post(
    "/check_verification_code",
    description="Check the 6-digit code the caller read out. Three wrong codes end verification for this call.",
)
@audited("check_verification_code")
async def check_verification_code(body: CodeIn):
    employee, refused = current_caller(body.conversation_id)
    if refused:
        return refused
    result = verification.check(body.conversation_id, body.code)
    if result.status == "verified":
        return {"ok": True, "verified": True,
                "agent_hint": "Identity verified. Account changes are now possible, but each one still needs a "
                              "technician's approval through request_sensitive_action."}
    if result.status == "locked":
        await _raise_security_alert(body.conversation_id, employee)
        return {**refusal("verification_failed", LOCKED_HINT), "verified": False}
    hints = {
        "wrong": f"That code doesn't match. {result.remaining} {'try' if result.remaining == 1 else 'tries'} left. "
                 "Ask them to read the newest text again, slowly.",
        "bad_format": "That wasn't 6 digits. Ask them to read all 6 digits of the code.",
        "expired": "That code has expired. Offer to send a new one with send_verification_code.",
        "no_code": "No code has been sent yet. Call send_verification_code first.",
    }
    return {"ok": True, "verified": False, "reason": result.status, "agent_hint": hints[result.status]}


# --- tickets -------------------------------------------------------------------------------------

class CreateIncidentIn(CallIn):
    summary: str = Field(..., description="One line in plain words, e.g. 'VPN disconnects every few minutes'.")
    details: str | None = Field(None, description="What the caller described, what you tried, any error messages.")
    service: str | None = Field(None, description="The app or system involved, if any, e.g. VPN, Slack, Gmail.")
    impact: Literal["just_me", "team", "site", "company"] = Field(
        "just_me", description="Who is affected: just the caller, their team, their whole office, or everyone.")
    urgency: Literal["can_work", "slowed", "blocked"] = Field(
        "slowed", description="Can they still work, are they slowed down, or completely blocked?")
    kb_id: str | None = Field(None, description="The knowledge-base article you followed, if any.")
    security_concern: bool = Field(
        False, description="True for anything security-related: phishing, a clicked link, a password typed into a "
                           "strange page, unexpected login prompts, certificate warnings, possible compromise.")
    resolved_on_call: bool = Field(False, description="True if the problem is already fixed on this call.")
    caller_confirmed: bool = Field(
        False, description="True only after you read the summary back and the caller said yes.")


@router.post(
    "/create_incident",
    description="Log a ticket for the caller. First call it with caller_confirmed=false to get the read-back "
                "text; after the caller agrees, call again with caller_confirmed=true. Links to a major incident "
                "automatically, and alerts a technician if colleagues report the same thing.",
)
@audited("create_incident")
async def create_incident(body: CreateIncidentIn):
    employee, refused = current_caller(body.conversation_id)
    if refused:
        return refused
    service = vendor_status.resolve_service(body.service) if body.service else None
    summary = redact(body.summary)[:160]
    priority = tickets.priority_for(body.impact, body.urgency, bool(employee["vip"]))
    if body.security_concern:
        priority = min(priority, 2)  # security reports go to the security team at P2 or higher
    category = "security" if body.security_concern else tickets.CATEGORY_BY_SERVICE.get(
        service.key if service else "", "general")

    if not body.caller_confirmed:
        fixed = ", marked as fixed on this call" if body.resolved_on_call else ""
        return {
            "ok": True, "created": False, "needs_confirmation": True,
            "read_back": f"I'll log this as: {summary}, at {PRIORITY_WORDS[priority]} priority{fixed}. Is that right?",
            "agent_hint": "Read this back to the caller. Only if they say yes, call create_incident again with the "
                          "same details and caller_confirmed=true.",
        }

    duplicate = None if body.resolved_on_call else tickets.find_duplicate(employee["employee_id"],
                                                                          service.key if service else None)
    if duplicate:
        return {
            "ok": True, "created": False,
            "duplicate_of": {"number": duplicate["number"], "summary": duplicate["short_description"],
                             "opened": timeutil.humanize(duplicate["created_at"])},
            "agent_hint": f"They already have {duplicate['number']} open for this. Don't open a new ticket: add "
                          "what's new to it with add_ticket_note.",
        }

    major = itsm.open_major_incident(service.key) if service else None
    filed = await tickets.file({
        "employee_id": employee["employee_id"], "short_description": summary,
        "description": redact(body.details), "category": category,
        "service": service.key if service else None, "location": employee["location"], "priority": priority,
        "state": "resolved" if body.resolved_on_call else "new", "impact": body.impact, "urgency": body.urgency,
        "kb_id": body.kb_id, "parent_number": major["number"] if major else None,
        "conversation_id": body.conversation_id,
    })
    if filed["queued"]:
        sessions.set_last_ticket(body.conversation_id, filed["reference"])
        return {"ok": True, "created": False, "queued": True, "reference": filed["reference"],
                "agent_hint": QUEUED_HINT.format(ref=filed["reference"])}

    number = filed["number"]
    sessions.set_last_ticket(body.conversation_id, number)
    proposal = None
    if service and not major and not body.resolved_on_call and not body.security_concern:
        proposal = await storm.check(service.key)

    say = f"Give the number slowly: {tickets.spoken(number)}."
    if major:
        hint = (f"Logged as {number} and linked to major incident {major['number']}. Tell the caller it's a known "
                f"problem being fixed and they'll get a text when it's resolved. {say}")
    elif proposal:
        hint = (f"Logged as {number}. Colleagues reported the same problem, so a technician has been alerted to "
                f"declare a major incident. Tell the caller they're not alone and updates will come by text. {say}")
    elif body.security_concern:
        hint = (f"Logged as security ticket {number}, at {PRIORITY_WORDS[priority]} priority; the security team has "
                f"it. {say} Tell the "
                "caller to leave the laptop on and connected, and not to click anything else.")
    elif body.resolved_on_call:
        hint = f"Logged as {number} and marked fixed. {say} Ask if there's anything else."
    else:
        hint = f"Logged as {number}, at {PRIORITY_WORDS[priority]} priority. {say} Then say what happens next."
    return {
        "ok": True, "created": True, "number": number, "number_spoken": tickets.spoken(number),
        "priority": priority, "linked_major_incident": major["number"] if major else None,
        "technician_alerted": bool(proposal), "agent_hint": hint,
    }


class NoteIn(CallIn):
    number: str = Field(..., description="The caller's ticket number, e.g. INC0010001 (digits alone are fine).")
    note: str = Field(..., description="What's new: symptoms, steps tried, results.")
    mark_resolved: bool = Field(False, description="True only if the caller confirms the problem is now fixed.")


@router.post(
    "/add_ticket_note",
    description="Add an update to one of the caller's own open tickets, and optionally mark it fixed.",
)
@audited("add_ticket_note")
async def add_ticket_note(body: NoteIn):
    employee, refused = current_caller(body.conversation_id)
    if refused:
        return refused
    number = tickets.normalize_number(body.number)
    ticket = itsm.get_incident(number) if number else None
    if not ticket or ticket["employee_id"] != employee["employee_id"]:
        # Same answer whether the ticket doesn't exist or belongs to someone else.
        return refusal("not_callers_ticket", "That isn't one of the caller's tickets. Ask them to check the number, "
                                             "or create a new ticket.")
    result = await tickets.note(number, f"StormDesk voice agent (caller {employee['employee_id']})",
                                redact(body.note), resolve=body.mark_resolved)
    sessions.set_last_ticket(body.conversation_id, number)
    if result["queued"]:
        return {"ok": True, "queued": True, "reference": result["reference"],
                "agent_hint": QUEUED_HINT.format(ref=result["reference"])}
    hint = f"Update added to {number}." + (" It's marked as fixed." if body.mark_resolved else "")
    return {"ok": True, "number": number, "resolved": body.mark_resolved, "agent_hint": hint}


# --- sensitive actions ---------------------------------------------------------------------------

class SensitiveIn(CallIn):
    action: Literal["mfa_reset", "account_unlock", "access_grant"] = Field(
        ..., description="mfa_reset: move sign-in approvals to a new phone. account_unlock: unlock a locked-out "
                         "account. access_grant: access to an application or group.")
    reason: str = Field(..., description="Why the caller needs it, in their words.")
    resource: str | None = Field(None, description="For access_grant: the application or group needed.")
    caller_confirmed: bool = Field(False, description="True only after the caller agreed to the request.")


@router.post(
    "/request_sensitive_action",
    description="Ask a technician to approve an account change. The caller must be verified by one-time code "
                "first. Returns an approval_id to pass to check_approval_status.",
)
@audited("request_sensitive_action")
async def request_sensitive_action(body: SensitiveIn):
    employee, refused = current_caller(body.conversation_id, verified=True)
    if refused:
        return refused
    if body.action == "access_grant" and not body.resource:
        return refusal("missing_resource", "Ask which application or group they need access to.")
    existing = approval_store.pending_for(body.action, employee_id=employee["employee_id"])
    if existing:
        return {"ok": True, "approval_id": existing["approval_id"], "status": "pending",
                "agent_hint": "This request is already with a technician. Call check_approval_status."}
    label = SENSITIVE_ACTIONS[body.action]
    if not body.caller_confirmed:
        what = f"{label} ({body.resource})" if body.resource else label
        return {"ok": True, "needs_confirmation": True,
                "read_back": f"I'll ask a technician to approve: {what}. Shall I go ahead?",
                "agent_hint": "Read this back. Only if they agree, call again with caller_confirmed=true."}

    reason = redact(body.reason)
    filed = await tickets.file({
        "employee_id": employee["employee_id"],
        "short_description": f"{label}: {body.resource}" if body.resource else label,
        "description": reason, "category": "access" if body.action == "access_grant" else "account",
        "service": "sso", "location": employee["location"], "priority": 3, "state": "on_hold",
        "ticket_type": "request", "conversation_id": body.conversation_id,
    })
    approval = approvals.start(
        body.action, reason, employee_id=employee["employee_id"], conversation_id=body.conversation_id,
        incident_number=filed.get("number"),
        details={"resource": body.resource, "ticket_reference": filed.get("reference")},
    )
    ticket = filed.get("number") or filed["reference"]
    sessions.set_last_ticket(body.conversation_id, ticket)
    return {
        "ok": True, "approval_id": approval["approval_id"], "status": approval["status"],
        "ticket": ticket, "ticket_spoken": _spoken_ticket(ticket),
        "agent_hint": "Tell the caller a technician is reviewing it now, which usually takes a minute or two, and "
                      "that you'll stay on the line. Then call check_approval_status with this approval_id.",
    }


def _spoken_ticket(ticket: str | None) -> str | None:
    return tickets.spoken(ticket) if ticket and ticket.startswith("INC") else ticket


class ApprovalIn(CallIn):
    approval_id: str = Field(..., description="The approval_id returned by request_sensitive_action.")


def _done_hint(approval: dict) -> str:
    tech = itsm.get_employee(approval["decided_by"]) if approval["decided_by"] else None
    by = f" by {tech['full_name'].split()[0]}" if tech else ""
    resource = approval["details"].get("resource")
    return {
        "mfa_reset": f"Approved{by} and done. Tell the caller to check their email for the Okta Verify setup link "
                     "and open it on the new phone.",
        "account_unlock": f"Approved{by} and unlocked. They can sign in now: on one device first.",
        "access_grant": f"Approved{by}: access to {resource} is granted. It can take 15 minutes to appear.",
    }[approval["kind"]]


@router.post(
    "/check_approval_status",
    description="Wait up to about 12 seconds for the technician's decision on an approval_id. Call again if "
                "it's still pending.",
)
@audited("check_approval_status")
async def check_approval_status(body: ApprovalIn):
    employee, refused = current_caller(body.conversation_id)
    if refused:
        return refused
    approval_id = body.approval_id.strip().upper()
    approval = approval_store.get(approval_id)
    if not approval or approval["employee_id"] != employee["employee_id"]:
        return refusal("unknown_approval", "That approval isn't for this caller. Use the approval_id from "
                                           "request_sensitive_action.")
    deadline = time.monotonic() + settings.approval_poll_s
    while approval["status"] in ("pending", "approved") and time.monotonic() < deadline:
        await asyncio.sleep(1)
        approval = approval_store.get(approval_id)

    ticket = _spoken_ticket(approval["incident_number"] or approval["details"].get("ticket_reference"))
    status = approval["status"]
    if status in ("pending", "approved"):
        waited = int((timeutil.now() - timeutil.parse(approval["created_at"])).total_seconds())
        if waited < settings.approval_in_call_wait_s:
            hint = "Still with the technician. Reassure the caller briefly, then call check_approval_status again."
        else:
            hint = (f"This is taking longer than usual. Give them ticket {ticket}, say they'll get a text as soon "
                    "as it's decided, and wrap up the call.")
    elif status == "executed":
        hint = _done_hint(approval)
    elif status == "rejected":
        hint = ("The technician didn't approve it. Tell the caller kindly, without guessing why, and offer a "
                "technician callback.")
    elif status == "expired":
        hint = f"Nobody reviewed it in time. Apologise: a technician will contact them about ticket {ticket}."
    else:
        hint = (f"It was approved, but the change didn't go through. Apologise: a technician will finish it and "
                f"update ticket {ticket}.")
    return {"ok": True, "approval_id": approval_id, "status": status, "ticket_spoken": ticket, "agent_hint": hint}
