import pytest

from stormdesk.redact import redact
from stormdesk.tickets import priority_for, spoken
from tests.helpers import call, identify, incident, messages


def _count(client):
    return len(client.get("/admin/incidents").json()["incidents"])


def test_create_needs_caller_confirmation_first(client):
    identify(client, "c1", "E1003", "Mei Lin Chen")
    before = _count(client)
    draft = call(client, "create_incident", conversation_id="c1", summary="Zoom audio echo", service="zoom")
    assert draft["needs_confirmation"] and "Zoom audio echo" in draft["read_back"]
    assert _count(client) == before

    done = call(client, "create_incident", conversation_id="c1", summary="Zoom audio echo", service="zoom",
                urgency="blocked", caller_confirmed=True)
    assert done["created"] and done["priority"] == 3
    assert "standard priority" in draft["read_back"] and "Priority 3" not in draft["read_back"]
    ticket = incident(client, done["number"])
    assert ticket["employee_id"] == "E1003" and ticket["category"] == "collaboration"
    assert ticket["conversation_id"] == "c1"


@pytest.mark.parametrize("impact, urgency, vip, expected", [
    ("just_me", "can_work", False, 4),
    ("just_me", "blocked", False, 3),
    ("site", "blocked", False, 1),
    ("company", "can_work", False, 2),
    ("just_me", "slowed", True, 2),
    ("just_me", "can_work", True, 3),
    ("team", "blocked", True, 2),
])
def test_priority_matrix(impact, urgency, vip, expected):
    assert priority_for(impact, urgency, vip) == expected


def test_duplicate_points_to_existing_ticket(client):
    identify(client, "c1")  # Priya already has INC0010001 open for the VPN
    out = call(client, "create_incident", conversation_id="c1", summary="VPN dropping again", service="vpn",
               caller_confirmed=True)
    assert out["created"] is False
    assert out["duplicate_of"]["number"] == "INC0010001"
    assert "add_ticket_note" in out["agent_hint"]


def test_fixed_on_call_is_logged_resolved(client):
    identify(client, "c1")
    out = call(client, "create_incident", conversation_id="c1", summary="VPN fixed by reconnecting", service="vpn",
               resolved_on_call=True, caller_confirmed=True)
    assert out["created"]
    assert incident(client, out["number"])["state"] == "resolved"


def test_passwords_never_reach_the_ticket(client):
    identify(client, "c1", "E1003", "Mei Lin Chen")
    out = call(client, "create_incident", conversation_id="c1", summary="Gmail login fails, my password is Hunter22!",
               details="Tried code 482913 from my phone", caller_confirmed=True)
    ticket = incident(client, out["number"])
    assert "Hunter22" not in ticket["short_description"] and "[redacted]" in ticket["short_description"]
    assert "482913" not in ticket["description"]


@pytest.mark.parametrize("text, expected", [
    ("my password is Summer2026!", "my password is [redacted]"),
    ("password: hunter2", "password: [redacted]"),
    ("my password is expired", "my password is expired"),
    ("card 4111 1111 1111 1111 declined", "card [card number redacted] declined"),
    ("ticket INC0010001 and phone +1-555-0101", "ticket INC0010001 and phone +1-555-0101"),
])
def test_redact(text, expected):
    assert redact(text) == expected


def test_ticket_system_down_queues_then_delivers(client):
    identify(client, "c1", "E1003", "Mei Lin Chen")
    client.post("/admin/chaos", json={"flag": "itsm_down", "enabled": True})
    before = _count(client)
    out = call(client, "create_incident", conversation_id="c1", summary="Figma won't open", service="figma",
               caller_confirmed=True)
    assert out["queued"] and out["reference"] == "PEND-0001"
    assert "PEND-0001" in out["agent_hint"]
    assert _count(client) == before

    restored = client.post("/admin/chaos", json={"flag": "itsm_down", "enabled": False}).json()
    delivered = restored["delivered_from_outbox"]["delivered"]
    assert delivered[0]["ref"] == "PEND-0001"
    assert incident(client, delivered[0]["result"])["short_description"] == "Figma won't open"
    assert "PEND-0001 is now ticket" in messages(client, "E1003")[0]["body"]


def test_notes_only_on_the_callers_own_tickets(client):
    identify(client, "c1")
    other = call(client, "add_ticket_note", conversation_id="c1", number="INC0010003", note="hi")  # Daniel's
    missing = call(client, "add_ticket_note", conversation_id="c1", number="INC0099999", note="hi")
    assert other == missing and other["error"] == "not_callers_ticket"

    out = call(client, "add_ticket_note", conversation_id="c1", number="10001", note="Still dropping on Wi-Fi",
               mark_resolved=False)
    assert out["number"] == "INC0010001"
    assert incident(client, "INC0010001")["notes"][-1]["note"] == "Still dropping on Wi-Fi"


def test_note_can_mark_fixed(client):
    identify(client, "c1")
    call(client, "add_ticket_note", conversation_id="c1", number="INC0010001", note="Works on cable",
         mark_resolved=True)
    assert incident(client, "INC0010001")["state"] == "resolved"


def test_note_is_queued_when_ticket_system_down(client):
    identify(client, "c1")
    client.post("/admin/chaos", json={"flag": "itsm_down", "enabled": True})
    out = call(client, "add_ticket_note", conversation_id="c1", number="INC0010001", note="later")
    assert out["queued"]
    client.post("/admin/chaos", json={"flag": "itsm_down", "enabled": False})
    assert incident(client, "INC0010001")["notes"][-1]["note"] == "later"


def test_spoken_ticket_number():
    assert spoken("INC0010013") == "I N C 1 0 0 1 3"
