"""The evaluation report's arithmetic, offline: the numbers that go into the docs must be right."""

import json

from stormdesk.store.db import connect
from stormdesk.voice import report
from stormdesk.voice.chat import Line
from stormdesk.voice.scenarios import SCENARIOS, Result
from tests.helpers import decide, request_action, verify


def _result(name, cid, checks, duration=60, verdict=None, coaching=()):
    review = None
    if verdict:
        review = {"verdict": verdict, "headline": "h", "status": "done",
                  "report": {"scorecard": {"resolution_score": 5, "process_score": 4, "experience_score": 3,
                                           "coaching": list(coaching)},
                             "experience": {"issues": ["repeated a question"]}}}
    scenario = next(s for s in SCENARIOS if s.name == name)
    return Result(scenario, conversation_id=cid, checks=checks, duration_s=duration, review=review,
                  transcript=[Line("agent", "Hello"), Line("caller", "Hi")])


def test_summary_counts(client):
    results = [_result("lost_phone", "c1", [("a", True), ("b", True)], 50, "pass", ["say it once"]),
               _result("impostor", "c2", [("a", True), ("b", False)], 300, "attention")]
    summary = report.summarise(client, results)
    assert summary["scenarios_passed"] == 1 and summary["checks_passed"] == 3 and summary["checks_total"] == 4
    assert summary["within_target"] == 1 and summary["longest_call_s"] == 300
    assert summary["review_verdicts"] == {"pass": 1, "attention": 1, "fail": 0}
    assert summary["avg_experience"] == 3 and summary["coaching"] == ["say it once"]
    assert summary["unsafe_account_changes"] == 0


def test_unsafe_change_is_counted(client):
    verify(client, "c-unsafe")
    req = request_action(client, "c-unsafe")
    decide(client, req["approval_id"])
    results = [_result("lost_phone", "c-unsafe", [("a", True)])]
    assert report.unsafe_changes(client, results) == 0
    with connect() as conn:  # pretend verification never happened: the report must notice
        conn.execute("UPDATE sessions SET verified_at = NULL WHERE conversation_id = 'c-unsafe'")
    assert report.unsafe_changes(client, results) == 1


def test_report_files(client, tmp_path):
    results = [_result("lost_phone", "c1", [("verified", True)], 40, "pass"),
               _result("phishing", "c2", [("security ticket", False)], 70, "attention")]
    path = tmp_path / "evals" / "run.md"
    report.write(path, "test run", results, report.summarise(client, results))
    text = path.read_text()
    assert "# StormDesk evaluation: test run" in text and "**1/2**" in text
    assert "**phishing**: security ticket" in text  # the failed check is listed
    data = json.loads(path.with_suffix(".json").read_text())
    assert data["summary"]["scenarios"] == 2 and data["results"][0]["transcript"][0]["text"] == "Hello"


def test_every_scenario_has_checks_and_cleans_up_its_drill():
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names)) == 15
    for scenario in SCENARIOS:
        assert scenario.checks, scenario.name
        if scenario.setup and "chaos" in getattr(scenario.setup, "__qualname__", ""):
            assert scenario.teardown, f"{scenario.name} turns a drill on but never off"
