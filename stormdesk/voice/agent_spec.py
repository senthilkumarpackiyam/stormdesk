"""The StormDesk agent: one ElevenLabs agent whose workflow is a team of six desks (sub-agents).

    start -> Intake -> Outage desk | Fix-it desk | Account desk | Security desk | Escalation desk

Each desk adds its own playbook and tools to the shared rulebook. The call moves between desks when an
edge's condition becomes true; ElevenLabs judges the conditions after each turn. The whole call stays one
conversation, so the backend's per-call session (who the caller is, whether they're verified) carries over."""

from dataclasses import dataclass

from stormdesk.voice import prompts
from stormdesk.voice.config import voice_settings


@dataclass(frozen=True)
class Desk:
    key: str
    label: str
    prompt: str
    tools: tuple[str, ...]
    position: tuple[int, int]


DESKS = [
    Desk("intake", "Intake", prompts.INTAKE,
         ("lookup_employee", "get_caller_history", "check_service_status", "find_similar_incidents"), (0, 200)),
    Desk("outage", "Outage desk", prompts.OUTAGE,
         ("check_service_status", "find_similar_incidents", "create_incident", "add_ticket_note"), (-750, 450)),
    Desk("fixit", "Fix-it desk", prompts.FIX_IT,
         ("search_kb", "check_device_health", "check_service_status", "get_caller_history", "create_incident",
          "add_ticket_note"), (-250, 450)),
    Desk("account", "Account desk", prompts.ACCOUNT,
         ("search_kb", "send_verification_code", "check_verification_code", "request_sensitive_action",
          "check_approval_status"), (250, 450)),
    Desk("security", "Security desk", prompts.SECURITY,
         ("check_security_advisories", "search_kb", "check_device_health", "create_incident"), (750, 450)),
    # check_verification_code too: if a call arrives here mid-verification, the next code is still checked and
    # three wrong ones still lock the call and alert security (a hand-off can't lose the lockout).
    Desk("escalation", "Escalation desk", prompts.ESCALATION,
         ("get_caller_history", "create_incident", "check_verification_code"), (0, 750)),
]

IDENTIFIED = "The caller has been identified (lookup_employee returned match true)"
NEEDS_PERSON = ("The caller asks to speak to a person, or is clearly upset or frustrated, or lookup_employee "
                "has failed twice, or the account is not active, or verification failed three times")
SECURITY_WORRY = ("reports something suspicious that happened to them or their device: a suspicious or phishing "
                  "email or text, a link they clicked, a password typed into an unfamiliar page, unexpected login or "
                  "MFA prompts, certificate warnings, strange pop-ups, or settings changing by themselves. A caller "
                  "being pushy, urgent, or failing verification is NOT a security report")
ACCOUNT_CHANGE = ("needs an account change: a lost, new or replaced phone, MFA or sign-in approval problems, a "
                  "locked account, a forgotten or expired password, or access to an application or group")
NEW_PROBLEM = "This desk's work is finished and the caller now raises a different, new problem"
# Pressure ("I'm the VP, I'm at the airport") is the impostor's tool, so on the Account desk a caller sounding upset
# must never move the call away mid-verification. Found in phase 6: it did, and the lockout was lost.
ACCOUNT_NEEDS_PERSON = ("The caller explicitly asks to speak to a person, or check_verification_code reported that "
                        "verification failed (the call is locked), or the account change is finished and the caller "
                        "needs a person for something else. A caller sounding upset, urgent or pushy is NOT enough "
                        "while verification is in progress")

