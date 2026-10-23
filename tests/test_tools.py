import httpx

from stormdesk.config import settings
from stormdesk.seed import add_storm
from stormdesk.sources import vendor_status
from stormdesk.sources.http import fetcher
from stormdesk.store.db import connect
from tests.conftest import SLACK_OUTAGE


def call(client, tool, **body):
    resp = client.post(f"/tools/{tool}", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- lookup_employee ---

def test_lookup_match_tolerates_speech_to_text_slips(client):
    out = call(client, "lookup_employee", employee_id="e 1 0 0 1", full_name="Priya Ramen")
    assert out["match"] and out["employee_id"] == "E1001"
    assert out["first_name"] == "Priya"
    assert out["identity_verified"] is False
    assert out["devices"][0]["os"] == "Windows 11 24H2"


def test_lookup_wrong_name_looks_exactly_like_unknown_id(client):
    wrong_name = call(client, "lookup_employee", employee_id="E1001", full_name="Grace Park")
    unknown_id = call(client, "lookup_employee", employee_id="E9999", full_name="Grace Park")
    assert wrong_name == unknown_id
    assert wrong_name["match"] is False
    assert "_reason" not in wrong_name
    assert "Priya" not in str(wrong_name)


def test_lookup_first_name_only_is_not_enough(client):
    assert call(client, "lookup_employee", employee_id="E1001", full_name="Priya")["match"] is False


def test_lookup_terminated_account(client):
    out = call(client, "lookup_employee", employee_id="E1012", full_name="Liam O Brien")
    assert out["match"] and out["account_active"] is False
    assert "devices" not in out


def test_lookup_vip_hint(client):
    out = call(client, "lookup_employee", employee_id="E1020", full_name="Olivia Bennett")
    assert out["vip"] and "VIP" in out["agent_hint"]


# --- get_caller_history ---

def test_history_points_at_open_ticket(client):
    out = call(client, "get_caller_history", employee_id="E1001")
    assert out["open"][0]["summary"].startswith("VPN disconnects")
    assert out["open"][0]["opened"] == "yesterday"
    assert out["open"][0]["number_spoken"] == "I N C 1 0 0 0 1"
    assert out["open"][0]["number_spoken"] in out["agent_hint"]


def test_history_refuses_terminated_employee(client):
    out = call(client, "get_caller_history", employee_id="E1012")
    assert out["ok"] is False


# --- check_service_status ---

def test_status_operational(client):
    out = call(client, "check_service_status", service="zoom")
    assert out["state"] == "operational" and out["demo"] is False


def test_status_live_slack_outage(client):
    fetcher.prime(vendor_status.SERVICES["slack"].url, SLACK_OUTAGE)
    out = call(client, "check_service_status", service="Slack won't load")
    assert out["state"] == "outage"
    assert "fix is rolling out" in out["summary"]
    assert "don't troubleshoot" in out["agent_hint"]


def test_status_unreachable_page_is_unknown_not_an_error(client, monkeypatch):
    fetcher.clear()
    broken = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(502)))
    monkeypatch.setattr(fetcher, "_client", broken)
    out = call(client, "check_service_status", service="jira")
    assert out["ok"] and out["state"] == "unknown"
    assert "couldn't reach" in out["summary"]


def test_feeds_down_drill_makes_status_unknown_without_crashing(client):
    client.post("/admin/chaos", json={"flag": "feeds_down", "enabled": True})
    status = call(client, "check_service_status", service="zoom")
    assert status["ok"] and status["state"] == "unknown"
    assert "carry on troubleshooting" in status["agent_hint"].lower()
    advisories = call(client, "check_security_advisories", product="vpn")
    assert advisories["error"] == "source_unavailable"
    client.post("/admin/chaos", json={"flag": "feeds_down", "enabled": False})
    assert call(client, "check_service_status", service="zoom")["state"] == "operational"


def test_status_unknown_service(client):
    out = call(client, "check_service_status", service="the coffee machine")
    assert out["ok"] is False and "Slack" in out["supported"]


def test_demo_outage_is_labelled(client):
    client.post("/admin/demo-outage", json={"service": "vpn", "title": "VPN gateway down"})
    out = call(client, "check_service_status", service="vpn")
    assert out["state"] == "outage" and out["demo"] is True
    client.delete("/admin/demo-outage/vpn")
    assert call(client, "check_service_status", service="vpn")["state"] == "operational"


