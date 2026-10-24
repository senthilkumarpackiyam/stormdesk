"""Matching what a caller says against the directory, tolerant of speech-to-text slips."""

import re
import unicodedata
from difflib import SequenceMatcher

NAME_SIMILARITY = 0.8


def normalize_employee_id(raw: str) -> str | None:
    """'e-1001', 'E 1001', '1 0 0 1' -> 'E1001'. None if it can't be an employee ID."""
    digits = re.sub(r"\D", "", raw or "")
    return f"E{digits}" if 3 <= len(digits) <= 6 else None


def _name_parts(name: str) -> list[str]:
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", ascii_name.lower()).split()


def _close(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= NAME_SIMILARITY


def names_match(said: str, on_file: str) -> bool:
    """Full name required: 'Sarah Jeesan' matches 'Sarah Jeesen', a bare 'Sarah' does not."""
    a, b = _name_parts(said), _name_parts(on_file)
    if not a or not b:
        return False
    if _close("".join(a), "".join(b)):
        return True
    return len(a) > 1 and _close(a[0], b[0]) and _close(a[-1], b[-1])
