import re


def call(client, tool, **body):
    resp = client.post(f"/tools/{tool}", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def identify(client, cid, employee_id="E1001", name="Priya Raman"):
    out = call(client, "lookup_employee", employee_id=employee_id, full_name=name, conversation_id=cid)
    assert out["match"], out
    return out


def messages(client, employee_id):
    return client.get("/admin/messages", params={"employee_id": employee_id}).json()["messages"]


def latest_code(client, employee_id):
    for message in messages(client, employee_id):
        found = re.search(r"code is (\d{6})", message["body"])
        if found:
            return found.group(1)
    raise AssertionError(f"no verification code texted to {employee_id}")


def verify(client, cid, employee_id="E1001", name="Priya Raman"):
    identify(client, cid, employee_id, name)
    assert call(client, "send_verification_code", conversation_id=cid)["ok"]
    out = call(client, "check_verification_code", conversation_id=cid, code=latest_code(client, employee_id))
    assert out["verified"], out


def incident(client, number):
    return client.get(f"/admin/incidents/{number}").json()


def decide(client, approval_id, technician_id="E1019", approve=True, note=""):
    return client.post(f"/admin/approvals/{approval_id}/decision",
                       json={"technician_id": technician_id, "approve": approve, "note": note})


def storm_proposal(client):
    """Two Chennai colleagues already reported the VPN; Arjun's report makes three. Returns the proposal."""
    from stormdesk.seed import add_storm

    add_storm("vpn", "Chennai", 2)
    identify(client, "storm-call", "E1004", "Arjun Mehta")
    out = call(client, "create_incident", conversation_id="storm-call", summary="VPN won't connect", service="vpn",
               urgency="blocked", caller_confirmed=True)
    assert out["technician_alerted"], out
    return client.get("/admin/approvals", params={"status": "pending"}).json()["approvals"][0]


def request_action(client, cid, action="mfa_reset", reason="Got a new phone", **extra):
    out = call(client, "request_sensitive_action", conversation_id=cid, action=action, reason=reason,
               caller_confirmed=True, **extra)
    assert out["ok"], out
    return out
