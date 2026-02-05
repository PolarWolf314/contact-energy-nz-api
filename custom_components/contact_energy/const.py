"""Constants for the Contact Energy integration."""

from typing import Final

DOMAIN: Final = "contact_energy"

# Configuration keys
CONF_API_URL: Final = "api_url"

# Default values
DEFAULT_API_URL: Final = "http://localhost:8000"
DEFAULT_SCAN_INTERVAL: Final = 900  # 15 minutes

# Platforms
PLATFORMS: Final = ["sensor"]

# Services
SERVICE_SYNC: Final = "sync"
SERVICE_BACKFILL: Final = "backfill"

# Attributes
ATTR_CONTRACT_ID: Final = "contract_id"
ATTR_ACCOUNT_ID: Final = "account_id"
ATTR_DATA_AS_OF: Final = "data_as_of"
ATTR_LAST_UPDATED: Final = "last_updated"
