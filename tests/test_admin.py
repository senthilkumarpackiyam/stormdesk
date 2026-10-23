from stormdesk.config import settings
from tests.helpers import decide, incident, messages, storm_proposal


def test_technician_endpoints_refuse_tunnelled_requests(client):
    assert client.get("/admin/overview").status_code == 200
    assert client.get("/admin/overview", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 403
    assert client.post("/admin/approvals/APR-0001/decision", json={"technician_id": "E1019", "approve": True},
                       headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 403


def test_admin_secret_opens_them_remotely(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_secret", "adm1n")
    tunnelled = {"X-Forwarded-For": "203.0.113.7"}
    assert client.get("/admin/overview", headers=tunnelled).status_code == 401
    assert client.get("/admin/overview", headers={**tunnelled, "X-StormDesk-Admin-Key": "adm1n"}).status_code == 200


def test_voice_agent_key_cannot_open_technician_endpoints(client, monkeypatch):
    monkeypatch.setattr(settings, "tool_secret", "t00l")
    monkeypatch.setattr(settings, "admin_secret", "adm1n")
    assert client.get("/admin/overview", headers={"X-StormDesk-Key": "t00l"}).status_code == 401


def test_health_is_public_and_says_nothing(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_secret", "adm1n")
    resp = client.get("/health", headers={"X-Forwarded-For": "203.0.113.7"})
    assert resp.status_code == 200 and resp.json() == {"ok": True, "service": "stormdesk"}


def test_overview_counts(client):
    storm_proposal(client)
    overview = client.get("/admin/overview").json()
    assert overview["pending_approvals"] == 1
    assert overview["storms_building"] == 1 and overview["major_incidents"] == 0


def test_storm_board(client):
    proposal = storm_proposal(client)
    row = client.get("/admin/storm-board").json()["services"][0]
    assert row["service_key"] == "vpn" and row["open_reports"] == 3
    assert row["proposal"] == proposal["approval_id"]
    assert row["locations"] == {"Chennai": 2, "Bengaluru": 1}


def test_resolving_a_major_incident_closes_everything_and_texts_everyone(client):
    major = decide(client, storm_proposal(client)["approval_id"]).json()["result"]["major_incident"]
    out = client.post(f"/admin/incidents/{major}/resolve",
                      json={"technician_id": "E1021", "note": "Gateway restarted"}).json()
    assert len(out["resolved_children"]) == 3 and out["notified"] == 3
    assert incident(client, major)["state"] == "resolved"
    assert all(incident(client, n)["state"] == "resolved" for n in out["resolved_children"])
    assert "is fixed" in messages(client, "E1004")[0]["body"]
    assert client.get("/admin/storm-board").json()["services"] == []


def test_resolving_needs_it_staff_and_happens_once(client):
    assert client.post("/admin/incidents/INC0010001/resolve", json={"technician_id": "E1002"}).status_code == 403
    assert client.post("/admin/incidents/INC0010001/resolve", json={"technician_id": "E1019"}).status_code == 200
    assert "has been resolved" in messages(client, "E1001")[0]["body"]
    assert client.post("/admin/incidents/INC0010001/resolve", json={"technician_id": "E1019"}).status_code == 409


def test_demo_storm_endpoint(client):
    opened = client.post("/admin/demo-storm", json={"service": "slack", "location": "London", "count": 2}).json()
    assert len(opened["opened"]) == 2
    assert client.post("/admin/demo-storm", json={"service": "slack", "location": "Remote", "count": 3}) \
        .status_code == 400  # only two people work remotely


def test_reset_needs_confirmation(client):
    assert client.post("/admin/reset", json={"confirm": False}).status_code == 400
    client.post("/admin/demo-storm", json={"service": "vpn", "location": "Chennai", "count": 2})
    assert client.post("/admin/reset", json={"confirm": True}).status_code == 200
    assert len(client.get("/admin/incidents").json()["incidents"]) == 10


def test_sessions_list_names_the_caller(client):
    storm_proposal(client)
    session = client.get("/admin/sessions").json()["sessions"][0]
    assert session["conversation_id"] == "storm-call" and session["full_name"] == "Arjun Mehta"
