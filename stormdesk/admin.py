"""Endpoints for people, not the voice agent: the technician's approvals, tickets, simulated phones,
live status board, post-call reviews, demo and failure switches, audit trail. The console uses these.

Local-only unless STORMDESK_ADMIN_SECRET is set (see require_admin_key)."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from stormdesk import approvals, chaos, housekeeping, messaging, outbox, policy, sessions, storm
from stormdesk.approvals import store as approval_store
from stormdesk.config import settings
from stormdesk.itsm import itsm
from stormdesk.resolve import ResolveError, resolve_incident
from stormdesk.review import followups
from stormdesk.review import runner as review_runner
from stormdesk.review import store as review_store
from stormdesk.seed import add_storm, seed
from stormdesk.sources import vendor_status
from stormdesk.store import audit
from stormdesk.tools.common import require_admin_key

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin_key)])

ERROR_STATUS = {"not_found": 404, "not_pending": 409, "forbidden": 403, "lost": 409, "already_closed": 409,
                "already_created": 409}


# --- overview ---

@router.get("/admin/overview")
async def overview():
    """The numbers for the console's sidebar, refreshed every few seconds."""
    board = storm.board()
    return {
        "company": settings.company_name,
        "pending_approvals": len(approval_store.list_approvals("pending", limit=500)),
        "open_incidents": len(itsm.list_incidents(open_only=True, limit=10_000)),
        "major_incidents": sum(1 for row in board if row["major_incident"]),
        "storms_building": sum(1 for row in board if not row["major_incident"]
                               and row["open_reports"] + 1 >= row["threshold"]),
        "outbox_pending": len(outbox.entries("pending")),
        "reviews": review_store.counts(),
        "drills_on": [flag for flag, on in chaos.all_flags().items() if on],
        "demo_outages": [d["service_key"] for d in vendor_status.list_demo_outages()],
    }


@router.get("/status/overview")
async def status_overview():
    """Every tracked service at once, for the console's status board."""
    return {"services": await vendor_status.all_statuses()}


@router.get("/admin/storm-board")
async def storm_board():
    return {"services": storm.board()}


@router.get("/admin/services")
async def list_services():
    return {"services": [{"key": s.key, "name": s.name, "kind": s.kind, "aliases": s.aliases}
                         for s in vendor_status.SERVICES.values()]}


@router.get("/admin/employees")
async def list_employees(department: str | None = None):
    return {"employees": itsm.list_employees(department)}


@router.get("/admin/policy")
async def get_policy():
    return {"tiers": policy.TIERS, "never": policy.NEVER, "sensitive_actions": policy.SENSITIVE_ACTIONS}


# --- approvals: the technician's queue ---

@router.get("/admin/approvals")
async def list_approvals(status: str | None = None, limit: int = 50):
    return {"approvals": approval_store.list_approvals(status, limit)}


@router.get("/admin/approvals/{approval_id}")
async def get_approval(approval_id: str):
    approval = approval_store.get(approval_id.upper())
    if not approval:
        raise HTTPException(404, f"No approval {approval_id}")
    return approval


class DecisionIn(BaseModel):
    technician_id: str
    approve: bool
    note: str = ""


