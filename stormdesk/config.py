from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="STORMDESK_", extra="ignore")

    company_name: str = "Acme Corp"
    db_path: Path = ROOT / "data" / "stormdesk.db"

    # Shared secret the voice agent sends in X-StormDesk-Key. Empty means no check (local dev only).
    tool_secret: str = ""
    # Separate secret for the technician endpoints (/admin, approvals). Empty means local-only:
    # anything arriving through a tunnel or proxy is refused, so the voice agent's key can never approve.
    admin_secret: str = ""
    # Where `voice test` checks the results of its scripted calls (the admin endpoints).
    backend_url: str = "http://localhost:8000"

    # Live data sources: per-request timeout and how long a fetched answer stays fresh.
    http_timeout_s: float = 4.0
    status_ttl_s: int = 60
    kev_ttl_s: int = 6 * 3600
    eol_ttl_s: int = 24 * 3600

    # Ticket-storm detection: this many open reports for one service within the window.
    storm_threshold: int = 3
    storm_window_min: int = 30

    # Approvals: LangGraph saves each paused approval here, so it survives a server restart.
    checkpoint_path: Path = ROOT / "data" / "checkpoints.db"
    approval_poll_s: float = 12.0       # how long check_approval_status waits for a decision per call
    approval_in_call_wait_s: int = 120  # after this, the agent stops holding the caller and promises a text
    approval_ttl_min: int = 60          # undecided approvals expire after this

    # Background chores: deliver queued tickets, expire stale approvals, review finished calls.
    housekeeping_interval_s: int = 30
    review_poll: bool = True        # look for finished ElevenLabs calls and review them automatically
    review_max_attempts: int = 3


settings = Settings()
