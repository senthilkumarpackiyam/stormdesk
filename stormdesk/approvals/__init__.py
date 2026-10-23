"""Requests that need a human: start one, let a technician decide, expire forgotten ones."""

from stormdesk import timeutil
from stormdesk.approvals import graph, store
from stormdesk.config import settings
from stormdesk.staff import get_technician


class ApprovalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def start(kind: str, reason: str, **fields) -> dict:
    approval_id = store.create(kind, reason, **fields)
    graph.start(approval_id)
    return store.get(approval_id)


def decide(approval_id: str, technician_id: str, approve: bool, note: str = "") -> dict:
    approval = store.get(approval_id)
    if not approval:
        raise ApprovalError("not_found", f"No approval {approval_id}.")
    if approval["status"] != "pending":
        raise ApprovalError("not_pending", f"{approval_id} is already {approval['status']}.")
    technician = get_technician(technician_id)
    if not technician:
        raise ApprovalError("forbidden", "Only active IT staff can decide approvals.")
    tech_id = technician["employee_id"]
    if technician["employee_id"] == approval["employee_id"]:
        raise ApprovalError("forbidden", "Nobody can approve their own request.")
    if not graph.is_waiting(approval_id):
        store.update(approval_id, status="failed", result={"error": "approval process state was lost"})
        raise ApprovalError("lost", f"{approval_id} is not waiting for a decision.")

    store.update(approval_id, status="approved" if approve else "rejected", decided_by=tech_id,
                 decision_note=note, decided_at=timeutil.now_iso())
    graph.resume(approval_id, {"approve": approve, "technician_id": tech_id,
                               "technician_name": technician["full_name"], "note": note})
    return store.get(approval_id)


def expire_stale() -> list[str]:
    cutoff = timeutil.ago_iso(minutes=settings.approval_ttl_min)
    expired = []
    for approval in store.list_approvals(status="pending", limit=500):
        if approval["created_at"] < cutoff and graph.is_waiting(approval["approval_id"]):
            store.update(approval["approval_id"], decided_at=timeutil.now_iso())
            graph.resume(approval["approval_id"], {"approve": False, "expired": True})
            expired.append(approval["approval_id"])
    return expired
