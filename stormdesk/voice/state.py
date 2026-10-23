"""The ids deploy created in your ElevenLabs account (data/elevenlabs.json). Kept apart from deploy.py so the
backend can read the agent id without importing the deploy machinery (which imports the backend)."""

import json
from pathlib import Path

from stormdesk.voice.config import STATE_FILE


def load_state(path: Path = STATE_FILE) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")
