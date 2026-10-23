"""Background chores, every 30 seconds: deliver queued tickets, expire forgotten approvals, and start
reviews of finished calls."""

import asyncio
import logging

from stormdesk import approvals, outbox, storm
from stormdesk.config import settings
from stormdesk.review import runner as reviews

log = logging.getLogger(__name__)


async def run_once() -> dict:
    delivered = outbox.flush()
    # Tickets that were queued during an outage still count towards a storm once they land.
    for service in {d["service"] for d in delivered if d["kind"] == "incident" and d["service"]}:
        await storm.check(service)
    return {"delivered": delivered, "expired_approvals": approvals.expire_stale(),
            "reviews_started": reviews.kick()}


async def loop() -> None:
    while True:
        await asyncio.sleep(settings.housekeeping_interval_s)
        try:
            result = await run_once()
            if result["delivered"] or result["expired_approvals"]:  # reviews log themselves
                log.info("housekeeping: %s", result)
        except Exception:
            log.exception("housekeeping failed; will retry next cycle")
