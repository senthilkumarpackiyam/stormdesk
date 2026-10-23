import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from stormdesk.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL,
    mobile      TEXT NOT NULL,
    department  TEXT NOT NULL,
    title       TEXT NOT NULL,
    location    TEXT NOT NULL,
    manager_id  TEXT,
    vip         INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'active'      -- active | terminated
);

CREATE TABLE IF NOT EXISTS devices (
    device_id   TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES employees(employee_id),
    kind        TEXT NOT NULL,                      -- laptop | phone
    model       TEXT NOT NULL,
    os_product  TEXT NOT NULL,                      -- endoflife.date product, e.g. windows, macos
    os_release  TEXT NOT NULL,                      -- endoflife.date release, e.g. 11-24h2-w
    os_label    TEXT NOT NULL                       -- what a person would say, e.g. Windows 11 24H2
);

CREATE TABLE IF NOT EXISTS kb_articles (
    kb_id            TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    category         TEXT NOT NULL,
    service          TEXT,
    keywords         TEXT NOT NULL,
    steps            TEXT NOT NULL,                 -- JSON list of short, speakable steps
    escalate_if      TEXT NOT NULL,
    sensitive_action TEXT                           -- set when the fix needs human approval, e.g. mfa_reset
);

CREATE TABLE IF NOT EXISTS incidents (
    number            TEXT PRIMARY KEY,
    employee_id       TEXT REFERENCES employees(employee_id),
    short_description TEXT NOT NULL,
    category          TEXT NOT NULL,
    service           TEXT,
    location          TEXT,
    priority          INTEGER NOT NULL DEFAULT 3,   -- 1 critical .. 4 low
    state             TEXT NOT NULL DEFAULT 'new',  -- new | in_progress | on_hold | resolved | closed
    is_major          INTEGER NOT NULL DEFAULT 0,
    parent_number     TEXT REFERENCES incidents(number),
    channel           TEXT NOT NULL DEFAULT 'voice',
    conversation_id   TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    resolved_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_incidents_service ON incidents(service, state, created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_employee ON incidents(employee_id, created_at);

CREATE TABLE IF NOT EXISTS demo_outages (
    service_key TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    impact      TEXT NOT NULL,                      -- degraded | outage
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    number     TEXT NOT NULL REFERENCES incidents(number),
    author     TEXT NOT NULL,
    note       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- One row per call: who the caller turned out to be, and how far they got verifying it.
CREATE TABLE IF NOT EXISTS sessions (
    conversation_id TEXT PRIMARY KEY,
    employee_id     TEXT REFERENCES employees(employee_id),
    identified_at   TEXT,
    verified_at     TEXT,
    lookup_failures INTEGER NOT NULL DEFAULT 0,
    code_failures   INTEGER NOT NULL DEFAULT 0,
    locked          INTEGER NOT NULL DEFAULT 0,
    last_ticket     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_codes (
    conversation_id TEXT PRIMARY KEY,
    employee_id     TEXT NOT NULL,
    code_hash       TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    sends           INTEGER NOT NULL DEFAULT 1
);

-- Simulated phones and inboxes: every text or email the system sends lands here.
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    channel     TEXT NOT NULL,                      -- sms | email
    to_address  TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id     TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,                  -- mfa_reset | account_unlock | access_grant | major_incident
    status          TEXT NOT NULL,                  -- pending | approved | rejected | expired | executed | failed
    employee_id     TEXT,
    service         TEXT,
    conversation_id TEXT,
    incident_number TEXT,
    reason          TEXT NOT NULL,
    details         TEXT NOT NULL DEFAULT '{}',     -- JSON
    risk_level      TEXT,
    risk_notes      TEXT NOT NULL DEFAULT '[]',     -- JSON
    decided_by      TEXT,
    decision_note   TEXT,
    result          TEXT,
    created_at      TEXT NOT NULL,
    decided_at      TEXT,
    completed_at    TEXT
);

-- What the identity system (Okta stand-in) actually changed, and on whose approval.
CREATE TABLE IF NOT EXISTS identity_changes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id  TEXT NOT NULL,
    action       TEXT NOT NULL,
    approval_id  TEXT NOT NULL,
    performed_by TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

-- Writes the ticket system couldn't take yet. The caller gets the PEND- reference straight away.
CREATE TABLE IF NOT EXISTS outbox (
    ref          TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,                     -- incident | note
    payload      TEXT NOT NULL,                     -- JSON
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | delivered
    attempts     INTEGER NOT NULL DEFAULT 0,
    result       TEXT,
    last_error   TEXT,
    created_at   TEXT NOT NULL,
    delivered_at TEXT
);

-- Failure switches for drills and demos: ticket system down, texts failing, identity system down.
CREATE TABLE IF NOT EXISTS chaos (
    flag    TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL
);

-- The post-call review of each conversation (phase 5).
CREATE TABLE IF NOT EXISTS reviews (
    conversation_id TEXT PRIMARY KEY,
    status          TEXT NOT NULL,                  -- running | done | partial | failed
    employee_id     TEXT,
    verdict         TEXT,                           -- pass | attention | fail
    headline        TEXT,
    report          TEXT NOT NULL DEFAULT '{}',     -- JSON: scorecard, reviewers, rule checks, follow-ups
    model           TEXT,
    source          TEXT NOT NULL,                  -- auto | manual
    attempts        INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    call_started_at TEXT,
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,
    conversation_id TEXT,
    tool            TEXT NOT NULL,
    request         TEXT NOT NULL,
    response        TEXT NOT NULL,
    ok              INTEGER NOT NULL,
    latency_ms      INTEGER NOT NULL
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after phase 1, so databases created then pick them up without a reset.
ADDED_COLUMNS = {
    "incidents": {
        "description": "TEXT",
        "impact": "TEXT",
        "urgency": "TEXT",
        "kb_id": "TEXT",
        # ITIL keeps two kinds apart: an *incident* (something is broken) and a *request* (please change
        # something for me, e.g. an MFA reset). Only incidents count towards storms and duplicates.
        "ticket_type": "TEXT NOT NULL DEFAULT 'incident'",
    },
}


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, columns in ADDED_COLUMNS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def dicts(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]
