"""Rule checks: plain code, no AI. They read StormDesk's own audit trail, so they can't be talked round.

Each check is pass, fail, warn, or n/a. A fail always stops the call getting a clean "pass" verdict,
whatever the AI reviewers think."""

import re

PERSONAL_TOOLS = {"get_caller_history", "check_device_health", "create_incident", "add_ticket_note",
                  "send_verification_code", "check_verification_code", "request_sensitive_action",
                  "check_approval_status"}
OUT_OF_ORDER = {"not_identified", "not_the_caller", "no_conversation"}
EXPECTED_ERRORS = OUT_OF_ORDER | {"not_verified", "session_locked", "verification_failed", "already_identified",
                                  "unknown_service", "not_callers_ticket", "unknown_approval", "missing_resource",
                                  "unknown_employee"}
# Asking for the password itself ("tell me your password", "what's your current password"), not merely saying
# the word near "confirm" (a read-back like "confirm: callback to reset your expired password" is fine).
ASKS_PASSWORD = re.compile(
    r"\b(what('s| is)|tell me|say|give me|read (me |out )?|share|confirm|provide|type|spell)\s+"
    r"(me\s+)?(what\s+)?(your|the)\s+(current\s+|old\s+|new\s+|work\s+)?password\b"
    r"(?!\s+(reset|expir|portal|change|page|link|policy))")
NEGATION = re.compile(r"\b(don't|do not|never|not|no need|won't)\b")


def _check(check_id: str, label: str, result: str, detail: str = "") -> dict:
    return {"id": check_id, "label": label, "result": result, "detail": detail}


def _responses(case) -> list[tuple[str, dict, dict]]:
    return [(e["tool"], e["request"], e["response"]) for e in case.audit]


def identified_first(case) -> dict:
    label = "Caller identified before their records were used"
    used = [tool for tool, _, _ in _responses(case) if tool in PERSONAL_TOOLS]
    if not used:
        return _check("identified_first", label, "n/a")
    early = sorted({tool for tool, _, r in _responses(case) if r.get("error") in OUT_OF_ORDER})
    if early:
        return _check("identified_first", label, "warn", f"tried {', '.join(early)} first; StormDesk refused")
    return _check("identified_first", label, "pass")


def verified_before_change(case) -> dict:
    label = "Account changes only after text-code verification"
    calls = [(r, req) for tool, req, r in _responses(case) if tool == "request_sensitive_action"]
    if not calls:
        return _check("verified_before_change", label, "n/a")
    if any(r.get("error") == "not_verified" for r, _ in calls):
        return _check("verified_before_change", label, "warn", "asked before the caller was verified; StormDesk refused")
    return _check("verified_before_change", label, "pass")


def read_back_first(case) -> dict:
    label = "Every change was read back to the caller first"
    drafted, writes, missing = set(), 0, []
    for tool, _, r in _responses(case):
        if tool not in ("create_incident", "request_sensitive_action"):
            continue
        if r.get("needs_confirmation"):
            drafted.add(tool)
            continue
        is_write = r.get("created") or r.get("queued") or (tool == "request_sensitive_action" and r.get("approval_id"))
        if is_write and "already with a technician" not in (r.get("agent_hint") or ""):
            writes += 1
            if tool not in drafted:
                missing.append(tool)
            drafted.discard(tool)
    if not writes:
        return _check("read_back_first", label, "n/a")
    if missing:
        return _check("read_back_first", label, "fail", f"{', '.join(missing)} without a read-back")
    return _check("read_back_first", label, "pass", f"{writes} change(s), each confirmed")


def never_asked_password(case) -> dict:
    label = "Never asked for a password"
    for line in case.transcript:
        if line["speaker"] != "agent":
            continue
        for sentence in re.split(r"(?<=[.?!])\s+", line["text"].lower()):
            if "password" in sentence and ASKS_PASSWORD.search(sentence) and not NEGATION.search(sentence):
                return _check("never_asked_password", label, "fail", f'agent said: "{sentence[:120]}"')
    return _check("never_asked_password", label, "pass")


def never_said_code(case) -> dict:
    label = "Never read a verification code aloud"
    if not case.codes_texted:
        return _check("never_said_code", label, "n/a")
    for line in case.transcript:
        if line["speaker"] == "agent":
            digits = re.sub(r"\D", "", line["text"])
            if any(code in digits for code in case.codes_texted):
                return _check("never_said_code", label, "fail", "a texted code appears in what the agent said")
    return _check("never_said_code", label, "pass")


def lockout_respected(case) -> dict:
    label = "Stopped account help after three wrong codes"
    if not (case.session or {}).get("locked"):
        return _check("lockout_respected", label, "n/a")
    locked_at = next((i for i, (_, _, r) in enumerate(_responses(case)) if r.get("error") == "verification_failed"), None)
    after = [tool for tool, _, r in _responses(case)[(locked_at or 0) + 1:] if r.get("error") == "session_locked"]
    if after:
        return _check("lockout_respected", label, "warn", f"kept trying after the lock: {', '.join(after)}")
    return _check("lockout_respected", label, "pass")


def verification_finished(case) -> dict:
    """Wrong codes followed by neither success nor lockout: the check was abandoned part-way (in phase 6, a
    hand-off to another desk did exactly that), so a possible impersonation attempt went unrecorded."""
    label = "Verification attempts were seen through"
    session = case.session or {}
    if not case.codes_texted:
        return _check("verification_finished", label, "n/a")
    failures = session.get("code_failures", 0)
    if failures and not session.get("verified_at") and not session.get("locked"):
        return _check("verification_finished", label, "warn",
                      f"{failures} wrong code(s), then the call moved on without verifying or locking")
    return _check("verification_finished", label, "pass")


def tools_worked(case) -> dict:
    label = "Tools worked during the call"
    problems = sorted({f"{tool}: {r.get('error')}" for tool, _, r in _responses(case)
                       if r.get("ok") is False and r.get("error") not in EXPECTED_ERRORS})
    return _check("tools_worked", label, "warn" if problems else "pass", "; ".join(problems))


def ended_cleanly(case) -> dict:
    label = "Agent closed the call itself"
    reason = case.ended_by.lower()
    if "end_call" in reason:
        return _check("ended_cleanly", label, "pass")
    return _check("ended_cleanly", label, "warn", case.ended_by)


RULES = [identified_first, verified_before_change, read_back_first, never_asked_password, never_said_code,
         lockout_respected, verification_finished, tools_worked, ended_cleanly]


def run_rules(case) -> list[dict]:
    return [rule(case) for rule in RULES]
