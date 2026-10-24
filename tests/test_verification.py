from stormdesk.store.db import connect
from tests.helpers import call, identify, latest_code, messages, verify


def test_send_requires_identified_caller(client):
    out = call(client, "send_verification_code", conversation_id="c1")
    assert out["error"] == "not_identified"


def test_code_goes_only_to_number_on_file_and_is_never_returned(client):
    identify(client, "c1")
    out = call(client, "send_verification_code", conversation_id="c1")
    assert out["sent_to"].endswith("0101")
    sms = messages(client, "E1001")[0]
    assert sms["to_address"] == "+1-555-0101"
    assert latest_code(client, "E1001") not in str(out)


def test_correct_code_verifies_and_cannot_be_replayed(client):
    verify(client, "c1")
    session = client.get("/admin/sessions/c1").json()
    assert session["verified_at"]
    replay = call(client, "check_verification_code", conversation_id="c1", code=latest_code(client, "E1001"))
    assert replay["verified"] is False


def test_spoken_code_with_spaces_is_accepted(client):
    identify(client, "c1")
    call(client, "send_verification_code", conversation_id="c1")
    code = latest_code(client, "E1001")
    out = call(client, "check_verification_code", conversation_id="c1", code=" ".join(code))
    assert out["verified"]


def test_three_wrong_codes_lock_the_call_and_alert_security(client):
    identify(client, "c1")
    call(client, "send_verification_code", conversation_id="c1")
    first = call(client, "check_verification_code", conversation_id="c1", code="000000")
    assert first["reason"] == "wrong" and "2 tries left" in first["agent_hint"]
    call(client, "check_verification_code", conversation_id="c1", code="111111")
    third = call(client, "check_verification_code", conversation_id="c1", code="222222")
    assert third["error"] == "verification_failed"

    security = [i for i in client.get("/admin/incidents").json()["incidents"] if i["category"] == "security"
                and "impersonation" in i["short_description"]]
    assert security and security[0]["employee_id"] == "E1001"
    assert "failed to verify as you" in messages(client, "E1001")[0]["body"]

    # Locked for the rest of the call, whatever the agent tries next.
    assert call(client, "create_incident", conversation_id="c1", summary="x", caller_confirmed=True)["error"] \
        == "session_locked"
    assert call(client, "lookup_employee", conversation_id="c1", employee_id="E1001",
                full_name="Sarah Jeesen")["error"] == "session_locked"


def test_asking_for_a_new_code_does_not_buy_more_guesses(client):
    identify(client, "c1")
    call(client, "send_verification_code", conversation_id="c1")
    call(client, "check_verification_code", conversation_id="c1", code="000000")
    call(client, "check_verification_code", conversation_id="c1", code="111111")
    call(client, "send_verification_code", conversation_id="c1")
    out = call(client, "check_verification_code", conversation_id="c1", code="222222")
    assert out["error"] == "verification_failed"


def test_at_most_three_codes_per_call(client):
    identify(client, "c1")
    for _ in range(3):
        assert call(client, "send_verification_code", conversation_id="c1")["ok"]
    assert call(client, "send_verification_code", conversation_id="c1")["error"] == "too_many_codes"


def test_text_messages_down(client):
    client.post("/admin/chaos", json={"flag": "sms_down", "enabled": True})
    identify(client, "c1")
    out = call(client, "send_verification_code", conversation_id="c1")
    assert out["error"] == "sms_unavailable"
    assert "Don't verify them any other way" in out["agent_hint"]


def test_malformed_code_is_not_counted_as_a_failure(client):
    identify(client, "c1")
    call(client, "send_verification_code", conversation_id="c1")
    out = call(client, "check_verification_code", conversation_id="c1", code="12345")
    assert out["reason"] == "bad_format"
    assert client.get("/admin/sessions/c1").json()["code_failures"] == 0


def test_expired_code(client):
    identify(client, "c1")
    call(client, "send_verification_code", conversation_id="c1")
    with connect() as conn:
        conn.execute("UPDATE verification_codes SET expires_at = '2000-01-01T00:00:00+00:00'")
    out = call(client, "check_verification_code", conversation_id="c1", code=latest_code(client, "E1001"))
    assert out["reason"] == "expired"
