import asyncio

import httpx
import pytest

from stormdesk.sources import vendor_status
from stormdesk.sources.http import CachedFetcher, SourceUnavailable
from tests.conftest import GOOGLE_FEED, SLACK_OUTAGE, STATUSPAGE_OK, STATUSPAGE_OUTAGE


def test_statuspage_operational():
    state, incidents = vendor_status.parse_statuspage(STATUSPAGE_OK)
    assert state == "operational"
    assert incidents == []


def test_statuspage_outage_strips_markdown():
    state, incidents = vendor_status.parse_statuspage(STATUSPAGE_OUTAGE)
    assert state == "outage"
    assert incidents[0]["title"] == "Git operations failing"
    assert "**" not in incidents[0]["latest_update"]


def test_statuspage_html_in_updates_is_cleaned():
    inc = {**STATUSPAGE_OUTAGE["incidents"][0],
           "incident_updates": [{"body": "Recovered. <br /><br />Still checking Projects &amp; Actions."}]}
    _, incidents = vendor_status.parse_statuspage({**STATUSPAGE_OUTAGE, "incidents": [inc]})
    assert incidents[0]["latest_update"] == "Recovered. Still checking Projects & Actions."


def test_statuspage_informational_notice_is_not_an_outage():
    notice = {**STATUSPAGE_OUTAGE["incidents"][0], "name": "Preventative certificate work", "impact": "none"}
    state, incidents = vendor_status.parse_statuspage({**STATUSPAGE_OK, "incidents": [notice]})
    assert state == "operational"
    assert incidents[0]["impact"] == "notice"


def test_statuspage_degraded_component_without_incident():
    data = {**STATUSPAGE_OK, "components": [{"name": "Recordings", "status": "partial_outage", "group": False}]}
    state, incidents = vendor_status.parse_statuspage(data)
    assert state == "degraded"
    assert "Recordings" in incidents[0]["title"]


def test_slack_outage_uses_latest_note():
    state, incidents = vendor_status.parse_slack(SLACK_OUTAGE)
    assert state == "outage"
    assert incidents[0]["latest_update"] == "A fix is rolling out."


def test_google_only_ongoing_incidents_for_that_product():
    state, incidents = vendor_status.parse_google(GOOGLE_FEED, ("Gmail",))
    assert state == "outage"
    assert incidents[0]["title"] == "Users can't load the Gmail inbox."
    assert vendor_status.parse_google(GOOGLE_FEED, ("Google Drive",)) == ("operational", [])


@pytest.mark.parametrize("said, key", [
    ("my email", "gmail"),
    ("Google Meet keeps freezing", "google_meet"),
    ("the vpn", "vpn"),
    ("wi-fi in the office", "wifi"),
    ("I can't print", "printing"),
    ("Okta", "sso"),
])
def test_resolve_service(said, key):
    assert vendor_status.resolve_service(said).key == key


def test_resolve_service_ignores_hard_drive_and_voicemail():
    assert vendor_status.resolve_service("my hard drive is full") is None
    assert vendor_status.resolve_service("voicemail") is None


def _fetcher(handler) -> CachedFetcher:
    return CachedFetcher(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_fetcher_retries_once_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"ok": 1})

    fetched = asyncio.run(_fetcher(handler).get_json("https://x.test/a", ttl_s=60))
    assert fetched.data == {"ok": 1}
    assert len(calls) == 2


def test_fetcher_serves_stale_copy_when_upstream_breaks():
    responses = iter([httpx.Response(200, json={"v": 1}), httpx.Response(500), httpx.Response(500)])
    f = _fetcher(lambda request: next(responses))

    async def run():
        await f.get_json("https://x.test/b", ttl_s=0)
        return await f.get_json("https://x.test/b", ttl_s=0)

    fetched = asyncio.run(run())
    assert fetched.data == {"v": 1}
    assert fetched.stale


def test_fetcher_raises_when_nothing_cached():
    f = _fetcher(lambda request: httpx.Response(500))
    with pytest.raises(SourceUnavailable):
        asyncio.run(f.get_json("https://x.test/c", ttl_s=60))


def test_fetcher_rejects_non_json():
    f = _fetcher(lambda request: httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(SourceUnavailable):
        asyncio.run(f.get_json("https://x.test/d", ttl_s=60))
