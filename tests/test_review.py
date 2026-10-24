"""The post-call review, offline: case file, rule checks, the graph with stand-in reviewers (no Nebius),
failure handling, storage, and technician-approved follow-up tickets."""

import asyncio
import json
import time

import pytest

from stormdesk.config import settings
from stormdesk.review import casefile, reviewers, runner
from stormdesk.review.reviewers import (ExperienceReview, FollowUp, FollowUpPlan, ProcessCheck, ProcessReview,
                                        ResolutionReview, Scorecard)
from tests.helpers import call, identify, latest_code

CID = "conv_review_test"


def turn(role, text=None, desk=None, t=0, calls=(), results=()):
    return {"role": role, "message": text, "time_in_call_secs": t,
            "agent_metadata": {"workflow_node_id": desk} if role == "agent" else None,
            "tool_calls": [{"tool_name": n, "params_as_json": json.dumps(p)} for n, p in calls],
            "tool_results": [{"tool_name": n, "result_value": json.dumps(r), "is_error": False} for n, r in results]}


def conversation(turns, ended="end_call tool was called."):
    return {"conversation_id": CID, "status": "done", "transcript": turns,
            "metadata": {"start_time_unix_secs": int(time.time()) - 300, "call_duration_secs": 42,
                         "termination_reason": ended},
            "analysis": {"call_successful": "success", "transcript_summary": "Caller reported Zoom echo."}}


def zoom_call(client, read_back=True):
    """A real call through the tools (so the audit trail exists) plus the matching ElevenLabs record."""
    identify(client, CID, "E1003", "Mei Lin Chen")
    body = dict(conversation_id=CID, summary="Echo on Zoom calls", service="zoom")
    steps = []
    if read_back:
        draft = call(client, "create_incident", **body)
        steps.append(turn("agent", calls=[("create_incident", body)], results=[("create_incident", draft)],
                          desk="fixit", t=20))
        steps.append(turn("agent", draft["read_back"], desk="fixit", t=21))
        steps.append(turn("user", "Yes, please.", t=24))
    done = call(client, "create_incident", **body, caller_confirmed=True)
    steps.append(turn("agent", calls=[("create_incident", {**body, "caller_confirmed": True})],
                      results=[("create_incident", done)], desk="fixit", t=25))
    return conversation([
        turn("agent", "Hi, you've reached the Acme Corp IT service desk.", desk="intake"),
        turn("user", "Mei Lin Chen, E 1 0 0 3.", t=3),
        turn("agent", "Thanks, Mei. What's going on?", desk="intake", t=5),
        turn("user", "There's an echo on my Zoom calls.", t=8),
        *steps,
        turn("agent", f"Logged as {done['number_spoken']}. Anything else I can help with?", desk="fixit", t=27),
        turn("user", "No, thanks.", t=30),
    ])


def stand_in(verdict="pass", failing=()):
    answers = {
        ResolutionReview: ResolutionReview(caller_need="Stop the Zoom echo", outcome="ticket_logged",
                                           caller_left_with_clear_next_step=True, evidence=["Logged as I N C"],
                                           summary="Echo reported; ticket logged."),
        ProcessReview: ProcessReview(checks=[ProcessCheck(name="identification", verdict="pass", evidence="ID given")],
                                     violations=[], social_engineering_signals=[], summary="Process followed."),
        ExperienceReview: ExperienceReview(score=5, strengths=["Clear"], issues=[], summary="Smooth."),
        FollowUpPlan: FollowUpPlan(needed=True, items=[FollowUp(action="Check Mei's headset settings",
                                                                owner="service_desk", urgency="this_week",
                                                                reason="Echo may be hardware")]),
        Scorecard: Scorecard(verdict=verdict, headline="Handled well.", resolution_score=4, process_score=5,
                             experience_score=5, flags=[], coaching=[]),
    }

    async def ask(schema, system, case, model=None):
        if schema in failing:
            raise RuntimeError("Nebius unavailable")
        return answers[schema]

    return ask


def rule(case, check_id):
    return next(c for c in case.rule_checks if c["id"] == check_id)


# --- the case file and rule checks ---

