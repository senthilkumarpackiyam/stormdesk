"""Live "is it them or is it us?" checks.

Vendor services come from their public status pages: the Atlassian Statuspage format most SaaS
companies use, Slack's own API, and Google Workspace's incident feed. Internal services (VPN,
Wi-Fi, SSO, printing) have no public page, so their status is whether our own ticket system has
an open major incident for them."""

import asyncio
import html
import re
from dataclasses import dataclass

from stormdesk import timeutil
from stormdesk.config import settings
from stormdesk.itsm import itsm
from stormdesk.sources.http import SourceUnavailable, fetcher
from stormdesk.store.db import connect, dicts

GOOGLE_FEED = "https://www.google.com/appsstatus/dashboard/incidents.json"
GOOGLE_DASHBOARD = "https://www.google.com/appsstatus/dashboard/"

# "notice" is an informational post (e.g. planned security work): listed, but nothing is broken.
SEVERITY = {"operational": 0, "notice": 0, "degraded": 1, "outage": 2}


@dataclass(frozen=True)
class Service:
    key: str
    name: str
    kind: str  # statuspage | slack | google | internal
    aliases: tuple[str, ...]
    url: str = ""
    google_products: tuple[str, ...] = ()
    tech_stack: str = ""  # product name to look up in the CISA KEV catalog


SERVICES: dict[str, Service] = {
    s.key: s
    for s in [
        Service("slack", "Slack", "slack", ("slack",), "https://slack-status.com/api/v2.0.0/current"),
        Service("zoom", "Zoom", "statuspage", ("zoom",), "https://www.zoomstatus.com/api/v2/summary.json",
                tech_stack="Zoom"),
        Service("gmail", "Gmail", "google", ("gmail", "google mail", "email", "e-mail", "mail", "inbox"),
                GOOGLE_FEED, ("Gmail",)),
        Service("google_meet", "Google Meet", "google", ("google meet", "meet", "hangouts"),
                GOOGLE_FEED, ("Google Meet",)),
        Service("google_drive", "Google Drive", "google", ("google drive", "gdrive", "shared drive"),
                GOOGLE_FEED, ("Google Drive",)),
        Service("google_calendar", "Google Calendar", "google", ("google calendar", "calendar"),
                GOOGLE_FEED, ("Google Calendar",)),
        Service("google_docs", "Google Docs", "google", ("google docs", "google sheets", "docs", "sheets", "slides"),
                GOOGLE_FEED, ("Google Docs", "Google Sheets", "Google Slides")),
        Service("github", "GitHub", "statuspage", ("github",), "https://www.githubstatus.com/api/v2/summary.json"),
        Service("jira", "Jira", "statuspage", ("jira",),
                "https://jira-software.status.atlassian.com/api/v2/summary.json"),
        Service("confluence", "Confluence", "statuspage", ("confluence", "wiki"),
                "https://confluence.status.atlassian.com/api/v2/summary.json"),
        Service("figma", "Figma", "statuspage", ("figma",), "https://status.figma.com/api/v2/summary.json"),
        Service("notion", "Notion", "statuspage", ("notion",), "https://www.notion-status.com/api/v2/summary.json"),
        Service("chatgpt", "ChatGPT", "statuspage", ("chatgpt", "chat gpt", "openai"),
                "https://status.openai.com/api/v2/summary.json"),
        Service("vpn", "VPN", "internal", ("vpn", "remote access", "ivanti", "secure access", "pulse secure"),
                tech_stack="Ivanti Connect Secure"),
        Service("wifi", "Office Wi-Fi", "internal", ("wifi", "wi-fi", "wireless", "office network")),
        Service("sso", "Single sign-on", "internal", ("sso", "single sign-on", "single sign on", "okta", "login page")),
        Service("printing", "Printing", "internal", ("printer", "printers", "printing", "print")),
    ]
}

# Longest alias first, so "google meet" wins over "meet".
_ALIASES = sorted(
    ((alias, s) for s in SERVICES.values() for alias in (s.key.replace("_", " "), s.name.lower(), *s.aliases)),
    key=lambda pair: -len(pair[0]),
)


