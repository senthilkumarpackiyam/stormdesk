from datetime import UTC, datetime, timedelta


def now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def now_iso() -> str:
    return iso(now())


def ago_iso(*, minutes: float = 0, days: float = 0) -> str:
    return iso(now() - timedelta(minutes=minutes, days=days))


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def humanize(ts: str) -> str:
    """'just now', '12 minutes ago', 'yesterday': the way a person would say it on a call."""
    minutes = int((now() - parse(ts)).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return "yesterday" if days == 1 else f"{days} days ago"
