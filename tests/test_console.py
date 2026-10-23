"""The console, driven the way a technician would: Streamlit's AppTest loads the real app, types into
fields and clicks buttons, while the app talks to the real backend (FastAPI TestClient)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from stormdesk.config import settings
from stormdesk.console import client as console_client
from tests.helpers import call, identify, latest_code, messages, request_action, storm_proposal, verify

APP = str(Path(__file__).resolve().parent.parent / "stormdesk" / "console" / "app.py")


@pytest.fixture
def console(client, monkeypatch):
    monkeypatch.setattr(console_client, "override", client)

    def open_console() -> AppTest:
        app = AppTest.from_file(APP, default_timeout=30)
        app.run()
        assert not app.exception, app.exception
        return app

    return open_console


def texts(elements) -> str:
    return " ".join(str(e.value) for e in elements)


def test_loads_with_nothing_waiting(console):
    app = console()
    assert "Nothing waiting for approval" in texts(app.success)
    assert app.selectbox(key="technician").value == "E1019"
    assert [t.label for t in app.tabs][:2] == ["🔔 Approvals", "🌩️ Storm board"]


def test_approve_from_the_console(console, client):
    verify(client, "c1")
    req = request_action(client, "c1")
    app = console()
    assert "MFA reset · Priya Raman (E1001)" in texts(app.markdown)
    app.text_input(key=f"note-{req['approval_id']}").input("Checked her badge photo")
    app.button(key=f"approve-{req['approval_id']}").click().run()
    approval = client.get(f"/admin/approvals/{req['approval_id']}").json()
    assert approval["status"] == "executed" and approval["decision_note"] == "Checked her badge photo"
    assert f"{req['approval_id']} approved." in texts(app.success)


def test_reject_from_the_console(console, client):
    verify(client, "c1")
    req = request_action(client, "c1", "account_unlock", "locked out")
    app = console()
    app.button(key=f"reject-{req['approval_id']}").click().run()
    assert client.get(f"/admin/approvals/{req['approval_id']}").json()["status"] == "rejected"


def test_own_request_cannot_be_approved_by_yourself(console, client):
    verify(client, "c1", "E1019", "Vikram Rao")
    req = request_action(client, "c1", "account_unlock", "locked out")
    app = console()
    assert app.button(key=f"approve-{req['approval_id']}").disabled
    app.selectbox(key="technician").set_value("E1021").run()
    assert not app.button(key=f"approve-{req['approval_id']}").disabled


def test_declare_and_resolve_a_major_incident(console, client):
    proposal = storm_proposal(client)
    app = console()
    assert app.get("progress")[0].proto.text.startswith("3 of 3 reports")
    app.button(key=f"approve-{proposal['approval_id']}").click().run()
    major = client.get(f"/admin/approvals/{proposal['approval_id']}").json()["result"]["major_incident"]
    app.run()
    assert f"major incident {major}" in texts(app.markdown)
    app.text_input(key=f"storm-resolve-note-{major}").input("Gateway restarted")
    app.button(key=f"storm-resolve-{major}").click().run()
    assert client.get(f"/admin/incidents/{major}").json()["state"] == "resolved"
    assert "is fixed" in messages(client, "E1004")[0]["body"]


def test_phone_shows_the_latest_code(console, client):
    identify(client, "c1")
    call(client, "send_verification_code", conversation_id="c1")
    app = console()
    code_tile = next(m for m in app.metric if m.label == "Latest verification code")
    assert code_tile.value == latest_code(client, "E1001")


def test_drill_switch(console, client):
    app = console()
    app.toggle(key="chaos-itsm_down").set_value(True).run()
    assert client.get("/admin/chaos").json()["flags"]["itsm_down"] is True
    assert "Drill on: Ticket system down" in texts(app.error)
    app.toggle(key="chaos-itsm_down").set_value(False).run()
    assert client.get("/admin/chaos").json()["flags"]["itsm_down"] is False


def test_demo_outage_and_storm_setup(console, client):
    app = console()
    app.selectbox(key="demo_service").set_value("slack")
    app.button(key="demo_start").click().run()
    assert client.get("/admin/demo-outages").json()["demo_outages"][0]["service_key"] == "slack"
    app.button(key="storm_add").click().run()
    assert client.get("/admin/storm-board").json()["services"][0]["open_reports"] == 2


def test_reset_needs_the_checkbox(console):
    app = console()
    assert app.button(key="reset").disabled
    app.checkbox(key="reset_confirm").check().run()
    assert not app.button(key="reset").disabled


def test_reviews_tab_and_follow_up_ticket(console, client, monkeypatch):
    import asyncio

    from stormdesk.review import reviewers, runner
    from tests.test_review import CID, stand_in, zoom_call

    monkeypatch.setattr(reviewers, "ask", stand_in())
    asyncio.run(runner.review(CID, conversation=zoom_call(client), model="test-model"))
    app = console()
    assert "1 call review(s) need a look" not in texts(app.warning)  # it's a pass
    assert next(m for m in app.metric if m.label == "✅ Pass").value == "1"
    app.session_state["reviews_table"] = {"selection": {"rows": [0], "columns": []}}  # a click on the first row
    app.run()
    assert "Handled well." in texts(app.markdown)
    app.button(key=f"followup-{CID}-0").click().run()
    items = client.get(f"/admin/reviews/{CID}").json()["report"]["follow_up"]["items"]
    assert items[0]["ticket"].startswith("INC")


def test_says_so_when_the_backend_is_down(monkeypatch):
    monkeypatch.setattr(console_client, "override", None)
    monkeypatch.setattr(console_client, "_shared", None)
    monkeypatch.setattr(settings, "backend_url", "http://127.0.0.1:9")
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert "Can't reach StormDesk" in texts(app.error)
