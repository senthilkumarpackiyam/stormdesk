"""CISA's Known Exploited Vulnerabilities catalog: security holes attackers are using right now.

If our VPN product appears here recently and a caller describes odd VPN behaviour, that is a
security call, not a "restart your laptop" call."""

import re
from datetime import timedelta

from stormdesk import timeutil
from stormdesk.config import settings
from stormdesk.sources.http import fetcher

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


async def find_advisories(product: str, recent_days: int = 30, limit: int = 3) -> dict:
    """Raises SourceUnavailable when the catalog can't be fetched and nothing is cached."""
    fetched = await fetcher.get_json(KEV_URL, settings.kev_ttl_s)
    terms = _tokens(product)
    hits = [
        v for v in fetched.data.get("vulnerabilities", [])
        if terms and terms <= _tokens(f"{v.get('vendorProject', '')} {v.get('product', '')}")
    ]
    hits.sort(key=lambda v: v.get("dateAdded", ""), reverse=True)
    cutoff = (timeutil.now() - timedelta(days=recent_days)).date().isoformat()
    recent = [v for v in hits if v.get("dateAdded", "") >= cutoff]
    return {
        "product": product,
        "total_known_exploited": len(hits),
        "recently_added": len(recent),
        "recent_window_days": recent_days,
        "latest": [
            {
                "cve": v.get("cveID"),
                "name": v.get("vulnerabilityName"),
                "date_added": v.get("dateAdded"),
                "summary": (v.get("shortDescription") or "")[:240],
                "used_in_ransomware": v.get("knownRansomwareCampaignUse") == "Known",
            }
            for v in hits[:limit]
        ],
        "catalog_version": fetched.data.get("catalogVersion"),
        "stale": fetched.stale,
    }
