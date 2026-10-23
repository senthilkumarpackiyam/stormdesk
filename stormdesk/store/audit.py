"""Every tool call is written down: who asked what, what came back, how long it took.

The post-call reviewer (phase 5) reads this to check the agent followed the process."""

import json
import logging

from stormdesk import timeutil
from stormdesk.store.db import connect, dicts

log = logging.getLogger(__name__)


def record(tool: str, conversation_id: str | None, request: dict, response: dict, latency_ms: int) -> None:
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, conversation_id, tool, request, response, ok, latency_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    timeutil.now_iso(),
                    conversation_id,
                    tool,
                    json.dumps(request, default=str),
                    json.dumps(response, default=str),
                    int(bool(response.get("ok"))),
                    latency_ms,
                ),
            )
    except Exception:
        # Losing an audit row must never break a live call.
        log.exception("could not write audit row for %s", tool)


def recent(limit: int = 50, conversation_id: str | None = None) -> list[dict]:
    query = "SELECT * FROM audit_log"
    params: tuple = ()
    if conversation_id:
        query += " WHERE conversation_id = ?"
        params = (conversation_id,)
    with connect() as conn:
        rows = dicts(conn.execute(query + " ORDER BY id DESC LIMIT ?", (*params, limit)))
    for row in rows:
        row["request"] = json.loads(row["request"])
        row["response"] = json.loads(row["response"])
    return rows
