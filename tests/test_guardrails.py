from tests.helpers import call, identify


def test_one_caller_per_call(client):
    identify(client, "c1")
    out = call(client, "lookup_employee", conversation_id="c1", employee_id="E1002", full_name="Daniel Okafor")
    assert out["error"] == "already_identified"
    assert "Daniel" not in str(out)
    assert client.get("/admin/sessions/c1").json()["employee_id"] == "E1001"


def test_cannot_read_another_employees_records(client):
    identify(client, "c1")
    for tool in ("get_caller_history", "check_device_health"):
        out = call(client, tool, conversation_id="c1", employee_id="E1002")
        assert out["error"] == "not_the_caller", tool


def test_records_need_an_identified_caller(client):
    out = call(client, "get_caller_history", conversation_id="c1", employee_id="E1001")
    assert out["error"] == "not_identified"


def test_second_failed_lookup_stops_and_points_to_the_desk(client):
    first = call(client, "lookup_employee", conversation_id="c1", employee_id="E1001", full_name="Grace Park")
    second = call(client, "lookup_employee", conversation_id="c1", employee_id="E1005", full_name="Grace Park")
    assert "Stop asking" in second["agent_hint"] and "in person" in second["agent_hint"]
    assert first["agent_hint"] != second["agent_hint"]


def test_no_hint_promises_a_live_transfer():
    """There is no live transfer on this line, so no tool may tell the agent to offer one."""
    import pathlib
    for path in pathlib.Path("stormdesk/tools").glob("*.py"):
        assert "transfer to a technician" not in path.read_text(), path


def test_terminated_account_gets_nothing(client):
    out = call(client, "lookup_employee", conversation_id="c1", employee_id="E1012", full_name="Liam O'Brien")
    assert out["account_active"] is False
    assert call(client, "create_incident", conversation_id="c1", summary="laptop", caller_confirmed=True)["error"] \
        == "not_identified"
    assert call(client, "send_verification_code", conversation_id="c1")["error"] == "not_identified"


def test_write_tools_require_a_conversation_id(client):
    assert client.post("/tools/create_incident", json={"summary": "x"}).status_code == 422


def test_remembers_earlier_calls(client):
    identify(client, "call-monday")
    identify(client, "call-tuesday")
    identify(client, "call-wednesday")
    out = call(client, "get_caller_history", conversation_id="call-wednesday", employee_id="E1001")
    assert out["previous_calls_7_days"] == 2 and out["last_call"] == "just now"
    assert "called 2 times" in out["agent_hint"]


def test_policy_is_published(client):
    policy = client.get("/admin/policy").json()
    assert any("password" in rule for rule in policy["never"])
    assert {t["tier"] for t in policy["tiers"]} == {"read", "low-risk write", "sensitive write"}
