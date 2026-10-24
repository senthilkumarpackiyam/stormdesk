"""The HTML5 console: served by the backend, local-only unless there's an admin secret, and its script
never puts server data into the page unescaped. (Its screens were checked by hand in Chrome.)"""

import re
from pathlib import Path

from stormdesk.config import settings

WEB = Path(__file__).resolve().parent.parent / "stormdesk" / "web"
TUNNEL = {"X-Forwarded-For": "203.0.113.7"}


def test_console_page_and_its_files(client):
    page = client.get("/console")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert '<script src="/console/app.js"' in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    for name, kind in (("app.js", "text/javascript"), ("app.css", "text/css"), ("logo.svg", "image/svg+xml")):
        resp = client.get(f"/console/{name}")
        assert resp.status_code == 200 and resp.headers["content-type"].startswith(kind), name


def test_home_opens_the_console(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307) and resp.headers["location"] == "/console"


def test_only_the_listed_files_are_served(client):
    assert client.get("/console/index.html").status_code == 404
    assert client.get("/console/..%2Fconsole.py").status_code == 404
    assert client.get("/console/%2E%2E%2F%2E%2E%2F.env").status_code == 404


def test_console_is_local_only_without_an_admin_secret(client):
    assert client.get("/console", headers=TUNNEL).status_code == 403
    assert client.get("/console/app.js", headers=TUNNEL).status_code == 403
    assert client.get("/admin/overview", headers=TUNNEL).status_code == 403


def test_with_a_secret_the_page_loads_but_data_needs_the_key(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_secret", "s3cret-for-tests")
    assert client.get("/console", headers=TUNNEL).status_code == 200  # the page itself holds no data
    assert client.get("/admin/overview", headers=TUNNEL).status_code == 401
    ok = client.get("/admin/overview", headers={**TUNNEL, "X-StormDesk-Admin-Key": "s3cret-for-tests"})
    assert ok.status_code == 200 and ok.json()["pending_approvals"] == 0


def test_script_only_fills_the_page_through_the_escaping_helper():
    script = (WEB / "app.js").read_text()
    assignments = re.findall(r"\.innerHTML\s*=\s*([^;]+);", script)
    assert assignments and all(a.startswith("part(") or a == "markup" for a in assignments), assignments
    assert "insertAdjacentHTML" not in script and "document.write" not in script
    assert not re.search(r"\son[a-z]+=", (WEB / "index.html").read_text())  # no inline handlers (CSP blocks them)
