import os
import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

from stormdesk.config import ROOT


class ReviewSettings(BaseSettings):
    """Keys for the reviewers' services, read from .env (named as the services name them)."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    stormdesk_review_model: str = "moonshotai/Kimi-K3"
    # Used when the main model times out or is unavailable: the other model that scored 5/5 in the comparison.
    stormdesk_review_backup_model: str = "deepseek-ai/DeepSeek-V4.1-Flash"
    langsmith_api_key: str = ""
    langsmith_project: str = "stormdesk-reviews"


review_settings = ReviewSettings()

# langchain-openai with a newer openai library warns about a metadata field it doesn't use. Harmless.
warnings.filterwarnings("ignore", message=".*Pydantic serializer warnings.*")
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")


def enable_tracing() -> bool:
    """Send every review run to LangSmith, if a key is set. Returns whether tracing is on."""
    if not review_settings.langsmith_api_key:
        return False
    os.environ.setdefault("LANGSMITH_API_KEY", review_settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", review_settings.langsmith_project)
    return True
