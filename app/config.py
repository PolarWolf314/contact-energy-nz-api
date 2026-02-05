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

    # Home Assistant integration settings
    # Set these to enable push notifications to HA when data is updated
    ha_url: str | None = None  # e.g., "http://homeassistant.local:8123"
    ha_token: str | None = None  # Long-lived access token
    ha_webhook_id: str | None = None  # Optional webhook ID for notifications
    # Comma-separated list of entity IDs to refresh after sync
    # e.g., "sensor.contact_energy_electricity,sensor.contact_energy_gas"
    ha_entities_to_refresh: str | None = None

    # Backfill settings
    # Maximum number of days to backfill hourly data (0 = adaptive/unlimited)
    backfill_max_days: int = 0  # 0 means keep going until API returns no data
    # Number of consecutive empty days before stopping adaptive backfill
    backfill_empty_days_threshold: int = 3
    # Delay between API calls during backfill (seconds) to avoid rate limiting
    backfill_api_delay: float = 1.0
    # Regular sync settings
    regular_sync_days: int = 7  # Days of hourly data for regular syncs
    regular_sync_months: int = 2  # Months of daily data for regular syncs
    # Sync interval in minutes
    sync_interval_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Using lru_cache ensures we only read the .env file once.
    """
    return Settings()
