"""StormDesk tool backend.

    uv run uvicorn stormdesk.main:app --reload --port 8000
    open http://localhost:8000/docs
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from stormdesk import housekeeping
from stormdesk.admin import router as admin_router
from stormdesk.seed import seed_if_empty
from stormdesk.sources.http import fetcher
from stormdesk.tools.read_tools import router as read_tools_router
from stormdesk.tools.write_tools import router as write_tools_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# One line per outgoing request to the status pages is noise; failures are still logged.
for noisy in ("httpx", "httpx2"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_if_empty()
    chores = asyncio.create_task(housekeeping.loop())
    yield
    chores.cancel()
    await fetcher.aclose()


app = FastAPI(
    title="StormDesk",
    description="Tool backend for the StormDesk IT service desk voice agent.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(read_tools_router)
app.include_router(write_tools_router)
app.include_router(admin_router)


@app.get("/health", tags=["public"])
async def health():
    """Unauthenticated, so tunnels and uptime checks can see the server is alive. Reveals nothing."""
    return {"ok": True, "service": "stormdesk"}
