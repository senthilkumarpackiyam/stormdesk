"""endoflife.date: is this operating system version still getting security updates?"""

from stormdesk.config import settings
from stormdesk.sources.http import fetcher

EOL_URL = "https://endoflife.date/api/v1/products/{product}"


async def release_support(product: str, release: str) -> dict | None:
    """None if endoflife.date doesn't list that release. Raises SourceUnavailable when unreachable."""
    fetched = await fetcher.get_json(EOL_URL.format(product=product), settings.eol_ttl_s)
    for rel in fetched.data.get("result", {}).get("releases", []):
        if rel.get("name") == release:
            latest = rel.get("latest") or {}
            return {
                "label": rel.get("label") or release,
                "supported": not rel.get("isEol", False),
                "support_ends": rel.get("eolFrom"),
                "latest_version": latest.get("name"),
            }
    return None
