"""A small client for the parts of the ElevenLabs API that StormDesk uses: secrets, tools, agents."""

import httpx

from stormdesk.voice.config import ELEVENLABS_API


class ElevenLabsError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"ElevenLabs answered {status}: {detail}")
        self.status = status
        self.detail = detail


class ElevenLabs:
    def __init__(self, api_key: str, http: httpx.Client | None = None):
        if not api_key and http is None:
            raise SystemExit("ELEVENLABS_API_KEY is empty. Add it to .env first.")
        self.http = http or httpx.Client(base_url=ELEVENLABS_API, headers={"xi-api-key": api_key}, timeout=60)

    def _call(self, method: str, path: str, **kwargs) -> dict:
        resp = self.http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise ElevenLabsError(resp.status_code, resp.text[:2000])
        return resp.json() if resp.content else {}

    def _all(self, path: str, key: str) -> list[dict]:
        items, cursor = [], None
        while True:
            page = self._call("GET", path, params={"page_size": 100, **({"cursor": cursor} if cursor else {})})
            items += page.get(key, [])
            cursor = page.get("next_cursor")
            if not page.get("has_more") or not cursor:
                return items

    # --- secrets: values the agent can send in headers without the AI ever seeing them ---

    def list_secrets(self) -> list[dict]:
        return self._call("GET", "/v1/convai/secrets").get("secrets", [])

    def create_secret(self, name: str, value: str) -> str:
        return self._call("POST", "/v1/convai/secrets", json={"type": "new", "name": name, "value": value})["secret_id"]

    def update_secret(self, secret_id: str, name: str, value: str) -> None:
        self._call("PATCH", f"/v1/convai/secrets/{secret_id}", json={"type": "update", "name": name, "value": value})

    # --- tools ---

    def list_tools(self) -> list[dict]:
        return self._all("/v1/convai/tools", "tools")

    def create_tool(self, tool_config: dict) -> str:
        return self._call("POST", "/v1/convai/tools", json={"tool_config": tool_config})["id"]

    def update_tool(self, tool_id: str, tool_config: dict) -> None:
        self._call("PATCH", f"/v1/convai/tools/{tool_id}", json={"tool_config": tool_config})

    # --- agents ---

    def find_agent(self, name: str) -> str | None:
        page = self._call("GET", "/v1/convai/agents", params={"search": name, "page_size": 30})
        return next((a["agent_id"] for a in page.get("agents", []) if a.get("name") == name), None)

    def get_agent(self, agent_id: str) -> dict:
        return self._call("GET", f"/v1/convai/agents/{agent_id}")

    def create_agent(self, payload: dict) -> str:
        return self._call("POST", "/v1/convai/agents/create", json=payload)["agent_id"]

    def update_agent(self, agent_id: str, payload: dict) -> dict:
        return self._call("PATCH", f"/v1/convai/agents/{agent_id}", json=payload)

    def get_conversation(self, conversation_id: str) -> dict:
        return self._call("GET", f"/v1/convai/conversations/{conversation_id}")

    def list_conversations(self, agent_id: str, page_size: int = 30) -> list[dict]:
        """Newest first: conversation_id, status, start_time_unix_secs, call_duration_secs, ..."""
        page = self._call("GET", "/v1/convai/conversations", params={"agent_id": agent_id, "page_size": page_size})
        return page.get("conversations", [])