# (id, source, target, label, condition, condition for going back target -> source or None).
# ElevenLabs allows one edge per pair of desks, so "back to Intake" is the backward condition of the same edge.
# Edges leaving a desk are tried in this order.
EDGES = [
    ("intake_escalation", "intake", "escalation", "Needs a person", NEEDS_PERSON, None),
    ("intake_security", "intake", "security", "Security worry", f"{IDENTIFIED} and {SECURITY_WORRY}.", NEW_PROBLEM),
    ("intake_account", "intake", "account", "Account change", f"{IDENTIFIED} and {ACCOUNT_CHANGE}.", NEW_PROBLEM),
    ("intake_outage", "intake", "outage", "Known outage",
     f"{IDENTIFIED} and their problem is with a service that has a known problem: check_service_status reported "
     "an outage or degraded state, or find_similar_incidents reported a major incident, a suspected storm, or a "
     "technician already reviewing it.", NEW_PROBLEM),
    ("intake_fixit", "intake", "fixit", "Needs a fix",
     f"{IDENTIFIED}, they have described a technical problem, and it is not a known outage (no outage, major "
     "incident or storm was found), not an account change, and not a security concern.", NEW_PROBLEM),
    ("fixit_escalation", "fixit", "escalation", "Needs a person", NEEDS_PERSON, None),
    ("fixit_security", "fixit", "security", "Security worry", f"The caller {SECURITY_WORRY}.", None),
    ("fixit_account", "fixit", "account", "Needs account change",
     "The fix needs an account change (search_kb said it needs mfa_reset, account_unlock or access_grant), or "
     "the caller now asks for one.", None),
    ("outage_escalation", "outage", "escalation", "Needs a person", NEEDS_PERSON, None),
    ("account_escalation", "account", "escalation", "Needs a person", ACCOUNT_NEEDS_PERSON, None),
    # No Account -> Security edge: in phase 6 a pushy impostor was moved to Security mid-verification, where the
    # code check doesn't exist, so the lockout never happened. A genuine security report goes back via Intake.
    ("security_escalation", "security", "escalation", "Needs a person", NEEDS_PERSON, None),
]

# Words the speech recogniser should expect: product names and the practice company's people.
ASR_KEYWORDS = [
    "StormDesk", "Acme", "VPN", "Ivanti", "Okta", "MFA", "Slack", "Zoom", "Gmail", "Jira", "Confluence", "GitHub",
    "Figma", "Notion", "Wi-Fi", "phishing", "Jeesen", "Okafor", "Karthik", "Senthil", "Alvarez", "Mensah", "Schmidt",
    "Shankar", "Noor", "Iyer", "Dubois", "Fischer",
]

# Events sent to clients: the voice defaults plus tool and turn events, which the text test client reads.
CLIENT_EVENTS = [
    "audio", "interruption", "user_transcript", "agent_response", "agent_response_correction",
    "agent_tool_request", "agent_tool_response", "agent_response_complete",
]


def workflow(tool_ids: dict[str, str]) -> dict:
    nodes: dict[str, dict] = {"start_node": {"type": "start", "position": {"x": 0, "y": 0},
                                        "edge_order": ["start_intake"]}}
    edges: dict[str, dict] = {"start_intake": {"source": "start_node", "target": "intake",
                                               "forward_condition": {"type": "unconditional"}}}
    for desk in DESKS:
        nodes[desk.key] = {
            "type": "override_agent",
            "label": desk.label,
            "additional_prompt": desk.prompt,
            "additional_tool_ids": [tool_ids[name] for name in desk.tools],
            "position": {"x": desk.position[0], "y": desk.position[1]},
            "edge_order": [edge_id for edge_id, source, *_ in EDGES if source == desk.key],
        }
    for edge_id, source, target, label, condition, back in EDGES:
        edges[edge_id] = {"source": source, "target": target,
                          "forward_condition": {"type": "llm", "label": label, "condition": condition}}
        if back:
            edges[edge_id]["backward_condition"] = {"type": "llm", "label": "New problem", "condition": back}
    return {"nodes": nodes, "edges": edges, "prevent_subagent_loops": False}


def build_agent(tool_ids: dict[str, str]) -> dict:
    """The full create/update payload. `tool_ids` maps tool name -> ElevenLabs tool id."""
    return {
        "name": voice_settings.stormdesk_agent_name,
        "tags": ["stormdesk", "it-service-desk"],
        "conversation_config": {
            "agent": {
                "first_message": prompts.FIRST_MESSAGE,
                "language": "en",
                "prompt": {
                    "prompt": prompts.BASE_PROMPT,
                    "llm": voice_settings.stormdesk_llm,
                    "temperature": 0.2,
                    "tool_ids": [],
                    "built_in_tools": {
                        "end_call": {
                            "type": "system", "name": "end_call",
                            "description": "End the call once the caller has nothing else and you've said goodbye.",
                            "params": {"system_tool_type": "end_call"},
                        },
                    },
                },
            },
            "tts": {"model_id": voice_settings.stormdesk_tts_model, "voice_id": voice_settings.stormdesk_voice_id},
            "asr": {"keywords": ASR_KEYWORDS},
            "conversation": {"client_events": CLIENT_EVENTS},
        },
        # Lets the test client hold text-only conversations (no audio, no voice minutes).
        "platform_settings": {"overrides": {"conversation_config_override": {"conversation": {"text_only": True}}}},
        "workflow": workflow(tool_ids),
    }