def test_internal_service_status_from_major_incident(client):
    with connect() as conn:
        conn.execute(
            "INSERT INTO incidents (number, short_description, category, service, priority, state, is_major,"
            " created_at, updated_at) VALUES ('INC0099999', 'VPN gateway down', 'network', 'vpn', 1, 'in_progress',"
            " 1, '2026-10-22T10:00:00+00:00', '2026-10-22T10:00:00+00:00')"
        )
    out = call(client, "check_service_status", service="VPN")
    assert out["state"] == "outage" and out["incidents"][0]["number"] == "INC0099999"


# --- find_similar_incidents ---

def test_similar_quiet(client):
    out = call(client, "find_similar_incidents", service="vpn", location="Chennai", employee_id="E1001")
    assert out["open_reports"] == 0 and out["storm_suspected"] is False


def test_similar_detects_storm_and_excludes_caller(client):
    add_storm("vpn", "Chennai", settings.storm_threshold - 1)
    out = call(client, "find_similar_incidents", service="VPN", location="Chennai", employee_id="E1001")
    assert out["open_reports"] == settings.storm_threshold - 1
    assert out["same_location"] == out["open_reports"]
    assert out["storm_suspected"] is True
    assert "wider outage" in out["agent_hint"]


# --- search_kb ---

def test_kb_finds_the_right_article(client):
    cases = {
        "my vpn keeps dropping every few minutes": "KB0011",
        "I can't connect to the VPN from home": "KB0010",
        "I lost my phone and can't approve sign ins": "KB0020",
        "I clicked a weird link in an email": "KB0070",
        "my laptop is really slow": "KB0060",
        "printer job is stuck in the queue": "KB0051",
    }
    for query, kb_id in cases.items():
        assert call(client, "search_kb", query=query)["articles"][0]["kb_id"] == kb_id, query


def test_kb_flags_sensitive_fix(client):
    out = call(client, "search_kb", query="account locked out too many attempts")
    assert out["articles"][0]["sensitive_action"] == "account_unlock"
    assert "approval" in out["agent_hint"]


def test_kb_no_match(client):
    out = call(client, "search_kb", query="quantum flux capacitor")
    assert out["articles"] == []


# --- check_device_health ---

def test_device_out_of_support(client):
    out = call(client, "check_device_health", employee_id="E1006")
    assert out["devices"][0]["supported"] is False
    assert "Windows 10 22H2" in out["agent_hint"]


def test_device_support_ending_soon(client):
    out = call(client, "check_device_health", employee_id="E1008")
    assert out["devices"][0]["supported"] is True
    assert "2026-11-10" in out["agent_hint"]


def test_device_supported(client):
    out = call(client, "check_device_health", employee_id="E1003")
    assert "No need to mention" in out["agent_hint"]


# --- check_security_advisories ---

def test_advisories_map_vpn_to_ivanti(client):
    out = call(client, "check_security_advisories", product="the VPN")
    assert out["looked_up"] == "Ivanti Connect Secure"
    assert out["total_known_exploited"] == 2
    assert out["latest"][0]["cve"] == "CVE-2026-0001"


def test_advisories_nothing_found(client):
    out = call(client, "check_security_advisories", product="Figma")
    assert out["total_known_exploited"] == 0


# --- plumbing ---

def test_every_call_is_audited(client):
    call(client, "lookup_employee", employee_id="E1001", full_name="Priya Raman", conversation_id="conv-1")
    call(client, "search_kb", query="vpn", conversation_id="conv-1")
    entries = client.get("/admin/audit", params={"conversation_id": "conv-1"}).json()["entries"]
    assert [e["tool"] for e in entries] == ["search_kb", "lookup_employee"]
    assert all(e["latency_ms"] >= 0 for e in entries)


def test_audit_keeps_private_reason(client):
    call(client, "lookup_employee", employee_id="E1001", full_name="Grace Park", conversation_id="conv-2")
    entry = client.get("/admin/audit", params={"conversation_id": "conv-2"}).json()["entries"][0]
    assert entry["response"]["_reason"] == "name_mismatch"


def test_crash_becomes_speakable_failure(client, monkeypatch):
    from stormdesk.itsm import itsm

    def boom(*args, **kwargs):
        raise RuntimeError("database on fire")

    monkeypatch.setattr(itsm, "kb_articles", boom)
    out = call(client, "search_kb", query="vpn")
    assert out == {"ok": False, "error": "internal_error", "agent_hint": out["agent_hint"]}
    assert "Apologise" in out["agent_hint"]


def test_secret_header_enforced(client, monkeypatch):
    monkeypatch.setattr(settings, "tool_secret", "s3cret")
    assert client.post("/tools/search_kb", json={"query": "vpn"}).status_code == 401
    ok = client.post("/tools/search_kb", json={"query": "vpn"}, headers={"X-StormDesk-Key": "s3cret"})
    assert ok.status_code == 200