def test_case_file_joins_transcript_and_stormdesk_records(client):
    case = casefile.build(zoom_call(client))
    assert case.employee["full_name"] == "Mei Lin Chen"
    assert case.desks == ["intake", "fixit"]
    assert len(case.tickets) == 1 and case.tickets[0]["service"] == "zoom"
    text = case.text()
    assert "CALLER: Mei Lin Chen (E1003" in text and "OUTCOMES IN STORMDESK" in text
    assert "create_incident -> ok=true created=true" in text
    assert rule(case, "read_back_first")["result"] == "pass"
    assert rule(case, "identified_first")["result"] == "pass"
    assert rule(case, "ended_cleanly")["result"] == "pass"
    assert case.metrics["caller_turns"] == 4


def test_rule_catches_a_change_made_without_read_back(client):
    case = casefile.build(zoom_call(client, read_back=False))
    assert rule(case, "read_back_first")["result"] == "fail"


def test_rule_catches_asking_for_a_password(client):
    identify(client, CID, "E1003", "Mei Lin Chen")
    asked = casefile.build(conversation([turn("agent", "Could you tell me your password, please?", desk="fixit")]))
    warned = casefile.build(conversation([turn("agent", "Please don't tell me your password.", desk="security")]))
    assert rule(asked, "never_asked_password")["result"] == "fail"
    assert rule(warned, "never_asked_password")["result"] == "pass"


@pytest.mark.parametrize("sentence, asks", [
    ("could you tell me your password, please?", True),
    ("what's your current password?", True),
    ("please confirm your password.", True),
    ("can you confirm: callback requested to reset your expired password?", False),  # a read-back, found in phase 6
    ("i'll log this as: callback requested, reset expired password.", False),
    ("please use the password reset portal.", False),
    ("tell me when your password reset is done.", False),
])
def test_password_rule_tells_asking_from_mentioning(sentence, asks):
    from stormdesk.review.rules import ASKS_PASSWORD
    assert bool(ASKS_PASSWORD.search(sentence)) is asks


def test_slow_model_falls_back_to_the_backup(monkeypatch):
    import httpx
    import openai

    class FakeModel:
        def __init__(self, name=None):
            self.name = name

        def with_structured_output(self, schema, method=None):
            return self

        async def ainvoke(self, messages):
            if self.name == "slow-model":
                raise openai.APITimeoutError(request=httpx.Request("POST", "https://nebius.test"))
            return f"answer from {self.name}"

    monkeypatch.setattr(reviewers, "chat_model", FakeModel)
    monkeypatch.setattr(reviewers.review_settings, "stormdesk_review_backup_model", "backup-model")
    assert asyncio.run(reviewers.ask(ResolutionReview, "rubric", "case", "slow-model")) == "answer from backup-model"
    monkeypatch.setattr(reviewers.review_settings, "stormdesk_review_backup_model", "slow-model")
    with pytest.raises(openai.APITimeoutError):  # no different backup: the graph records the failure
        asyncio.run(reviewers.ask(ResolutionReview, "rubric", "case", "slow-model"))


def test_rule_catches_a_code_said_out_loud(client):
    identify(client, CID)
    call(client, "send_verification_code", conversation_id=CID)
    code = latest_code(client, "E1001")
    case = casefile.build(conversation([turn("agent", f"Your code is {' '.join(code)}.", desk="account")]))
    assert rule(case, "never_said_code")["result"] == "fail"
    assert code not in json.dumps(case.facts()), "codes are never stored in the review"


def test_rule_flags_verification_left_unfinished(client):
    identify(client, CID)
    call(client, "send_verification_code", conversation_id=CID)
    call(client, "check_verification_code", conversation_id=CID, code="000000")
    call(client, "check_verification_code", conversation_id=CID, code="111111")
    case = casefile.build(conversation([turn("agent", "Let me pass you to another desk.", desk="security")]))
    check = rule(case, "verification_finished")
    assert check["result"] == "warn" and "2 wrong code(s)" in check["detail"]


def test_rule_notes_when_the_caller_hung_up(client):
    case = casefile.build(conversation([turn("agent", "Hello", desk="intake")], ended="Client disconnected: 1000"))
    assert rule(case, "ended_cleanly")["result"] == "warn"


# --- the graph, storage, failures ---

def _review(conv):
    return asyncio.run(runner.review(CID, conversation=conv, model="test-model"))


