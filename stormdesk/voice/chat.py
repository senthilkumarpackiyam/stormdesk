"""Talk to the deployed agent in text, over the same WebSocket a voice call uses: real agent, real
workflow, real tools, but no audio and no voice minutes. Used by `voice chat` (you type) and
`voice test` (scripted callers)."""

import asyncio
import json
import time
from dataclasses import dataclass, field

from websockets.asyncio.client import connect

WS_URL = "wss://api.elevenlabs.io/v1/convai/conversation?agent_id={agent_id}"
QUIET_AFTER_COMPLETE_S = 2.5  # the agent may speak again right after a tool returns
QUIET_FALLBACK_S = 6.0  # if a "turn complete" event never comes


@dataclass
class Line:
    speaker: str  # agent | caller | tool
    text: str


@dataclass
class TextCall:
    agent_id: str
    conversation_id: str | None = None
    transcript: list[Line] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    ended: bool = False

    async def __aenter__(self) -> "TextCall":
        self.ws = await connect(WS_URL.format(agent_id=self.agent_id), max_size=None, open_timeout=30)
        await self.ws.send(json.dumps({
            "type": "conversation_initiation_client_data",
            "conversation_config_override": {"conversation": {"text_only": True}},
        }))
        self.events: asyncio.Queue = asyncio.Queue()
        self.reader = asyncio.create_task(self._read())
        return self

    async def __aexit__(self, *exc) -> None:
        self.reader.cancel()
        await self.ws.close()

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await self.ws.send(json.dumps({"type": "pong", "event_id": msg["ping_event"]["event_id"]}))
                    continue
                if msg.get("type") == "conversation_initiation_metadata":
                    self.conversation_id = msg["conversation_initiation_metadata_event"]["conversation_id"]
                await self.events.put(msg)
        finally:
            await self.events.put({"type": "_closed"})

    async def agent_turn(self, timeout: float = 90) -> list[str]:
        """The agent's messages until its turn is over: turn complete, no tool still running, then quiet."""
        texts, running, complete = [], 0, False
        last_event = time.monotonic()
        deadline = last_event + timeout
        while True:
            quiet = QUIET_AFTER_COMPLETE_S if complete else QUIET_FALLBACK_S
            wait = quiet if (texts and running == 0) else max(0.1, deadline - time.monotonic())
            try:
                msg = await asyncio.wait_for(self.events.get(), wait)
            except TimeoutError:
                if texts and running == 0:
                    return texts
                raise TimeoutError(f"the agent didn't finish its turn within {timeout:.0f} s") from None
            last_event = time.monotonic()
            kind = msg.get("type")
            if kind == "agent_response":
                text = msg["agent_response_event"]["agent_response"]
                texts.append(text)
                self.transcript.append(Line("agent", text))
                complete = False
            elif kind == "agent_response_complete":
                complete = True
            elif kind == "agent_tool_request":
                running += 1
                name = (msg.get("agent_tool_request") or {}).get("tool_name", "?")
                self.tools_called.append(name)
            elif kind == "agent_tool_response":
                running = max(0, running - 1)
                info = msg.get("agent_tool_response") or {}
                if not self.tools_called or info.get("tool_name") not in self.tools_called[-3:]:
                    self.tools_called.append(info.get("tool_name", "?"))
                self.transcript.append(Line("tool", f"{info.get('tool_name')} {'error' if info.get('is_error') else 'ok'}"))
            elif kind == "_closed":
                self.ended = True
                return texts

    async def say(self, text: str) -> list[str]:
        self.transcript.append(Line("caller", text))
        await self.ws.send(json.dumps({"type": "user_message", "text": text}))
        return await self.agent_turn()


async def interactive(agent_id: str) -> None:
    async with TextCall(agent_id) as call:
        for text in await call.agent_turn():
            print(f"Storm: {text}")
        print(f"(conversation {call.conversation_id}; type /quit to hang up)")
        while not call.ended:
            line = (await asyncio.to_thread(input, "you> ")).strip()
            if line in ("/quit", "/exit"):
                break
            if not line:
                continue
            for text in await call.say(line):
                print(f"Storm: {text}")
        if call.ended:
            print("(Storm ended the call)")
