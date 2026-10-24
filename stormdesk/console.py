"""The technician console: one HTML5 page (stormdesk/web/) served by the backend itself.

    open http://localhost:8000/console

The page holds no data. Its script reads everything from the /admin endpoints, which keep their own
guard, and refreshes by itself every few seconds, so a request made on a live call shows up while the
caller is still on the line."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from stormdesk.config import settings
from stormdesk.tools.common import PROXY_HEADERS

WEB = Path(__file__).resolve().parent / "web"
# Only these files are served: nothing else in the folder (or above it) can be asked for by name.
ASSETS = {"app.css": "text/css", "app.js": "text/javascript", "logo.svg": "image/svg+xml"}
HEADERS = {
    "Cache-Control": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'"
    ),
}

router = APIRouter(include_in_schema=False)


def _local_or_secret(request: Request) -> None:
    """With an admin secret the page loads anywhere and asks for the key; without one it stays local."""
    if not settings.admin_secret and any(header in request.headers for header in PROXY_HEADERS):
        raise HTTPException(403, "The console is local-only. Set STORMDESK_ADMIN_SECRET to use it through a tunnel.")


@router.get("/")
async def home():
    return RedirectResponse("/console")


@router.get("/console")
async def console(request: Request):
    _local_or_secret(request)
    return FileResponse(WEB / "index.html", media_type="text/html", headers=HEADERS)


@router.get("/console/{name}")
async def asset(name: str, request: Request):
    _local_or_secret(request)
    if name not in ASSETS:
        raise HTTPException(404, "Not found")
    return FileResponse(WEB / name, media_type=ASSETS[name], headers=HEADERS)
