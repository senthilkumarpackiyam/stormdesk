import pytest
from fastapi.testclient import TestClient

from stormdesk.approvals.graph import forget_compiled
from stormdesk.config import settings
from stormdesk.main import app
from stormdesk.review.config import review_settings
from stormdesk.seed import seed
from stormdesk.sources import eol, kev, vendor_status
from stormdesk.sources.http import fetcher

STATUSPAGE_OK = {
    "page": {"name": "Zoom", "url": "https://www.zoomstatus.com"},
    "status": {"indicator": "none", "description": "All Systems Operational"},
    "components": [{"name": "Meetings", "status": "operational", "group": False}],
    "incidents": [],
}

STATUSPAGE_OUTAGE = {
    "page": {"name": "GitHub", "url": "https://www.githubstatus.com"},
    "status": {"indicator": "major", "description": "Partial System Outage"},
    "components": [{"name": "Git Operations", "status": "major_outage", "group": False}],
    "incidents": [{
        "name": "Git operations failing", "status": "investigating", "impact": "major",
        "started_at": "2026-10-22T15:00:00Z", "shortlink": "https://stspg.io/x",
        "incident_updates": [{"body": "We are **investigating** failures pushing to repositories."}],
        "components": [{"name": "Git Operations"}],
    }],
}

SLACK_OUTAGE = {
    "status": "active",
    "active_incidents": [{
        "title": "Messages failing to send", "type": "outage", "status": "active",
        "date_created": "2026-10-22T10:00:00-07:00", "url": "https://slack-status.com/2026-10/abc",
        "services": ["Messaging"],
        "notes": [{"date_created": "2026-10-22T10:05:00-07:00", "body": "We're looking into it."},
                  {"date_created": "2026-10-22T10:20:00-07:00", "body": "A fix is rolling out."}],
    }],
}

GOOGLE_FEED = [
    {"begin": "2026-10-22T09:00:00+00:00", "end": None, "status_impact": "SERVICE_OUTAGE",
     "service_name": "Gmail", "affected_products": [{"title": "Gmail"}], "uri": "incidents/abc",
     "external_desc": "**Summary:**\nUsers can't load the Gmail inbox.\n**Description:**\nWe're on it.",
     "most_recent_update": {"text": "Mitigation is in progress."}},
    {"begin": "2026-10-01T09:00:00+00:00", "end": "2026-10-01T10:00:00+00:00", "status_impact": "SERVICE_OUTAGE",
     "service_name": "Google Drive", "affected_products": [{"title": "Google Drive"}], "uri": "incidents/old",
     "external_desc": "**Summary:**\nOld, finished.", "most_recent_update": {"text": "Resolved."}},
]

KEV_FEED = {
    "catalogVersion": "2026.10.21",
    "vulnerabilities": [
        {"cveID": "CVE-2026-0001", "vendorProject": "Ivanti", "product": "Connect Secure",
         "vulnerabilityName": "Ivanti Connect Secure Auth Bypass", "dateAdded": "2026-10-13",
         "shortDescription": "Lets attackers skip login.", "knownRansomwareCampaignUse": "Known"},
        {"cveID": "CVE-2024-0002", "vendorProject": "Ivanti", "product": "Connect Secure",
         "vulnerabilityName": "Older Ivanti bug", "dateAdded": "2024-01-10",
         "shortDescription": "Old.", "knownRansomwareCampaignUse": "Unknown"},
        {"cveID": "CVE-2023-0003", "vendorProject": "Zoom", "product": "Desktop Client",
         "vulnerabilityName": "Zoom thing", "dateAdded": "2023-05-01",
         "shortDescription": "Old Zoom.", "knownRansomwareCampaignUse": "Unknown"},
    ],
}


def eol_feed(releases: list[tuple[str, str, bool, str]]) -> dict:
    return {"result": {"releases": [
        {"name": name, "label": label, "isEol": is_eol, "eolFrom": eol_from, "latest": {"name": "x"}}
        for name, label, is_eol, eol_from in releases
    ]}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App on a fresh practice-company database, with every live feed primed (no network)."""
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "checkpoint_path", tmp_path / "checkpoints.db")
    monkeypatch.setattr(settings, "tool_secret", "")
    monkeypatch.setattr(settings, "approval_poll_s", 0)
    monkeypatch.setattr(settings, "review_poll", False)  # never reach ElevenLabs or Nebius from tests
    monkeypatch.setattr(review_settings, "nebius_api_key", "")
    monkeypatch.setattr(review_settings, "langsmith_api_key", "")
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    seed(reset=True)
    fetcher.clear()
    for service in vendor_status.SERVICES.values():
        if service.kind == "statuspage":
            fetcher.prime(service.url, STATUSPAGE_OK)
    fetcher.prime(vendor_status.SERVICES["slack"].url, {"status": "ok", "active_incidents": []})
    fetcher.prime(vendor_status.GOOGLE_FEED, [])
    fetcher.prime(kev.KEV_URL, KEV_FEED)
    fetcher.prime(eol.EOL_URL.format(product="windows"), eol_feed([
        ("11-24h2-w", "11 24H2 (W)", True, "2026-10-13"),
        ("11-24h2-e", "11 24H2 (E)", False, "2027-10-12"),
        ("11-23h2-e", "11 23H2 (E)", False, "2026-11-10"),
        ("11-25h2-e", "11 25H2 (E)", False, "2028-10-10"),
        ("10-22h2", "10 22H2", True, "2025-10-14"),
    ]))
    fetcher.prime(eol.EOL_URL.format(product="macos"), eol_feed([
        ("26", "26", False, None), ("15", "15", False, None), ("14", "14", True, "2026-09-14"),
    ]))
    with TestClient(app) as test_client:
        yield test_client
    fetcher.clear()
    forget_compiled()
