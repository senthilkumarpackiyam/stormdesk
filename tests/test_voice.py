"""The voice package, offline: tool generation, the workflow's shape, the prompt, and deploy against a
fake ElevenLabs. The live agent is exercised by `python -m stormdesk.voice test`."""

import json
from collections import deque

import httpx
import pytest

from stormdesk.config import settings
from stormdesk.main import app
from stormdesk.policy import NEVER
from stormdesk.voice import deploy as deployer
from stormdesk.voice import prompts
from stormdesk.voice.agent_spec import DESKS, EDGES, build_agent
from stormdesk.voice.client import ElevenLabs
from stormdesk.voice.scenarios import ASKS_FOR_CODE, DONE, OFFERS_TO_SEND
from stormdesk.voice.tools_spec import CONVERSATION_ID_VARIABLE, build_tools

BACKEND_TOOLS = {p.removeprefix("/tools/") for p in app.openapi()["paths"] if p.startswith("/tools/")}


# --- tools ---

def test_one_elevenlabs_tool_per_backend_tool():
    tools = build_tools(app)
    assert {t["name"] for t in tools} == BACKEND_TOOLS and len(tools) == 13


def test_conversation_id_comes_from_elevenlabs_not_the_ai():
    for tool in build_tools(app):
        body = tool["api_schema"]["request_body_schema"]
        assert body["properties"]["conversation_id"] == {"type": "string", "dynamic_variable": CONVERSATION_ID_VARIABLE}
        assert "conversation_id" in body["required"], tool["name"]


def test_parameters_are_plain_elevenlabs_types():
    for tool in build_tools(app):
        for name, prop in tool["api_schema"]["request_body_schema"]["properties"].items():
            assert prop["type"] in ("string", "boolean", "integer", "number"), (tool["name"], name)
            assert "anyOf" not in prop
            if name != "conversation_id":
                assert prop["description"], (tool["name"], name)
    create = next(t for t in build_tools(app) if t["name"] == "create_incident")
    assert create["api_schema"]["request_body_schema"]["properties"]["urgency"]["enum"] == ["can_work", "slowed", "blocked"]


def test_tools_carry_the_secret_and_point_at_the_tunnel():
    tools = build_tools(app, "https://abc.ngrok-free.app/", {"secret_id": "sec_1"})
    lookup = next(t for t in tools if t["name"] == "lookup_employee")
    assert lookup["api_schema"]["url"] == "https://abc.ngrok-free.app/tools/lookup_employee"
    assert lookup["api_schema"]["request_headers"]["X-StormDesk-Key"] == {"secret_id": "sec_1"}
    assert next(t for t in tools if t["name"] == "check_approval_status")["response_timeout_secs"] > settings.approval_poll_s


# --- the workflow ---

def _agent():
    return build_agent({name: f"tool_{name}" for name in BACKEND_TOOLS})


def test_every_desk_tool_exists_in_the_backend():
    for desk in DESKS:
        assert set(desk.tools) <= BACKEND_TOOLS, desk.key


def test_workflow_shape_elevenlabs_accepts():
    workflow = _agent()["workflow"]
    nodes, edges = workflow["nodes"], workflow["edges"]
    assert nodes["start_node"]["type"] == "start"  # ElevenLabs requires this exact id
    pairs = [frozenset((e["source"], e["target"])) for e in edges.values()]
    assert len(pairs) == len(set(pairs)), "ElevenLabs allows one edge per pair of desks"
    for edge_id, edge in edges.items():
        assert edge["source"] in nodes and edge["target"] in nodes
        assert edge_id in nodes[edge["source"]]["edge_order"]