def resolve_service(text: str) -> Service | None:
    """Map whatever the caller said ("my email", "the VPN thing") to a tracked service."""
    cleaned = " ".join(re.findall(r"[a-z0-9\-]+", text.lower()))
    if cleaned in SERVICES:
        return SERVICES[cleaned]
    for alias, service in _ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", cleaned):
            return service
    return None


def _worst(a: str, b: str) -> str:
    return a if SEVERITY.get(a, 0) >= SEVERITY.get(b, 0) else b


def _clip(text: str | None, limit: int = 280) -> str:
    """Strip HTML and markdown, and trim to roughly one spoken sentence or two."""
    text = html.unescape(re.sub(r"<[^>]*>", " ", text or ""))
    text = re.sub(r"[*#_`>]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0] + "…"


# --- parsers: upstream JSON -> (state, incidents) ---------------------------------------------

_SP_INDICATOR = {"none": "operational", "minor": "degraded", "major": "outage", "critical": "outage",
                 "maintenance": "degraded"}
_SP_IMPACT = {"none": "notice", "minor": "degraded", "major": "outage", "critical": "outage",
              "maintenance": "degraded"}
_SP_DONE = {"resolved", "postmortem", "completed"}


def parse_statuspage(data: dict) -> tuple[str, list[dict]]:
    state = _SP_INDICATOR.get(data.get("status", {}).get("indicator"), "operational")
    incidents = []
    for inc in data.get("incidents", []):
        if inc.get("status") in _SP_DONE:
            continue
        updates = inc.get("incident_updates") or []
        impact = _SP_IMPACT.get(inc.get("impact"), "degraded")
        incidents.append({
            "title": inc.get("name", "Unnamed incident"),
            "impact": impact,
            "status": inc.get("status"),
            "started_at": inc.get("started_at") or inc.get("created_at"),
            "latest_update": _clip(updates[0].get("body")) if updates else "",
            "affected": [c["name"] for c in inc.get("components", [])][:5],
            "link": inc.get("shortlink"),
        })
        state = _worst(state, impact)
    if state == "operational":
        broken = [c for c in data.get("components", []) if not c.get("group") and c.get("status") != "operational"]
        if broken:
            state = "degraded"
            incidents.append({
                "title": "Degraded: " + ", ".join(c["name"] for c in broken[:3]),
                "impact": "degraded",
                "status": broken[0].get("status"),
                "started_at": broken[0].get("updated_at"),
                "latest_update": "",
                "affected": [c["name"] for c in broken[:5]],
                "link": data.get("page", {}).get("url"),
            })
    return state, incidents


_SLACK_TYPE = {"outage": "outage", "incident": "degraded", "notice": "degraded"}


def parse_slack(data: dict) -> tuple[str, list[dict]]:
    state = "operational"
    incidents = []
    for inc in data.get("active_incidents", []):
        notes = inc.get("notes") or []
        latest = max(notes, key=lambda n: n.get("date_created", ""), default={})
        impact = _SLACK_TYPE.get(inc.get("type"), "degraded")
        incidents.append({
            "title": inc.get("title", "Slack incident"),
            "impact": impact,
            "status": inc.get("status"),
            "started_at": inc.get("date_created"),
            "latest_update": _clip(latest.get("body")),
            "affected": inc.get("services", [])[:5],
            "link": inc.get("url"),
        })
        state = _worst(state, impact)
    if data.get("status") not in (None, "ok") and state == "operational":
        state = "degraded"
    return state, incidents


_GOOGLE_IMPACT = {"SERVICE_OUTAGE": "outage", "SERVICE_DISRUPTION": "degraded", "SERVICE_INFORMATION": "degraded"}


def _google_title(desc: str) -> str:
    lines = [ln.strip(" *") for ln in (desc or "").splitlines() if ln.strip(" *")]
    for i, line in enumerate(lines):
        if line.lower().startswith("summary") and i + 1 < len(lines):
            return _clip(lines[i + 1], 140)
    return _clip(lines[0], 140) if lines else "Google Workspace incident"


def parse_google(data: list, products: tuple[str, ...]) -> tuple[str, list[dict]]:
    state = "operational"
    incidents = []
    for inc in data:
        if inc.get("end"):
            continue
        names = {p.get("title") for p in inc.get("affected_products") or []} | {inc.get("service_name")}
        if not names & set(products):
            continue
        impact = _GOOGLE_IMPACT.get(inc.get("status_impact"), "degraded")
        incidents.append({
            "title": _google_title(inc.get("external_desc", "")),
            "impact": impact,
            "status": "ongoing",
            "started_at": inc.get("begin"),
            "latest_update": _clip((inc.get("most_recent_update") or {}).get("text")),
            "affected": sorted(n for n in names if n),
            "link": GOOGLE_DASHBOARD + inc["uri"] if inc.get("uri") else GOOGLE_DASHBOARD,
        })
        state = _worst(state, impact)
    return state, incidents


# --- demo switch ---------------------------------------------------------------------------------
# Real outages happen at random. For a recorded demo you can flip a service into a fake outage;
# every answer built from it carries demo=true so nobody mistakes it for the live feed.

def demo_outage(service_key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM demo_outages WHERE service_key = ?", (service_key,)).fetchone()
    return dict(row) if row else None


def list_demo_outages() -> list[dict]:
    with connect() as conn:
        return dicts(conn.execute("SELECT * FROM demo_outages ORDER BY created_at"))


def set_demo_outage(service_key: str, title: str, impact: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO demo_outages (service_key, title, impact, created_at) VALUES (?, ?, ?, ?)",
            (service_key, title, impact, timeutil.now_iso()),
        )


def clear_demo_outage(service_key: str) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM demo_outages WHERE service_key = ?", (service_key,)).rowcount > 0


# --- public API ----------------------------------------------------------------------------------

def _summary(service: Service, state: str, incidents: list[dict], stale_age_s: int | None) -> str:
    if state == "unknown":
        return f"I couldn't reach the {service.name} status page just now, so I can't confirm either way."
    if state == "operational":
        text = f"{service.name} reports no known issues right now."
        if incidents:
            text += f" There's an informational notice: {incidents[0]['title']}."
    else:
        top = incidents[0]
        text = f"{service.name} has an active {'outage' if state == 'outage' else 'issue'}: {top['title']}."
        if top.get("latest_update"):
            text += f" Latest update: {top['latest_update']}"
    if stale_age_s is not None:
        text += f" (This is from {max(stale_age_s // 60, 1)} min ago; the live page didn't answer.)"
    return text


def _result(service: Service, state: str, incidents: list[dict], *, source: str,
            stale_age_s: int | None = None, demo: bool = False) -> dict:
    return {
        "service": service.name,
        "service_key": service.key,
        "state": state,
        "summary": _summary(service, state, incidents, stale_age_s),
        "incidents": incidents[:3],
        "source": source,
        "checked_at": timeutil.now_iso(),
        "stale": stale_age_s is not None,
        "demo": demo,
    }


async def get_status(service: Service) -> dict:
    override = demo_outage(service.key)
    if override:
        incident = {"title": override["title"], "impact": override["impact"], "status": "investigating",
                    "started_at": override["created_at"], "latest_update": "Engineers are investigating.",
                    "affected": [service.name], "link": None}
        return _result(service, override["impact"], [incident], source="demo override", demo=True)

    if service.kind == "internal":
        major = itsm.open_major_incident(service.key)
        if not major:
            return _result(service, "operational", [], source="internal tickets")
        impact = "outage" if major["priority"] == 1 else "degraded"
        incident = {"title": major["short_description"], "impact": impact, "status": major["state"],
                    "started_at": major["created_at"], "latest_update": f"Tracked as major incident {major['number']}.",
                    "affected": [service.name], "link": None, "number": major["number"]}
        return _result(service, impact, [incident], source="internal tickets")

    try:
        fetched = await fetcher.get_json(service.url, settings.status_ttl_s)
        if service.kind == "statuspage":
            state, incidents = parse_statuspage(fetched.data)
        elif service.kind == "slack":
            state, incidents = parse_slack(fetched.data)
        else:
            state, incidents = parse_google(fetched.data, service.google_products)
    except (SourceUnavailable, KeyError, TypeError, AttributeError):
        return _result(service, "unknown", [], source=service.url)
    return _result(service, state, incidents, source=service.url,
                   stale_age_s=fetched.age_s if fetched.stale else None)


async def all_statuses() -> list[dict]:
    return list(await asyncio.gather(*(get_status(s) for s in SERVICES.values())))
