"""Application settings loaded from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values are read from environment variables prefixed with ``OPSBRIEF_``,
    falling back to a local ``.env`` file when one is present.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPSBRIEF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "OpsBrief AI"
    environment: str = "development"
    log_level: str = "info"
    database_url: str = "sqlite:///./opsbrief.db"
    ai_provider: str = "fake"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
