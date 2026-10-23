import functools
import logging
import secrets
import time

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field

from stormdesk.config import settings
from stormdesk.store import audit

log = logging.getLogger(__name__)

TOOL_FAILURE_HINT = (
    "That lookup failed on our side. Apologise briefly, don't retry it more than once, "
    "and carry on: offer to log a ticket so a technician can follow up."
)


class ToolRequest(BaseModel):
    conversation_id: str | None = Field(
        None, description="The current conversation id (system__conversation_id). Used for the audit trail."
    )


def require_tool_key(x_stormdesk_key: str | None = Header(default=None)) -> None:
    if settings.tool_secret and not secrets.compare_digest(x_stormdesk_key or "", settings.tool_secret):
        raise HTTPException(status_code=401, detail="Missing or wrong X-StormDesk-Key header.")


# Headers that tunnels (ngrok, Cloudflare) and reverse proxies add. Their presence means "not local".
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "forwarded", "x-real-ip", "cf-connecting-ip")


def require_admin_key(request: Request, x_stormdesk_admin_key: str | None = Header(default=None)) -> None:
    if settings.admin_secret:
        if not secrets.compare_digest(x_stormdesk_admin_key or "", settings.admin_secret):
            raise HTTPException(status_code=401, detail="Missing or wrong X-StormDesk-Admin-Key header.")
        return
    if any(header in request.headers for header in PROXY_HEADERS):
        raise HTTPException(status_code=403, detail="Technician endpoints are local-only. Set "
                                                    "STORMDESK_ADMIN_SECRET to use them through a tunnel.")


def audited(tool: str):
    """Log every call to the audit trail and turn crashes into a speakable failure.

    Tools always answer 200 with JSON: a 500 would leave the voice agent guessing mid-call.
    Keys starting with "_" go to the audit log only, never back to the agent."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(**kwargs):
            body = kwargs.get("body")
            started = time.perf_counter()
            try:
                result = await fn(**kwargs)
            except Exception:
                log.exception("tool %s crashed", tool)
                result = {"ok": False, "error": "internal_error", "agent_hint": TOOL_FAILURE_HINT}
            latency_ms = int((time.perf_counter() - started) * 1000)
            request = body.model_dump() if body is not None else {}
            audit.record(tool, request.get("conversation_id"), request, result, latency_ms)
            return {k: v for k, v in result.items() if not k.startswith("_")}

        return wrapper

    return decorator
