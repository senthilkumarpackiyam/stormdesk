from pydantic_settings import BaseSettings, SettingsConfigDict

from stormdesk.config import ROOT


class VoiceSettings(BaseSettings):
    """Keys for the outside services, read from .env (no STORMDESK_ prefix, as the services name them)."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    elevenlabs_api_key: str = ""
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""  # optional free static domain, e.g. happy-otter-1234.ngrok-free.app

    # The conversation itself.
    stormdesk_agent_name: str = "StormDesk"
    stormdesk_llm: str = "claude-haiku-5-5"
    stormdesk_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # Sarah: mature, reassuring
    stormdesk_tts_model: str = "eleven_flash_v2"


voice_settings = VoiceSettings()

ELEVENLABS_API = "https://api.elevenlabs.io"
STATE_FILE = ROOT / "data" / "elevenlabs.json"  # ids of what deploy created in your account
EXPORT_DIR = ROOT / "elevenlabs"  # the agent and tool definitions, committed for reviewers
SECRET_NAME = "stormdesk_tool_key"
