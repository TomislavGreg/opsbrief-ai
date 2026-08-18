"""Application settings loaded from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from opsbrief.redaction import DEFAULT_SENSITIVE_KEYS


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
    redact_metadata_keys: str = ""

    def sensitive_metadata_keys(self) -> frozenset[str]:
        """Return the metadata key terms redaction masks values for.

        The built-in :data:`~opsbrief.redaction.DEFAULT_SENSITIVE_KEYS` are always
        included; ``OPSBRIEF_REDACT_METADATA_KEYS`` adds deployment-specific terms
        as a comma-separated list, so an operator can widen redaction without
        losing the defaults.
        """
        extra = (term.strip() for term in self.redact_metadata_keys.split(","))
        return DEFAULT_SENSITIVE_KEYS | frozenset(term for term in extra if term)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
