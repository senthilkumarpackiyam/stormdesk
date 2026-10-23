"""The console's connection to the StormDesk backend.

The console only uses the HTTP admin endpoints, never the database directly, so it can run on a
different machine from the backend."""

import httpx

from stormdesk.config import settings


class BackendError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Backend:
    def __init__(self, http: httpx.Client):
        self.http = http
        self.base_url = str(http.base_url)

    @staticmethod
    def _json(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise BackendError(resp.status_code, str(detail))
        return resp.json()

    def get(self, path: str, **params) -> dict:
        return self._json(self.http.get(path, params={k: v for k, v in params.items() if v is not None}))

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._json(self.http.post(path, json=body or {}))

    def delete(self, path: str) -> dict:
        return self._json(self.http.delete(path))


# Tests plug the FastAPI TestClient in here (it is an httpx.Client).
override: httpx.Client | None = None
_shared: Backend | None = None


def connect() -> Backend:
    global _shared
    if override is not None:
        return Backend(override)
    if _shared is None:
        headers = {"X-StormDesk-Admin-Key": settings.admin_secret} if settings.admin_secret else {}
        _shared = Backend(httpx.Client(base_url=settings.backend_url, headers=headers, timeout=20))
    return _shared
