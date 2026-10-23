import threading

from stormdesk import approvals
from stormdesk.approvals.graph import forget_compiled
from stormdesk.config import settings
from stormdesk.store.db import connect
from tests.helpers import call, decide, identify, incident, latest_code, messages, request_action, verify


def test_account_changes_need_verification(client):
    identify(client, "c1")
    out = call(client, "request_sensitive_action", conversation_id="c1", action="mfa_reset", reason="new phone",
               caller_confirmed=True)
    assert out["error"] == "not_verified"


def test_request_needs_caller_agreement(client):
    verify(client, "c1")
    out = call(client, "request_sensitive_action", conversation_id="c1", action="mfa_reset", reason="new phone")
    assert out["needs_confirmation"]
    assert client.get("/admin/approvals").json()["approvals"] == []


def test_full_mfa_reset(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    assert req["status"] == "pending"
    assert incident(client, req["ticket"])["state"] == "on_hold"

    queue = client.get("/admin/approvals", params={"status": "pending"}).json()["approvals"]
    assert queue[0]["approval_id"] == req["approval_id"]
    assert queue[0]["risk_level"] == "low"
    assert "risk_level" not in req  # risk signals are for the technician, not the caller

    decided = decide(client, req["approval_id"], "E1019").json()
    assert decided["status"] == "executed" and decided["decided_by"] == "E1019"
    assert "enroll.acme.example" in messages(client, "E1001")[0]["body"]
    ticket = incident(client, req["ticket"])
    assert ticket["state"] == "resolved" and "Vikram Rao" in ticket["notes"][-1]["note"]
    with connect() as conn:
        change = conn.execute("SELECT * FROM identity_changes").fetchone()
    assert change["action"] == "mfa_reset" and change["performed_by"] == "E1019"

    status = call(client, "check_approval_status", conversation_id="c1", approval_id=req["approval_id"])
    assert status["status"] == "executed" and "Vikram" in status["agent_hint"]


def test_rejection(client):
    verify(client, "c1")
    req = request_action(client, "c1", "account_unlock", "locked out")
    decide(client, req["approval_id"], approve=False, note="Caller sounded unsure")
    status = call(client, "check_approval_status", conversation_id="c1", approval_id=req["approval_id"])
    assert status["status"] == "rejected"
    assert "Caller sounded unsure" not in status["agent_hint"]  # internal note stays internal
    assert "was not approved" in messages(client, "E1001")[0]["body"]


def test_only_active_it_staff_can_decide(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    assert decide(client, req["approval_id"], "E1002").status_code == 403  # Sales VP
    assert decide(client, req["approval_id"], "E9999").status_code == 403


def test_nobody_approves_their_own_request(client):
    verify(client, "c1", "E1019", "Vikram Rao")  # the technician calls in for himself
    req = request_action(client, "c1", "account_unlock", "locked out")
    assert decide(client, req["approval_id"], "E1019").status_code == 403
    assert decide(client, req["approval_id"], "E1021").json()["status"] == "executed"


def test_cannot_decide_twice(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    decide(client, req["approval_id"])
    assert decide(client, req["approval_id"], approve=False).status_code == 409


def test_pending_approval_survives_a_restart(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    forget_compiled()  # what a server restart does to the in-memory graph
    assert decide(client, req["approval_id"]).json()["status"] == "executed"


def test_forgotten_approval_expires(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    with connect() as conn:
        conn.execute("UPDATE approvals SET created_at = '2000-01-01T00:00:00+00:00'")
    result = client.post("/admin/housekeeping").json()
    assert result["expired_approvals"] == [req["approval_id"]]
    status = call(client, "check_approval_status", conversation_id="c1", approval_id=req["approval_id"])
    assert status["status"] == "expired"
    assert "wasn't reviewed in time" in messages(client, "E1001")[0]["body"]


def test_identity_system_down_marks_failed(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    client.post("/admin/chaos", json={"flag": "identity_down", "enabled": True})
    assert decide(client, req["approval_id"]).json()["status"] == "failed"
    assert "could not be applied" in incident(client, req["ticket"])["notes"][-1]["note"]
    status = call(client, "check_approval_status", conversation_id="c1", approval_id=req["approval_id"])
    assert "didn't go through" in status["agent_hint"]


def test_risk_signals_for_a_shaky_vip_caller(client):
    call(client, "lookup_employee", conversation_id="c1", employee_id="E1011", full_name="Grace Parker Smith")
    identify(client, "c1", "E1011", "Grace Park")
    call(client, "send_verification_code", conversation_id="c1")
    call(client, "check_verification_code", conversation_id="c1", code="000000")
    assert call(client, "check_verification_code", conversation_id="c1", code=latest_code(client, "E1011"))["verified"]
    req = request_action(client, "c1")
    approval = client.get(f"/admin/approvals/{req['approval_id']}").json()
    assert approval["risk_level"] == "high"
    notes = " ".join(approval["risk_notes"])
    assert "2 tries" in notes and "wrong employee ID or name" in notes and "VIP" in notes


def test_status_waits_for_a_decision_made_meanwhile(client, monkeypatch):
    verify(client, "c1")
    req = request_action(client, "c1")
    monkeypatch.setattr(settings, "approval_poll_s", 8)
    timer = threading.Timer(1.0, approvals.decide, args=(req["approval_id"], "E1019", True))
    timer.start()
    status = call(client, "check_approval_status", conversation_id="c1", approval_id=req["approval_id"])
    timer.join()
    assert status["status"] == "executed"


def test_long_wait_tells_agent_to_stop_holding(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    with connect() as conn:
        conn.execute("UPDATE approvals SET created_at = ?", ("2026-01-01T00:00:00+00:00",))
    status = call(client, "check_approval_status", conversation_id="c1", approval_id=req["approval_id"])
    assert "taking longer than usual" in status["agent_hint"]


def test_approvals_are_private_to_the_caller(client):
    verify(client, "c1")
    req = request_action(client, "c1")
    identify(client, "c2", "E1003", "Mei Lin Chen")
    out = call(client, "check_approval_status", conversation_id="c2", approval_id=req["approval_id"])
    assert out["error"] == "unknown_approval"


def test_repeat_request_returns_the_pending_one(client):
    verify(client, "c1")
    first = request_action(client, "c1")
    again = request_action(client, "c1")
    assert again["approval_id"] == first["approval_id"]
    assert len(client.get("/admin/approvals").json()["approvals"]) == 1


def test_access_grant_needs_a_resource(client):
    verify(client, "c1")
    out = call(client, "request_sensitive_action", conversation_id="c1", action="access_grant",
               reason="new project", caller_confirmed=True)
    assert out["error"] == "missing_resource"