@router.post("/admin/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, body: DecisionIn):
    try:
        return approvals.decide(approval_id.upper(), body.technician_id, body.approve, body.note)
    except approvals.ApprovalError as exc:
        raise HTTPException(ERROR_STATUS[exc.code], str(exc)) from exc


# --- tickets, phones, calls ---

@router.get("/admin/incidents")
async def list_incidents(open_only: bool = False, limit: int = 100):
    return {"incidents": itsm.list_incidents(open_only, limit)}


@router.get("/admin/incidents/{number}")
async def get_incident(number: str):
    incident = itsm.get_incident(number.upper())
    if not incident:
        raise HTTPException(404, f"No incident {number}")
    incident["children"] = itsm.children_of(incident["number"], open_only=False) if incident["is_major"] else []
    return incident


class ResolveIn(BaseModel):
    technician_id: str
    note: str = ""


@router.post("/admin/incidents/{number}/resolve")
async def resolve(number: str, body: ResolveIn):
    try:
        return resolve_incident(number.upper(), body.technician_id, body.note)
    except ResolveError as exc:
        raise HTTPException(ERROR_STATUS[exc.code], str(exc)) from exc


@router.get("/admin/messages")
async def list_messages(employee_id: str | None = None, limit: int = 50):
    """The simulated phones and inboxes: verification codes, approval results, outage texts."""
    return {"messages": messaging.inbox(employee_id.upper() if employee_id else None, limit)}


@router.get("/admin/sessions")
async def list_sessions(limit: int = 30):
    return {"sessions": sessions.recent(limit)}


@router.get("/admin/sessions/{conversation_id}")
async def get_session(conversation_id: str):
    session = sessions.get(conversation_id)
    if not session:
        raise HTTPException(404, f"No session {conversation_id}")
    return session


@router.get("/admin/audit")
async def audit_trail(limit: int = 50, conversation_id: str | None = None):
    return {"entries": audit.recent(limit, conversation_id)}


# --- post-call reviews ---

@router.get("/admin/reviews")
async def list_reviews(limit: int = 50):
    return {"reviews": review_store.list_reviews(limit)}


@router.get("/admin/reviews/{conversation_id}")
async def get_review(conversation_id: str):
    review = review_store.get(conversation_id)
    if not review:
        raise HTTPException(404, f"No review for {conversation_id}")
    return review


@router.post("/admin/reviews/{conversation_id}/run")
async def run_review(conversation_id: str):
    """Start (or redo) a review in the background; it takes about half a minute."""
    asyncio.get_running_loop().create_task(review_runner.review(conversation_id, source="manual"))
    return {"started": True, "conversation_id": conversation_id}


class FollowUpIn(BaseModel):
    technician_id: str


@router.post("/admin/reviews/{conversation_id}/follow-ups/{index}")
async def create_follow_up(conversation_id: str, index: int, body: FollowUpIn):
    try:
        return {"ticket": followups.create_ticket(conversation_id, index, body.technician_id)}
    except followups.FollowUpError as exc:
        raise HTTPException(ERROR_STATUS[exc.code], str(exc)) from exc


# --- demo switches, failure drills, the outbox ---

class DemoOutageIn(BaseModel):
    service: str
    title: str = "Users unable to connect"
    impact: Literal["degraded", "outage"] = "outage"


@router.post("/admin/demo-outage")
async def set_demo_outage(body: DemoOutageIn):
    service = vendor_status.resolve_service(body.service)
    if not service:
        raise HTTPException(404, f"Unknown service: {body.service}")
    vendor_status.set_demo_outage(service.key, body.title, body.impact)
    return {"ok": True, "service": service.key, "demo": True}


@router.delete("/admin/demo-outage/{service}")
async def clear_demo_outage(service: str):
    resolved = vendor_status.resolve_service(service)
    return {"ok": bool(resolved) and vendor_status.clear_demo_outage(resolved.key)}


@router.get("/admin/demo-outages")
async def list_demo_outages():
    return {"demo_outages": vendor_status.list_demo_outages()}


class DemoStormIn(BaseModel):
    service: str = "vpn"
    location: str = "Chennai"
    count: int = Field(2, ge=1, le=5)


@router.post("/admin/demo-storm")
async def demo_storm(body: DemoStormIn):
    """Open fresh reports from colleagues, so the next caller tips a storm (the rehearsal's scene 3)."""
    service = vendor_status.resolve_service(body.service)
    if not service:
        raise HTTPException(404, f"Unknown service: {body.service}")
    try:
        return {"opened": add_storm(service.key, body.location, body.count)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/admin/chaos")
async def get_chaos():
    return {"flags": chaos.all_flags(), "descriptions": chaos.FLAGS}


class ChaosIn(BaseModel):
    flag: Literal["itsm_down", "sms_down", "identity_down", "feeds_down"]
    enabled: bool


@router.post("/admin/chaos")
async def set_chaos(body: ChaosIn):
    chaos.set_flag(body.flag, body.enabled)
    result = {"flags": chaos.all_flags()}
    if body.flag == "itsm_down" and not body.enabled:
        result["delivered_from_outbox"] = await housekeeping.run_once()
    return result


@router.get("/admin/outbox")
async def get_outbox(status: str | None = None):
    return {"entries": outbox.entries(status)}


@router.post("/admin/housekeeping")
async def run_housekeeping():
    """Deliver queued tickets and expire stale approvals now, instead of waiting for the next cycle."""
    return await housekeeping.run_once()


class ResetIn(BaseModel):
    confirm: bool


@router.post("/admin/reset")
async def reset_practice_data(body: ResetIn):
    if not body.confirm:
        raise HTTPException(400, "Send {\"confirm\": true} to wipe and reload the practice company.")
    return {"ok": True, "backup": seed(reset=True)}
