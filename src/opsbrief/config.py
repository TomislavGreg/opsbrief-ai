"""Application settings loaded from the environment."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from opsbrief.exclusion import normalise_excluded_fields
from opsbrief.redaction import DEFAULT_SENSITIVE_KEYS
from opsbrief.webhooks import DEFAULT_TIMESTAMP_TOLERANCE_SECONDS, MIN_SECRET_LENGTH


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
    ai_context_excluded_fields: str = ""
    webhook_secret: str = ""
    webhook_timestamp_tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS

    @model_validator(mode="after")
    def _check_webhook_settings(self) -> "Settings":
        """Refuse a webhook configuration that would silently weaken the path.

        The webhook is disabled when ``OPSBRIEF_WEBHOOK_SECRET`` is unset, so an
        empty secret is allowed and means "no webhook". A secret that is set but
        shorter than :data:`~opsbrief.webhooks.MIN_SECRET_LENGTH`, or a
        non-positive skew tolerance, is a misconfiguration that fails loudly here
        rather than accepting weakly authenticated writes later.
        """
        if self.webhook_secret and len(self.webhook_secret) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"OPSBRIEF_WEBHOOK_SECRET must be at least {MIN_SECRET_LENGTH} characters"
            )
        if self.webhook_timestamp_tolerance_seconds <= 0:
            raise ValueError("OPSBRIEF_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS must be positive")
        return self

    def webhook_enabled(self) -> bool:
        """Return whether the webhook front door is configured and enabled.

        A webhook write path exists only when a secret is set; without one the
        route accepts nothing, so an unconfigured deployment never takes an
        unauthenticated write.
        """
        return bool(self.webhook_secret)

    def sensitive_metadata_keys(self) -> frozenset[str]:
        """Return the metadata key terms redaction masks values for.

        The built-in :data:`~opsbrief.redaction.DEFAULT_SENSITIVE_KEYS` are always
        included; ``OPSBRIEF_REDACT_METADATA_KEYS`` adds deployment-specific terms
        as a comma-separated list, so an operator can widen redaction without
        losing the defaults.
        """
        extra = (term.strip() for term in self.redact_metadata_keys.split(","))
        return DEFAULT_SENSITIVE_KEYS | frozenset(term for term in extra if term)

    def excluded_ai_context_fields(self) -> frozenset[str]:
        """Return the event fields held back from the material a model is shown.

        ``OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS`` names them as a comma-separated
        list; an empty setting excludes nothing. Each name must be one of
        :data:`~opsbrief.exclusion.EXCLUDABLE_CONTEXT_FIELDS`, so an unknown field
        is refused here rather than silently ignored.
        """
        return normalise_excluded_fields(self.ai_context_excluded_fields.split(","))


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
