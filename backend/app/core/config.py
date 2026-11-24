"""Application configuration, loaded from environment variables.

Secrets and deployment-specific values come only from the environment
(or a local, git-ignored ``.env`` file). See ``.env.example`` for the
full list of supported variables.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the Zhero backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Zhero API"
    app_version: str = "0.1.0"
    app_env: str = Field(default="development", description="development | test | production")
    app_secret_key: str = "replace_with_local_secret"
    log_level: str = "INFO"

    # Not used until the database milestone (Sprint 1, day 4).
    database_url: str | None = None

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings (override in tests via ``dependency_overrides``)."""
    return Settings()
