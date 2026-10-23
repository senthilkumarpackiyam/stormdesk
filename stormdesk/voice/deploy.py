"""Create or update everything StormDesk needs in your ElevenLabs account. Safe to run again and again.

1. The tool secret: a random key the agent sends with every tool call (X-StormDesk-Key). It's stored in
   .env for the backend and as an ElevenLabs secret for the agent, so the AI never sees it.
2. The 13 webhook tools, pointing at the public URL.
3. The agent with its workflow of six desks.

It also writes the definitions to elevenlabs/ (URL and secret replaced by placeholders) for the repo."""

import json
import secrets

from stormdesk.config import ROOT, settings
from stormdesk.main import app
from stormdesk.voice import state as state_file
from stormdesk.voice.agent_spec import build_agent
from stormdesk.voice.client import ElevenLabs
from stormdesk.voice.config import EXPORT_DIR, SECRET_NAME, STATE_FILE, voice_settings
from stormdesk.voice.tools_spec import build_tools

ENV_FILE = ROOT / ".env"


def set_env_value(key: str, value: str) -> None:
    """Set KEY=value in .env, keeping every other line exactly as it was."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def ensure_tool_secret() -> str:
    if not settings.tool_secret:
        settings.tool_secret = secrets.token_urlsafe(32)
        set_env_value("STORMDESK_TOOL_SECRET", settings.tool_secret)
    return settings.tool_secret


def load_state() -> dict:
    return state_file.load_state(STATE_FILE)


def save_state(state: dict) -> None:
    state_file.save_state(state, STATE_FILE)


def sync_secret(client: ElevenLabs, value: str) -> str:
    existing = next((s for s in client.list_secrets() if s["name"] == SECRET_NAME), None)
    if existing:
        client.update_secret(existing["secret_id"], SECRET_NAME, value)
        return existing["secret_id"]
    return client.create_secret(SECRET_NAME, value)


def sync_tools(client: ElevenLabs, tools: list[dict], known: dict[str, str]) -> dict[str, str]:
    by_name = {t["tool_config"]["name"]: t["id"] for t in client.list_tools() if "tool_config" in t}
    ids = {}
    for tool in tools:
        tool_id = known.get(tool["name"]) if known.get(tool["name"]) in by_name.values() else by_name.get(tool["name"])
        if tool_id:
            client.update_tool(tool_id, tool)
        else:
            tool_id = client.create_tool(tool)
        ids[tool["name"]] = tool_id
    return ids


def sync_agent(client: ElevenLabs, payload: dict, known_id: str | None) -> str:
    agent_id = known_id or client.find_agent(payload["name"])
    if agent_id:
        client.update_agent(agent_id, payload)
        return agent_id
    return client.create_agent(payload)


def export() -> None:
    """Write the definitions to elevenlabs/ with placeholders, for the repo and for reviewers."""
    tools = build_tools(app)
    (EXPORT_DIR / "tools").mkdir(parents=True, exist_ok=True)
    for tool in tools:
        (EXPORT_DIR / "tools" / f"{tool['name']}.json").write_text(json.dumps(tool, indent=2) + "\n")
    agent = build_agent({t["name"]: f"{{{{tool:{t['name']}}}}}" for t in tools})
    (EXPORT_DIR / "agent.json").write_text(json.dumps(agent, indent=2) + "\n")


def deploy(public_url: str, client: ElevenLabs | None = None) -> dict:
    if not public_url.startswith("https://"):
        raise SystemExit(f"The public URL must start with https:// (got {public_url!r}).")
    client = client or ElevenLabs(voice_settings.elevenlabs_api_key)
    state = load_state()
    secret_id = sync_secret(client, ensure_tool_secret())
    tool_ids = sync_tools(client, build_tools(app, public_url, {"secret_id": secret_id}), state.get("tool_ids", {}))
    agent_id = sync_agent(client, build_agent(tool_ids), state.get("agent_id"))
    state = {"agent_id": agent_id, "tool_ids": tool_ids, "secret_id": secret_id, "public_url": public_url}
    save_state(state)
    export()
    return state


def links(agent_id: str) -> dict[str, str]:
    return {
        "talk": f"https://elevenlabs.io/app/talk-to?agent_id={agent_id}",
        "dashboard": f"https://elevenlabs.io/app/agents/agents/{agent_id}",
    }
