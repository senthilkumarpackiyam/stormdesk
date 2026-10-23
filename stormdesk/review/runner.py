"""Running reviews: one at a time, in the background, for every finished call.

Calls are pulled rather than pushed. Every housekeeping cycle asks ElevenLabs for the agent's recent calls
and reviews the finished ones it hasn't seen. No webhook to register, nothing breaks when the tunnel's
address changes, and a call missed while the backend was down is picked up when it comes back."""

import asyncio
import logging

from stormdesk import sessions
from stormdesk.config import settings
from stormdesk.review import store
from stormdesk.review.config import enable_tracing, review_settings
from stormdesk.review.graph import review_graph
from stormdesk.voice.client import ElevenLabs, ElevenLabsError
from stormdesk.voice.config import voice_settings
from stormdesk.voice.state import load_state

log = logging.getLogger(__name__)

FINISHED = {"done", "failed"}
_one_at_a_time = asyncio.Lock()
_background: asyncio.Task | None = None


def _elevenlabs() -> ElevenLabs:
    return ElevenLabs(voice_settings.elevenlabs_api_key)


async def review(conversation_id: str, source: str = "manual", model: str | None = None,
                 conversation: dict | None = None) -> dict:
    """Review one call and store the result. `conversation` skips the fetch (tests)."""
    model = model or review_settings.stormdesk_review_model
    async with _one_at_a_time:
        store.start(conversation_id, source, model)
        try:
            if conversation is None:
                conversation = await asyncio.to_thread(_elevenlabs().get_conversation, conversation_id)
        except (ElevenLabsError, OSError) as exc:
            store.fail(conversation_id, f"couldn't fetch the call from ElevenLabs: {exc}")
            return store.get(conversation_id)
        tracing = enable_tracing()
        config = {"run_name": f"review {conversation_id}", "tags": ["stormdesk", "post-call-review", source],
                  "metadata": {"conversation_id": conversation_id, "model": model}}
        try:
            state = await review_graph.ainvoke({"conversation": conversation, "model": model}, config)
        except Exception as exc:  # the graph isolates reviewer failures, so this is unexpected
            log.exception("review of %s crashed", conversation_id)
            store.fail(conversation_id, f"{type(exc).__name__}: {exc}")
            return store.get(conversation_id)
        result = store.finish(conversation_id, state)
        log.info("reviewed %s: %s (tracing %s)", conversation_id, result["verdict"], "on" if tracing else "off")
        return result


def _due(summary: dict) -> bool:
    if summary.get("status") not in FINISHED:
        return False  # still in progress
    if not sessions.get(summary["conversation_id"]):
        return False  # not served by this backend (e.g. another machine's test calls): no records to judge against
    existing = store.get(summary["conversation_id"])
    if not existing:
        return True
    return existing["status"] == "failed" and existing["attempts"] < settings.review_max_attempts


async def review_new_calls(limit: int = 20) -> list[str]:
    agent_id = load_state().get("agent_id")
    if not (agent_id and voice_settings.elevenlabs_api_key):
        return []
    try:
        recent = await asyncio.to_thread(_elevenlabs().list_conversations, agent_id, limit)
    except (ElevenLabsError, OSError) as exc:
        log.warning("couldn't list calls from ElevenLabs: %s", exc)
        return []
    reviewed = []
    for summary in reversed(recent):  # oldest first
        if _due(summary):
            await review(summary["conversation_id"], source="auto")
            reviewed.append(summary["conversation_id"])
    return reviewed


def kick() -> bool:
    """Start a background pass unless one is already running. Called by housekeeping."""
    global _background
    if not settings.review_poll or (_background and not _background.done()):
        return False
    _background = asyncio.get_running_loop().create_task(review_new_calls())
    return True