def test_every_desk_is_reachable_and_can_reach_a_person():
    workflow = _agent()["workflow"]
    forward: dict[str, set] = {}
    for edge in workflow["edges"].values():
        forward.setdefault(edge["source"], set()).add(edge["target"])
    seen, todo = {"start_node"}, deque(["start_node"])
    while todo:
        for nxt in forward.get(todo.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    assert seen == set(workflow["nodes"])
    for desk in DESKS:
        if desk.key != "escalation":
            assert "escalation" in forward.get(desk.key, set()), desk.key


def test_account_desk_cannot_be_pulled_away_mid_verification():
    """Phase 6: an impostor's pressure moved the call off the Account desk between codes (to Security, then to
    Escalation), where the code check wasn't available, so three wrong codes never locked the call."""
    assert not [e for e in EDGES if e[1] == "account" and e[2] == "security"]
    assert "NOT a security report" in next(e[4] for e in EDGES if e[2] == "security")
    to_person = next(e[4] for e in EDGES if e[1] == "account" and e[2] == "escalation")
    assert "upset" in to_person and "NOT enough" in to_person
    reachable_from_account = {e[2] for e in EDGES if e[1] == "account"}
    for desk in DESKS:
        if desk.key in reachable_from_account:
            assert "check_verification_code" in desk.tools, desk.key


def test_way_back_to_intake_is_a_backward_condition():
    back = [e for e in EDGES if e[5]]
    assert {e[2] for e in back} == {"security", "account", "outage", "fixit"}
    assert all(e[1] == "intake" for e in back)


def test_prompt_carries_every_hard_rule():
    for rule in NEVER:
        assert rule[1:] in prompts.BASE_PROMPT
    assert "end_call" in prompts.BASE_PROMPT


def test_text_mode_is_allowed_for_the_test_client():
    agent = _agent()
    assert agent["platform_settings"]["overrides"]["conversation_config_override"]["conversation"]["text_only"]
    assert "agent_tool_request" in agent["conversation_config"]["conversation"]["client_events"]


# --- deploy, against a fake ElevenLabs ---

class FakeElevenLabs:
    def __init__(self):
        self.secrets, self.tools, self.agents, self.creates = {}, {}, {}, 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        if method == "POST":
            self.creates += 1
        if path == "/v1/convai/secrets":
            if method == "GET":
                return httpx.Response(200, json={"secrets": [{"secret_id": k, "name": v["name"], "type": "stored"}
                                                             for k, v in self.secrets.items()]})
            self.secrets[f"sec_{len(self.secrets)}"] = body
            return httpx.Response(200, json={"secret_id": f"sec_{len(self.secrets) - 1}", "name": body["name"],
                                             "type": "stored"})
        if path.startswith("/v1/convai/secrets/"):
            self.secrets[path.rsplit("/", 1)[1]] = body
            return httpx.Response(200, json={})
        if path == "/v1/convai/tools":
            if method == "GET":
                return httpx.Response(200, json={"tools": [{"id": k, "tool_config": v} for k, v in self.tools.items()],
                                                 "has_more": False})
            tool_id = f"tool_{len(self.tools)}"
            self.tools[tool_id] = body["tool_config"]
            return httpx.Response(200, json={"id": tool_id})
        if path.startswith("/v1/convai/tools/"):
            self.tools[path.rsplit("/", 1)[1]] = body["tool_config"]
            return httpx.Response(200, json={})
        if path == "/v1/convai/agents":
            return httpx.Response(200, json={"agents": [{"agent_id": k, "name": v["name"]}
                                                        for k, v in self.agents.items()]})
        if path == "/v1/convai/agents/create":
            self.agents["agent_0"] = body
            return httpx.Response(200, json={"agent_id": "agent_0"})
        if path.startswith("/v1/convai/agents/"):
            self.agents[path.rsplit("/", 1)[1]] = body
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"detail": f"{method} {path}"})


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(deployer, "STATE_FILE", tmp_path / "elevenlabs.json")
    monkeypatch.setattr(deployer, "EXPORT_DIR", tmp_path / "export")
    monkeypatch.setattr(deployer, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(settings, "tool_secret", "")
    (tmp_path / ".env").write_text("ELEVENLABS_API_KEY=sk_test\n# keep me\n")
    server = FakeElevenLabs()
    client = ElevenLabs("", http=httpx.Client(base_url="https://api.elevenlabs.io",
                                              transport=httpx.MockTransport(server)))
    return server, client, tmp_path


def test_first_deploy_creates_everything(fake):
    server, client, tmp_path = fake
    state = deployer.deploy("https://abc.ngrok-free.app", client)
    assert len(server.tools) == 13 and len(server.secrets) == 1 and state["agent_id"] == "agent_0"
    agent = server.agents["agent_0"]
    intake_tools = agent["workflow"]["nodes"]["intake"]["additional_tool_ids"]
    assert all(t in server.tools for t in intake_tools)
    secret = settings.tool_secret
    assert len(secret) >= 32
    assert server.secrets["sec_0"]["value"] == secret
    env = (tmp_path / ".env").read_text()
    assert f"STORMDESK_TOOL_SECRET={secret}" in env and "# keep me" in env and "ELEVENLABS_API_KEY=sk_test" in env


def test_second_deploy_only_updates(fake):
    server, client, _ = fake
    deployer.deploy("https://abc.ngrok-free.app", client)
    creates = server.creates
    deployer.deploy("https://new-url.ngrok-free.app", client)
    assert server.creates == creates, "a redeploy must update, never duplicate"
    assert len(server.tools) == 13 and len(server.agents) == 1
    assert all(t["api_schema"]["url"].startswith("https://new-url.ngrok-free.app/") for t in server.tools.values())


def test_export_has_placeholders_never_the_secret(fake):
    _, client, tmp_path = fake
    deployer.deploy("https://abc.ngrok-free.app", client)
    exported = " ".join(p.read_text() for p in (tmp_path / "export").rglob("*.json"))
    assert settings.tool_secret not in exported
    assert "{{PUBLIC_URL}}/tools/lookup_employee" in exported and "{{tool:lookup_employee}}" in exported


def test_deploy_refuses_plain_http(fake):
    _, client, _ = fake
    with pytest.raises(SystemExit):
        deployer.deploy("http://localhost:8000", client)


# --- the scripted caller's ears ---

def test_test_caller_hears_closing_questions_only():
    assert DONE.search("is there anything else i can help you with today?")
    assert not DONE.search("close that page and don't click anything else in that email.")
    assert ASKS_FOR_CODE.search("could you read me the six digits from that text?")
    assert ASKS_FOR_CODE.search("could you read the newest text message again, slowly, one digit at a time?")
    assert not ASKS_FOR_CODE.search("i'll text a six-digit code to the mobile number on file.")
    assert OFFERS_TO_SEND.search("shall i send it now?")
