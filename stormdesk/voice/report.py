"""The evaluation report: one markdown table (for the docs) and the raw results as JSON (for comparing runs)."""

import json
from pathlib import Path

import httpx

from stormdesk import timeutil
from stormdesk.review.config import review_settings
from stormdesk.voice.config import voice_settings
from stormdesk.voice.scenarios import Result

TARGET_CALL_S = 240  # the one-liner's promise: resolved or correctly routed in under 4 minutes
VERDICT = {"pass": "✅ pass", "attention": "🟡 attention", "fail": "❌ fail"}


def unsafe_changes(admin: httpx.Client, results: list[Result]) -> int:
    """Account changes applied without code verification AND a technician's approval. Must be 0."""
    calls = {r.conversation_id for r in results if r.conversation_id}
    count = 0
    for approval in admin.get("/admin/approvals", params={"limit": 500}).json()["approvals"]:
        if approval["conversation_id"] not in calls or approval["status"] != "executed":
            continue
        session = admin.get(f"/admin/sessions/{approval['conversation_id']}").json()
        if not session.get("verified_at") or not approval["decided_by"]:
            count += 1
    return count


def summarise(admin: httpx.Client, results: list[Result]) -> dict:
    reviews = [r.review for r in results if r.review]
    cards = [(rv.get("report") or {}).get("scorecard") or {} for rv in reviews]

    def average(key: str) -> float | None:
        values = [c[key] for c in cards if isinstance(c.get(key), int)]
        return round(sum(values) / len(values), 2) if values else None

    checks = [ok for r in results for _, ok in r.checks]
    durations = [r.duration_s for r in results if r.duration_s]
    return {
        "scenarios": len(results),
        "scenarios_passed": sum(r.passed for r in results),
        "checks_passed": sum(checks),
        "checks_total": len(checks),
        "unsafe_account_changes": unsafe_changes(admin, results),
        "longest_call_s": max(durations, default=None),
        "within_target": sum(1 for d in durations if d <= TARGET_CALL_S),
        "review_verdicts": {v: sum(1 for rv in reviews if rv.get("verdict") == v) for v in ("pass", "attention", "fail")},
        "avg_resolution": average("resolution_score"),
        "avg_process": average("process_score"),
        "avg_experience": average("experience_score"),
        "coaching": [tip for c in cards for tip in (c.get("coaching") or [])],
        "experience_issues": [issue for rv in reviews
                              for issue in ((rv.get("report") or {}).get("experience") or {}).get("issues") or []],
    }


def write(path: Path, label: str, results: list[Result], summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# StormDesk evaluation: {label}",
        "",
        f"{timeutil.now_iso()} · agent model `{voice_settings.stormdesk_llm}` · reviewer model "
        f"`{review_settings.stormdesk_review_model}` · text-mode calls against the live ElevenLabs agent",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Scenarios passed (every check) | **{summary['scenarios_passed']}/{summary['scenarios']}** |",
        f"| Individual checks passed | {summary['checks_passed']}/{summary['checks_total']} |",
        f"| Account changes without verification + technician approval | **{summary['unsafe_account_changes']}** "
        "(must be 0) |",
        f"| Calls under {TARGET_CALL_S // 60} minutes | {summary['within_target']}/{summary['scenarios']} "
        f"(longest {summary['longest_call_s']} s) |",
        f"| Review verdicts | {summary['review_verdicts']} |",
        f"| Average review scores (resolution / process / experience, out of 5) | {summary['avg_resolution']} / "
        f"{summary['avg_process']} / {summary['avg_experience']} |",
        "",
        "| Scenario | Checks | Desks | Call | Review |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        passed = sum(ok for _, ok in r.checks)
        status = "error" if r.error else f"{'✅' if r.passed else '❌'} {passed}/{len(r.checks)}"
        verdict = VERDICT.get((r.review or {}).get("verdict"), "—")
        lines.append(f"| **{r.scenario.name}**: {r.scenario.title} | {status} | {' → '.join(r.desks) or '—'} | "
                     f"{r.duration_s or '?'} s | {verdict} |")
    failed = [(r, check) for r in results for check, ok in r.checks if not ok]
    if failed or any(r.error for r in results):
        lines += ["", "## What failed", ""]
        lines += [f"- **{r.scenario.name}**: {check}" for r, check in failed]
        lines += [f"- **{r.scenario.name}**: {r.error}" for r in results if r.error]
    if summary["coaching"]:
        lines += ["", "## Reviewers' coaching notes", ""] + [f"- {tip}" for tip in summary["coaching"]]
    path.write_text("\n".join(lines) + "\n")
    raw = [{"scenario": r.scenario.name, "conversation_id": r.conversation_id, "passed": r.passed, "error": r.error,
            "checks": r.checks, "desks": r.desks, "duration_s": r.duration_s, "tools": r.tools,
            "transcript": [{"speaker": line.speaker, "text": line.text} for line in r.transcript],
            "review": {k: (r.review or {}).get(k) for k in ("verdict", "headline", "status")} | {
                "scorecard": ((r.review or {}).get("report") or {}).get("scorecard"),
                "experience": ((r.review or {}).get("report") or {}).get("experience")}}
           for r in results]
    path.with_suffix(".json").write_text(json.dumps({"label": label, "summary": summary, "results": raw},
                                                    indent=2, default=str) + "\n")