def test_review_is_stored_with_every_part(client, monkeypatch):
    monkeypatch.setattr(reviewers, "ask", stand_in())
    review = _review(zoom_call(client))
    assert review["status"] == "done" and review["verdict"] == "pass" and review["employee_id"] == "E1003"
    report = review["report"]
    assert report["resolution"]["outcome"] == "ticket_logged"
    assert report["follow_up"]["items"][0]["owner"] == "service_desk"
    assert {c["id"] for c in report["rule_checks"]} >= {"read_back_first", "never_asked_password"}
    assert report["desks"] == ["intake", "fixit"]


def test_a_broken_rule_can_never_be_graded_pass(client, monkeypatch):
    monkeypatch.setattr(reviewers, "ask", stand_in(verdict="pass"))
    review = _review(zoom_call(client, read_back=False))
    assert review["verdict"] == "attention"
    assert any("Verdict lowered" in f for f in review["report"]["scorecard"]["flags"])


def test_one_reviewer_down_still_gives_a_review(client, monkeypatch):
    monkeypatch.setattr(reviewers, "ask", stand_in(failing={ProcessReview}))
    review = _review(zoom_call(client))
    assert review["status"] == "partial" and "process reviewer failed" in review["error"]
    assert review["verdict"] == "pass" and review["report"]["resolution"]["outcome"] == "ticket_logged"


def test_nebius_down_falls_back_to_the_rule_checks(client, monkeypatch):
    everything = {ResolutionReview, ProcessReview, ExperienceReview, FollowUpPlan, Scorecard}
    monkeypatch.setattr(reviewers, "ask", stand_in(failing=everything))
    review = _review(zoom_call(client, read_back=False))
    assert review["status"] == "partial"
    assert review["verdict"] == "fail"  # the rule check failed, and no AI judge to say otherwise
    assert review["headline"].startswith("Automatic review incomplete")


def test_rerunning_a_review_replaces_it(client, monkeypatch):
    monkeypatch.setattr(reviewers, "ask", stand_in(verdict="attention"))
    conv = zoom_call(client)
    _review(conv)
    monkeypatch.setattr(reviewers, "ask", stand_in(verdict="pass"))
    review = _review(conv)
    assert review["verdict"] == "pass" and review["attempts"] == 2


# --- when reviews run ---

def test_which_calls_are_due_for_review(client, monkeypatch):
    identify(client, "c-new")
    assert runner._due({"conversation_id": "c-new", "status": "done"}) is True
    assert runner._due({"conversation_id": "c-new", "status": "in-progress"}) is False
    assert runner._due({"conversation_id": "c-elsewhere", "status": "done"}) is False  # never reached our tools
    monkeypatch.setattr(reviewers, "ask", stand_in())
    _review(zoom_call(client))
    assert runner._due({"conversation_id": CID, "status": "done"}) is False  # already reviewed


def test_automatic_reviews_respect_the_switch(client):
    async def kick():
        return runner.kick()
    assert settings.review_poll is False and asyncio.run(kick()) is False


# --- the technician's side ---

def test_review_endpoints(client, monkeypatch):
    monkeypatch.setattr(reviewers, "ask", stand_in())
    _review(zoom_call(client))
    assert client.get("/admin/reviews").json()["reviews"][0]["conversation_id"] == CID
    assert client.get(f"/admin/reviews/{CID}").json()["verdict"] == "pass"
    assert client.get("/admin/reviews/conv_unknown").status_code == 404
    assert client.get("/admin/overview").json()["reviews"] == {"pass": 1}


def test_follow_up_becomes_a_ticket_only_when_a_technician_says_so(client, monkeypatch):
    monkeypatch.setattr(reviewers, "ask", stand_in())
    _review(zoom_call(client))
    url = f"/admin/reviews/{CID}/follow-ups/0"
    assert client.post(url, json={"technician_id": "E1002"}).status_code == 403  # not IT
    number = client.post(url, json={"technician_id": "E1019"}).json()["ticket"]
    ticket = client.get(f"/admin/incidents/{number}").json()
    assert ticket["ticket_type"] == "request" and ticket["channel"] == "review"
    assert "approved by Senthil Kumar" in ticket["description"]
    assert client.get(f"/admin/reviews/{CID}").json()["report"]["follow_up"]["items"][0]["ticket"] == number
    assert client.post(url, json={"technician_id": "E1019"}).status_code == 409
    assert client.post(f"/admin/reviews/{CID}/follow-ups/7", json={"technician_id": "E1019"}).status_code == 404


def test_reviewers_refuse_to_run_without_a_key(client):
    with pytest.raises(RuntimeError):
        reviewers.chat_model()
