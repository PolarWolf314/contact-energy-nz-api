"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Contact Energy credentials
    username: str
    password: str

    # Cache settings
    cache_ttl_minutes: int = 15

    # Database settings
    database_path: str = "usage.db"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Using lru_cache ensures we only read the .env file once.
    """
    return Settings()
