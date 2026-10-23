"""Ticket-storm detection: many colleagues, one broken service, a few minutes apart.

StormDesk never declares a major incident itself. It proposes one, with the evidence, and an
on-call technician decides. Once declared, every new caller is linked to it automatically."""

from collections import Counter

from stormdesk import approvals, timeutil
from stormdesk.approvals import store
from stormdesk.config import settings
from stormdesk.itsm import itsm
from stormdesk.sources import vendor_status


def board() -> list[dict]:
    """Every service with recent reports, a pending proposal, or an open major incident."""
    since = timeutil.ago_iso(minutes=settings.storm_window_min)
    rows = []
    for service in vendor_status.SERVICES.values():
        reports = itsm.open_reports(service.key, since)
        major = itsm.open_major_incident(service.key)
        proposal = store.pending_for("major_incident", service=service.key)
        if not (reports or major or proposal):
            continue
        rows.append({
            "service_key": service.key,
            "service": service.name,
            "open_reports": len(reports),
            "threshold": settings.storm_threshold,
            "window_minutes": settings.storm_window_min,
            "locations": dict(Counter(r["location"] or "unknown" for r in reports)),
            "proposal": proposal["approval_id"] if proposal else None,
            "major_incident": {
                "number": major["number"],
                "summary": major["short_description"],
                "opened": timeutil.humanize(major["created_at"]),
                "linked_open": len(itsm.children_of(major["number"])),
            } if major else None,
        })
    return sorted(rows, key=lambda r: (r["major_incident"] is None, -r["open_reports"]))


async def check(service_key: str) -> dict | None:
    """Propose a major incident if a storm is building. Returns the proposal (new or already pending)."""
    if itsm.open_major_incident(service_key):
        return None
    pending = store.pending_for("major_incident", service=service_key)
    if pending:
        return pending
    since = timeutil.ago_iso(minutes=settings.storm_window_min)
    reports = itsm.open_reports(service_key, since)
    if len(reports) < settings.storm_threshold:
        return None
    service = vendor_status.SERVICES[service_key]
    status = await vendor_status.get_status(service)
    by_location = Counter(r["location"] or "unknown" for r in reports)
    evidence = [
        f"{len(reports)} open {service.name} reports in the last {settings.storm_window_min} minutes "
        f"({', '.join(f'{n} from {loc}' for loc, n in by_location.most_common())}).",
        f"Status check: {status['summary']}",
    ]
    return approvals.start("major_incident", f"Possible {service.name} outage", service=service_key,
                           details={"since": since, "evidence": evidence, "report_count": len(reports)})
