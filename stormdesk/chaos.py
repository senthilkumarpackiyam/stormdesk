"""Failure switches for drills and the demo video: make a dependency "go down" on purpose."""

import sqlite3

from stormdesk.store.db import connect

FLAGS = {
    "itsm_down": "Ticket system rejects writes (tickets go to the outbox).",
    "sms_down": "Text messages fail to send (no verification codes).",
    "identity_down": "Identity system fails (approved account changes can't be applied).",
    "feeds_down": "Live data sources unreachable (vendor status pages, CISA KEV, endoflife.date).",
}


def is_on(flag: str) -> bool:
    try:
        with connect() as conn:
            row = conn.execute("SELECT enabled FROM chaos WHERE flag = ?", (flag,)).fetchone()
    except sqlite3.OperationalError:  # no database yet (fresh checkout, a bare script): no drills running
        return False
    return bool(row and row["enabled"])


def set_flag(flag: str, enabled: bool) -> None:
    if flag not in FLAGS:
        raise KeyError(flag)
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO chaos (flag, enabled) VALUES (?, ?)", (flag, int(enabled)))


def all_flags() -> dict[str, bool]:
    return {flag: is_on(flag) for flag in FLAGS}
