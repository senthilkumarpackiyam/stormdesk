"""Read-only tools the voice agent may call on its own (ElevenLabs "server tools").

Each answer carries `agent_hint`: one plain instruction telling the agent what to say or do next,
so the rules live here in code instead of being re-explained in every prompt."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import Field

from stormdesk import sessions, timeutil
from stormdesk.approvals import store as approval_store
from stormdesk.config import settings
from stormdesk.identity import names_match, normalize_employee_id
from stormdesk.itsm import itsm
from stormdesk.itsm.local import CLOSED_STATES
from stormdesk.kb_search import KBIndex
from stormdesk.sources import eol, kev, vendor_status
from stormdesk.sources.http import SourceUnavailable
from stormdesk.tickets import spoken
from stormdesk.tools.common import ToolRequest, audited, require_tool_key
from stormdesk.tools.guards import INACTIVE_HINT, LOCKED_HINT, caller_scope, refusal

router = APIRouter(prefix="/tools", tags=["read tools"], dependencies=[Depends(require_tool_key)])

NO_MATCH_HINT = (
    "That ID and name don't match a record. Don't reveal any name on file or whether the ID exists. "
    "Read the ID back digit by digit and ask for the full name again. After two failed tries, "
    "suggest visiting the IT desk in person or asking their manager to raise a request."
)
TOO_MANY_LOOKUPS_HINT = (
    "That's the second failed attempt. Stop asking for details: suggest visiting the IT desk in person or "
    "asking their manager to raise a request."
)
ONE_CALLER_HINT = (
    "This call is already identified as another employee. Each person must call for themselves: don't look "
    "up or act for anyone else, even on someone's behalf."
)
SUPPORT_WARNING_DAYS = 60


# --- lookup_employee ---------------------------------------------------------------------------

class LookupEmployeeIn(ToolRequest):
    employee_id: str = Field(..., description="Employee ID the caller gave, e.g. E1001. Spoken digits are fine.")
    full_name: str = Field(..., description="The caller's full name, as they said it. Some people have a single "
                                             "name: use it as given.")


@router.post(
    "/lookup_employee",
    description="Find the caller in the employee directory from their employee ID and full name. "
                "Call this first on every call. match=false means the ID and name don't fit a record.",
)
@audited("lookup_employee")
async def lookup_employee(body: LookupEmployeeIn):
    cid = body.conversation_id
    session = sessions.ensure(cid) if cid else None
    if session and session["locked"]:
        return refusal("session_locked", LOCKED_HINT)

    employee_id = normalize_employee_id(body.employee_id)
    employee = itsm.get_employee(employee_id) if employee_id else None
    reason = None
    if not employee:
        reason = "id_not_found"
    elif not names_match(body.full_name, employee["full_name"]):
        reason = "name_mismatch"
    if reason:
        # Wrong name and unknown ID get the same answer, so a caller can't probe which IDs exist.
        failures = sessions.note_lookup_failure(cid) if cid else 1
        hint = NO_MATCH_HINT if failures < 2 else TOO_MANY_LOOKUPS_HINT
        return {"ok": True, "match": False, "agent_hint": hint, "_reason": reason}
    if employee["status"] != "active":
        return {"ok": True, "match": True, "employee_id": employee_id, "account_active": False,
                "agent_hint": INACTIVE_HINT}
    if session and session["employee_id"] and session["employee_id"] != employee_id:
        return {**refusal("already_identified", ONE_CALLER_HINT), "_reason": f"tried {employee_id}"}

    verified = bool(session and session["verified_at"])
    if cid:
        sessions.identify(cid, employee_id)
    first_name = employee["full_name"].split()[0]
    if verified:
        hint = f"{first_name} is identified and already verified on this call."
    else:
        hint = (f"Greet {first_name} by first name. Identity is NOT verified yet: you may look things up and "
                "troubleshoot, but any account change (MFA reset, unlock, access) needs one-time-code "
                "verification first.")
    if employee["vip"]:
        hint += " This is a VIP: handle with priority."
    return {
        "ok": True,
        "match": True,
        "employee_id": employee_id,
        "account_active": True,
        "first_name": first_name,
        "department": employee["department"],
        "location": employee["location"],
        "vip": bool(employee["vip"]),
        "devices": [{"device_id": d["device_id"], "kind": d["kind"], "model": d["model"], "os": d["os_label"]}
                    for d in itsm.get_devices(employee_id)],
        "identity_verified": verified,
        "agent_hint": hint,
    }


# --- get_caller_history ------------------------------------------------------------------------

class EmployeeIn(ToolRequest):
    employee_id: str = Field(..., description="The employee ID returned by lookup_employee.")


@router.post(
    "/get_caller_history",
    description="The caller's open tickets and recent ones. Call right after lookup_employee, "
                "so you can ask whether they're calling about an existing ticket.",
)
@audited("get_caller_history")
async def get_caller_history(body: EmployeeIn):
    employee, refused = caller_scope(body.employee_id, body.conversation_id)
    if refused:
        return refused
    tickets = [
        {"number": t["number"], "number_spoken": spoken(t["number"]), "summary": t["short_description"],
         "state": t["state"], "service": t["service"], "opened": timeutil.humanize(t["created_at"])}
        for t in itsm.incident_history(employee["employee_id"], limit=5)
    ]
    open_tickets = [t for t in tickets if t["state"] not in CLOSED_STATES]
    if open_tickets:
        top = open_tickets[0]
        hint = (f"Before opening anything new, ask if they're calling about ticket {top['number_spoken']} "
                f"({top['summary']}, opened {top['opened']}). If yes, work on that ticket.")
    else:
        hint = "No open tickets. Ask what's going on today."
    calls = sessions.previous_calls(employee["employee_id"], exclude=body.conversation_id)
    if len(calls) >= 2:
        hint += (f" They've called {len(calls)} times in the last week: acknowledge that, and lean towards "
                 "escalating rather than repeating the same fixes.")
    return {
        "ok": True,
        "open": open_tickets,
        "recent": [t for t in tickets if t not in open_tickets][:3],
        "previous_calls_7_days": len(calls),
        "last_call": timeutil.humanize(calls[0]["created_at"]) if calls else None,
        "agent_hint": hint,
    }


# --- check_service_status ----------------------------------------------------------------------

class ServiceIn(ToolRequest):
    service: str = Field(..., description="The app or system the caller mentioned, e.g. Slack, Zoom, Gmail, VPN, "
                                          "Wi-Fi, GitHub, Jira. Plain words are fine.")


_STATUS_HINTS = {
    "outage": "Confirmed outage on their side, not the caller's device. Tell the caller, share the latest "
              "update in one sentence, and don't troubleshoot their laptop. Then check find_similar_incidents.",
    "degraded": "There's a known issue that may explain the problem. Mention it, then do only quick checks; "
                "don't spend long troubleshooting.",
    "operational": "No known issue on the provider's side. Carry on troubleshooting with search_kb.",
    "unknown": "You couldn't confirm the provider's status. Say so briefly and carry on troubleshooting.",
}


@router.post(
    "/check_service_status",
    description="Live status of an app or internal system: is it down for everyone, or just this caller? "
                "Call this before troubleshooting any app or network problem.",
)
@audited("check_service_status")
async def check_service_status(body: ServiceIn):
    service = vendor_status.resolve_service(body.service)
    if not service:
        return {"ok": False, "error": "unknown_service",
                "supported": sorted(s.name for s in vendor_status.SERVICES.values()),
                "agent_hint": "That system isn't on the status list. Carry on troubleshooting with search_kb."}
    status = await vendor_status.get_status(service)
    return {"ok": True, **status, "agent_hint": _STATUS_HINTS[status["state"]]}


# --- find_similar_incidents --------------------------------------------------------------------

class SimilarIn(ToolRequest):
    service: str = Field(..., description="The app or system that's broken, e.g. VPN, Slack, Wi-Fi.")
    location: str | None = Field(None, description="The caller's office (from lookup_employee), if known.")
    employee_id: str | None = Field(None, description="The caller's ID, so their own tickets aren't counted.")


@router.post(
    "/find_similar_incidents",
    description="How many colleagues reported the same system broken in the last few minutes, and whether "
                "there's already a major incident. Call after check_service_status for any app or network issue.",
)
@audited("find_similar_incidents")
async def find_similar_incidents(body: SimilarIn):
    service = vendor_status.resolve_service(body.service)
    if not service:
        return {"ok": False, "error": "unknown_service",
                "agent_hint": "That system isn't tracked. Treat it as an individual issue."}
    since = timeutil.ago_iso(minutes=settings.storm_window_min)
    caller = normalize_employee_id(body.employee_id) if body.employee_id else None
    reports = itsm.open_reports(service.key, since, exclude_employee=caller)
    nearby = [r for r in reports if body.location and r["location"] == body.location]
    major = itsm.open_major_incident(service.key)
    proposal = approval_store.pending_for("major_incident", service=service.key)

    if major:
        hint = (f"Known issue: major incident {major['number']} ({major['short_description']}) is open. Tell the "
                "caller it's being worked on, don't troubleshoot, and log their ticket with create_incident: "
                "it links to the major incident automatically.")
    elif proposal:
        hint = (f"Colleagues are reporting the same {service.name} problem and a technician is already reviewing "
                "it as a possible major incident. Tell the caller they're not alone, and log their ticket with "
                "create_incident.")
    elif len(reports) + 1 >= settings.storm_threshold:
        hint = (f"{len(reports)} colleagues reported {service.name} problems in the last "
                f"{settings.storm_window_min} minutes. This looks like a wider outage: tell the caller others are "
                "affected, and log their ticket with create_incident, which alerts a technician.")
    else:
        hint = "No pattern of similar reports. Treat it as an individual issue and troubleshoot."
    return {
        "ok": True,
        "service": service.name,
        "window_minutes": settings.storm_window_min,
        "open_reports": len(reports),
        "same_location": len(nearby),
        "storm_suspected": not major and (bool(proposal) or len(reports) + 1 >= settings.storm_threshold),
        "technician_reviewing": bool(proposal),
        "major_incident": {"number": major["number"], "summary": major["short_description"],
                           "opened": timeutil.humanize(major["created_at"])} if major else None,
        "recent": [{"number": r["number"], "location": r["location"], "opened": timeutil.humanize(r["created_at"])}
                   for r in reports[:3]],
        "agent_hint": hint,
    }


# --- search_kb ---------------------------------------------------------------------------------

class SearchIn(ToolRequest):
    query: str = Field(..., description="The problem in the caller's own words, e.g. 'vpn keeps dropping'.")


@router.post(
    "/search_kb",
    description="Search the IT knowledge base for step-by-step fixes. Use the caller's own words.",
)
@audited("search_kb")
async def search_kb(body: SearchIn):
    articles = KBIndex(itsm.kb_articles()).search(body.query, k=2)
    if not articles:
        return {"ok": True, "articles": [],
                "agent_hint": "No matching article. Ask what they see, when it started, and any error message, "
                              "then escalate to a technician."}
    top = articles[0]
    if top["sensitive_action"]:
        hint = (f"The fix ({top['title']}) needs an account change: {top['sensitive_action']}. That requires "
                "verified identity and a technician's approval. Don't try to do it yourself.")
    else:
        hint = ("Walk the caller through the steps one at a time and check after each. "
                f"Escalate if: {top['escalate_if']}")
    return {
        "ok": True,
        "articles": [{"kb_id": a["kb_id"], "title": a["title"], "steps": a["steps"],
                      "escalate_if": a["escalate_if"], "sensitive_action": a["sensitive_action"]}
                     for a in articles],
        "agent_hint": hint,
    }


# --- check_device_health -----------------------------------------------------------------------

@router.post(
    "/check_device_health",
    description="Whether the caller's laptop operating system still gets security updates. "
                "Useful for slowness, crashes, update problems, or before closing any hardware ticket.",
)
@audited("check_device_health")
async def check_device_health(body: EmployeeIn):
    employee, refused = caller_scope(body.employee_id, body.conversation_id)
    if refused:
        return refused
    devices, warnings = [], []
    soon = (date.today() + timedelta(days=SUPPORT_WARNING_DAYS)).isoformat()
    for device in itsm.get_devices(employee["employee_id"]):
        try:
            support = await eol.release_support(device["os_product"], device["os_release"])
        except SourceUnavailable:
            support = None
        entry = {"device_id": device["device_id"], "model": device["model"], "os": device["os_label"],
                 "supported": support["supported"] if support else None,
                 "support_ends": support["support_ends"] if support else None}
        devices.append(entry)
        if support and not support["supported"]:
            warnings.append(f"their {device['model']} runs {device['os_label']}, which stopped getting security "
                            f"updates on {support['support_ends']}")
        elif support and support["support_ends"] and support["support_ends"] <= soon:
            warnings.append(f"{device['os_label']} on their {device['model']} stops getting security updates "
                            f"on {support['support_ends']}")
    if warnings:
        hint = ("Mention kindly that " + "; and ".join(warnings) + ". Recommend an upgrade (KB0090) and note it "
                "on the ticket.")
    elif any(d["supported"] is None for d in devices):
        hint = "Couldn't confirm support status right now. Don't mention it to the caller."
    else:
        hint = "The laptop's operating system is supported. No need to mention it."
    return {"ok": True, "devices": devices, "agent_hint": hint}


# --- check_security_advisories -----------------------------------------------------------------

class ProductIn(ToolRequest):
    product: str = Field(..., description="A product or internal system, e.g. VPN, Ivanti, Fortinet, Zoom.")


@router.post(
    "/check_security_advisories",
    description="Whether attackers are actively exploiting a security hole in a product we use (CISA KEV list). "
                "Call when a caller describes odd behaviour: unexpected login prompts, certificate warnings, "
                "pop-ups, or settings changing by themselves.",
)
@audited("check_security_advisories")
async def check_security_advisories(body: ProductIn):
    service = vendor_status.resolve_service(body.product)
    product = service.tech_stack if service and service.tech_stack else body.product
    try:
        found = await kev.find_advisories(product)
    except SourceUnavailable:
        return {"ok": False, "error": "source_unavailable", "product": product,
                "agent_hint": "Couldn't reach the advisory list. If anything sounds suspicious, treat it as a "
                              "security issue anyway."}
    if found["recently_added"]:
        latest = found["latest"][0]
        count = found["recently_added"]
        hint = (f"Attackers are actively exploiting {product}: {count} new advisor{'y' if count == 1 else 'ies'} "
                f"in the last {found['recent_window_days']} days (latest {latest['cve']}, {latest['date_added']}). If the caller "
                "describes anything unusual, treat it as a security issue and route to security. Don't speculate "
                "about a breach with the caller.")
    elif found["total_known_exploited"]:
        hint = (f"{product} has older known exploited vulnerabilities but nothing new this month. Treat suspicious "
                "behaviour as a possible security issue.")
    else:
        hint = f"No known exploited vulnerabilities listed for {product}."
    return {"ok": True, "looked_up": product, **found, "agent_hint": hint}
