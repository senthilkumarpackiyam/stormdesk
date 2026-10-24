"""Copies of the practice data, saved automatically before every reset.

Each backup is a pair of files in data/backups/ named by local time, e.g. stormdesk-20261024-202410.db
(tickets, calls, reviews) and checkpoints-20261024-202410.db (saved approvals). The newest KEPT are kept.

    uv run python -m stormdesk.seed --backups          # list them, newest first
    uv run python -m stormdesk.seed --restore          # put the newest back (stop the backend first)
    uv run python -m stormdesk.seed --restore 20261024-202410
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from stormdesk import timeutil
from stormdesk.config import settings

KEPT = 10


def folder() -> Path:
    return settings.db_path.parent / "backups"


def _files() -> tuple[Path, Path]:
    return settings.db_path, settings.checkpoint_path


def _copy(source: Path, target: Path) -> None:
    # SQLite's own backup takes a consistent snapshot, even while the server has the file open.
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def _has_data() -> bool:
    if not settings.db_path.exists():
        return False
    with closing(sqlite3.connect(settings.db_path)) as conn:
        try:
            return conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] > 0
        except sqlite3.OperationalError:  # no tables yet
            return False


def names() -> list[str]:
    """Backup names (their timestamps), newest first."""
    prefix = f"{settings.db_path.stem}-"
    return sorted((p.stem.removeprefix(prefix) for p in folder().glob(f"{prefix}*.db")), reverse=True)


def save() -> str | None:
    """Copy the current data aside. Returns the backup's name, or None when there was nothing to keep."""
    if not _has_data():
        return None
    stamp = timeutil.now().astimezone().strftime("%Y%m%d-%H%M%S")
    # Two saves in the same second must not overwrite each other: number them after the highest one so far.
    same = [x for x in names() if x == stamp or x.startswith(f"{stamp}-")]
    name = f"{stamp}-{1 + max(int(x[len(stamp) + 1:] or 1) for x in same)}" if same else stamp
    folder().mkdir(parents=True, exist_ok=True)
    for source in _files():
        if source.exists():
            _copy(source, folder() / f"{source.stem}-{name}.db")
    for old in names()[KEPT:]:
        for source in _files():
            (folder() / f"{source.stem}-{old}.db").unlink(missing_ok=True)
    return name


def restore(name: str = "latest") -> tuple[str, str | None]:
    """Put a backup back in place, after saving the current data too. Returns (restored, safety backup)."""
    available = names()
    if not available:
        raise ValueError("There are no backups yet.")
    chosen = available[0] if name == "latest" else name
    if chosen not in available:
        raise ValueError(f"No backup called {name}. Available: {', '.join(available)}")
    safety = save()
    for target in _files():
        source = folder() / f"{target.stem}-{chosen}.db"
        if source.exists():
            _copy(source, target)
    return chosen, safety
