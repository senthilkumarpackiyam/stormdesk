"""One-time codes: proof the caller holds the phone registered to the employee they claim to be.

Knowing someone's name and employee ID is easy (LinkedIn, an email signature). Holding their phone
isn't. The code is only ever texted to the number on file; the caller can't supply a different one."""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from stormdesk import messaging, sessions, timeutil
from stormdesk.store.db import connect

CODE_TTL_MIN = 5
MAX_SENDS = 3
MAX_FAILURES = 3  # per call, across resends, so asking for a fresh code doesn't buy more guesses


class TooManyCodes(Exception):
    pass


@dataclass
class CheckResult:
    status: str  # verified | wrong | locked | expired | no_code | bad_format
    remaining: int = 0


def _hash(conversation_id: str, code: str) -> str:
    return hashlib.sha256(f"{conversation_id}:{code}".encode()).hexdigest()


def issue(conversation_id: str, employee: dict) -> None:
    """Text a fresh code to the employee's mobile on file. Raises TooManyCodes or MessagingDown."""
    with connect() as conn:
        row = conn.execute("SELECT sends FROM verification_codes WHERE conversation_id = ?",
                           (conversation_id,)).fetchone()
    sends = row["sends"] if row else 0
    if sends >= MAX_SENDS:
        raise TooManyCodes()
    code = f"{secrets.randbelow(10**6):06d}"
    messaging.send(employee, "sms",
                   f"Acme IT: your verification code is {code}. It expires in {CODE_TTL_MIN} minutes. "
                   "We will never ask for your password. Didn't call the service desk? Ignore this text.")
    expires = timeutil.iso(timeutil.now() + timedelta(minutes=CODE_TTL_MIN))
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO verification_codes (conversation_id, employee_id, code_hash, expires_at, sends)"
            " VALUES (?, ?, ?, ?, ?)",
            (conversation_id, employee["employee_id"], _hash(conversation_id, code), expires, sends + 1),
        )


def check(conversation_id: str, spoken_code: str) -> CheckResult:
    code = re.sub(r"\D", "", spoken_code or "")
    if len(code) != 6:
        return CheckResult("bad_format")
    with connect() as conn:
        row = conn.execute("SELECT * FROM verification_codes WHERE conversation_id = ?",
                           (conversation_id,)).fetchone()
    if not row:
        return CheckResult("no_code")
    if hmac.compare_digest(row["code_hash"], _hash(conversation_id, code)):
        if row["expires_at"] < timeutil.now_iso():
            return CheckResult("expired")
        with connect() as conn:
            # Spent: the same code can't be replayed. Keep the row so the send count still counts.
            conn.execute("UPDATE verification_codes SET code_hash = '' WHERE conversation_id = ?",
                         (conversation_id,))
        sessions.mark_verified(conversation_id)
        return CheckResult("verified")
    failures = sessions.note_code_failure(conversation_id)
    if failures >= MAX_FAILURES:
        sessions.lock(conversation_id)
        return CheckResult("locked")
    return CheckResult("wrong", remaining=MAX_FAILURES - failures)
