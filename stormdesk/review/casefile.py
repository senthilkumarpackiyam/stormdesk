"""The case file: everything the reviewers look at, gathered in one place.

Two sources, on purpose:
- ElevenLabs' record of the call: what was said, by which desk, and every tool call it made.
- StormDesk's own records (the ground truth): the audit trail, the session, tickets and approvals.
The reviewers read the transcript; the rule checks trust only StormDesk's records."""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from stormdesk import sessions
from stormdesk.approvals import store as approval_store
from stormdesk.itsm import itsm
from stormdesk.review.rules import run_rules
from stormdesk.store import audit
from stormdesk.store.db import connect, dicts

# Fields of a tool result worth showing a reviewer; the rest is noise.
RESULT_FIELDS = ("ok", "error", "match", "account_active", "identity_verified", "verified", "reason", "state",
                 "created", "needs_confirmation", "queued", "reference", "number", "priority", "duplicate_of",
                 "linked_major_incident", "technician_alerted", "storm_suspected", "open_reports", "approval_id",
                 "status", "already_verified", "sent_to")


def _short(value, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _result_summary(raw: str | None) -> str:
    try:
        data = json.loads(raw or "")
    except (TypeError, ValueError):
        return _short(raw or "")
    if not isinstance(data, dict):
        return _short(data)
    parts = [f"{k}={_short(data[k], 60)}" for k in RESULT_FIELDS if k in data and data[k] not in (None, "", [])]
    if data.get("articles"):
        parts.append("articles=" + ",".join(a.get("kb_id", "?") for a in data["articles"]))
    if data.get("agent_hint"):
        parts.append(f'hint="{_short(data["agent_hint"], 200)}"')
    return " ".join(parts)


def _params(raw: str | None) -> str:
    try:
        params = json.loads(raw or "{}")
    except ValueError:
        return _short(raw or "")
    return ", ".join(f"{k}={_short(v, 50)}" for k, v in params.items() if k != "conversation_id")


@dataclass
class CaseFile:
    conversation_id: str
    started_at: str | None
    duration_s: int | None
    ended_by: str
    desks: list[str]
    transcript: list[dict]
    employee: dict | None
    session: dict | None
    audit: list[dict]
    tickets: list[dict]
    approvals: list[dict]
    codes_texted: list[str]
    elevenlabs_opinion: dict
    rule_checks: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def text(self) -> str:
        """The case file as reviewers read it."""
        who = (f"{self.employee['full_name']} ({self.employee['employee_id']}, {self.employee['department']}, "
               f"{self.employee['location']}{', VIP' if self.employee['vip'] else ''})" if self.employee
               else "not identified")
        session = self.session or {}
        lines = [
            f"CALL {self.conversation_id} · {self.duration_s or '?'} s · ended by: {self.ended_by}",
            f"DESKS VISITED: {' -> '.join(self.desks) or 'unknown'}",
            f"CALLER: {who}",
            f"VERIFICATION: {'verified by text code' if session.get('verified_at') else 'not verified'}"
            f"{' · LOCKED after failed codes' if session.get('locked') else ''}"
            f" · wrong IDs/names: {session.get('lookup_failures', 0)} · wrong codes: {session.get('code_failures', 0)}",
            "",
            "TRANSCRIPT (tool lines show what the agent's tools did and the instruction, 'hint', each returned)",
        ]
        for line in self.transcript:
            where = f" [{line['desk']}]" if line.get("desk") else ""
            lines.append(f"  {line['t']:>4}s {line['speaker']}{where}: {line['text']}")
        lines += ["", "OUTCOMES IN STORMDESK (ground truth)"]
        lines += [f"  ticket {t['number']}: {t['short_description']} · {t['ticket_type']} · {t['category']} · "
                  f"P{t['priority']} · {t['state']}" + (f" · linked to {t['parent_number']}" if t["parent_number"] else "")
                  for t in self.tickets] or ["  no tickets"]
        lines += [f"  approval {a['approval_id']}: {a['kind']} · {a['status']}"
                  + (f" · decided by {a['decided_by']}" if a["decided_by"] else "") for a in self.approvals]
        lines += ["", "AUTOMATIC RULE CHECKS (from StormDesk's records)"]
        lines += [f"  [{c['result'].upper()}] {c['label']}" + (f": {c['detail']}" if c["detail"] else "")
                  for c in self.rule_checks]
        return "\n".join(lines)

    def facts(self) -> dict:
        data = asdict(self)
        data.pop("audit")
        data.pop("codes_texted")  # never store or show codes in the review
        return data


def _iso(unix: int | None) -> str | None:
    return datetime.fromtimestamp(unix, UTC).isoformat(timespec="seconds") if unix else None


def _codes_texted(employee_id: str | None, since: str | None) -> list[str]:
    if not employee_id:
        return []
    with connect() as conn:
        rows = dicts(conn.execute(
            "SELECT body FROM messages WHERE employee_id = ? AND created_at >= ? AND body LIKE '%code is%'",
            (employee_id, since or "0000"),
        ))
    return [word.strip(".") for row in rows for word in row["body"].split() if word.strip(".").isdigit()
            and len(word.strip(".")) == 6]


def build(conversation: dict) -> CaseFile:
    cid = conversation["conversation_id"]
    metadata = conversation.get("metadata") or {}
    started_at = _iso(metadata.get("start_time_unix_secs"))

    transcript, desks = [], []
    for turn in conversation.get("transcript") or []:
        t = turn.get("time_in_call_secs") or 0
        desk = (turn.get("agent_metadata") or {}).get("workflow_node_id")
        if turn.get("role") == "agent" and desk and (not desks or desks[-1] != desk):
            desks.append(desk)
        for call in turn.get("tool_calls") or []:
            transcript.append({"t": t, "speaker": "tool call", "desk": desk,
                               "text": f"{call.get('tool_name')}({_params(call.get('params_as_json'))})"})
        for result in turn.get("tool_results") or []:
            transcript.append({"t": t, "speaker": "tool result", "desk": desk,
                               "text": f"{result.get('tool_name')} -> {_result_summary(result.get('result_value'))}"})
        if turn.get("message"):
            speaker = "agent" if turn.get("role") == "agent" else "caller"
            transcript.append({"t": t, "speaker": speaker, "desk": desk if speaker == "agent" else None,
                               "text": turn["message"]})

    session = sessions.get(cid)
    employee = itsm.get_employee(session["employee_id"]) if session and session.get("employee_id") else None
    with connect() as conn:
        tickets = dicts(conn.execute("SELECT * FROM incidents WHERE conversation_id = ? ORDER BY created_at", (cid,)))
    approvals = [a for a in approval_store.list_approvals(limit=500) if a["conversation_id"] == cid]
    analysis = conversation.get("analysis") or {}

    case = CaseFile(
        conversation_id=cid,
        started_at=started_at,
        duration_s=metadata.get("call_duration_secs"),
        ended_by=metadata.get("termination_reason") or "unknown",
        desks=desks,
        transcript=transcript,
        employee={k: employee[k] for k in ("employee_id", "full_name", "department", "location", "vip")}
        if employee else None,
        session=session,
        audit=list(reversed(audit.recent(500, cid))),
        tickets=tickets,
        approvals=approvals,
        codes_texted=_codes_texted(employee["employee_id"] if employee else None, started_at),
        elevenlabs_opinion={"call_successful": analysis.get("call_successful"),
                            "summary": analysis.get("transcript_summary")},
    )
    case.rule_checks = run_rules(case)
    case.metrics = {
        "duration_s": case.duration_s,
        "caller_turns": sum(1 for line in transcript if line["speaker"] == "caller"),
        "agent_turns": sum(1 for line in transcript if line["speaker"] == "agent"),
        "tool_calls": sum(1 for line in transcript if line["speaker"] == "tool call"),
        "desks": len(desks),
    }
    return case
