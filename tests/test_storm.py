from stormdesk.config import settings
from stormdesk.seed import add_storm
from tests.helpers import call, decide, identify, incident, messages


def _report_vpn(client, cid, employee_id, name):
    identify(client, cid, employee_id, name)
    return call(client, "create_incident", conversation_id=cid, summary="VPN won't connect", service="vpn",
                urgency="blocked", caller_confirmed=True)


def _storm_proposal(client):
    add_storm("vpn", "Chennai", settings.storm_threshold - 1)  # Ravi and Ananya already reported it
    out = _report_vpn(client, "c1", "E1004", "Karthik")
    assert out["technician_alerted"], out
    return client.get("/admin/approvals", params={"status": "pending"}).json()["approvals"][0]


def test_third_report_proposes_a_major_incident(client):
    proposal = _storm_proposal(client)
    assert proposal["kind"] == "major_incident" and proposal["service"] == "vpn"
    assert "3 open VPN reports" in proposal["risk_notes"][0]
    assert "2 from Chennai" in proposal["risk_notes"][0]


def test_more_reports_join_the_same_proposal(client):
    _storm_proposal(client)
    out = _report_vpn(client, "c2", "E1013", "Fatima Noor")
    assert out["technician_alerted"]
    assert len(client.get("/admin/approvals").json()["approvals"]) == 1
    similar = call(client, "find_similar_incidents", service="vpn")
    assert similar["technician_reviewing"] and "already reviewing" in similar["agent_hint"]


def test_declaring_it_links_everyone_and_texts_them(client):
    proposal = _storm_proposal(client)
    decided = decide(client, proposal["approval_id"], "E1019").json()
    major_number = decided["result"]["major_incident"]
    major = incident(client, major_number)
    assert major["is_major"] == 1 and major["priority"] == 1 and major["state"] == "in_progress"
    assert len(decided["result"]["linked"]) == 3 and decided["result"]["notified"] == 3
    for number in decided["result"]["linked"]:
        assert incident(client, number)["parent_number"] == major_number
    assert major_number in messages(client, "E1004")[0]["body"]

    status = call(client, "check_service_status", service="vpn")
    assert status["state"] == "outage" and status["incidents"][0]["number"] == major_number

    late = _report_vpn(client, "c3", "E1013", "Fatima Noor")
    assert late["linked_major_incident"] == major_number
    assert incident(client, late["number"])["parent_number"] == major_number
    assert "Known issue" in call(client, "find_similar_incidents", service="vpn")["agent_hint"]


def test_rejected_proposal_declares_nothing(client):
    proposal = _storm_proposal(client)
    assert decide(client, proposal["approval_id"], approve=False).json()["status"] == "rejected"
    assert call(client, "check_service_status", service="vpn")["state"] == "operational"


def test_account_requests_are_not_outage_reports(client):
    from tests.helpers import request_action, verify

    verify(client, "c1")
    request_action(client, "c1")  # an MFA reset request filed under single sign-on
    assert client.get("/admin/storm-board").json()["services"] == []
    out = call(client, "create_incident", conversation_id="c1", summary="Okta login page won't load",
               service="sso", caller_confirmed=True)
    assert out["created"], "a request must not make a real SSO problem look like a duplicate"


def test_two_reports_are_not_a_storm(client):
    add_storm("vpn", "Chennai", 1)
    out = _report_vpn(client, "c1", "E1004", "Karthik")
    assert out["technician_alerted"] is False
