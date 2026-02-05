"""Home Assistant notification service.

Notifies Home Assistant when new data is available so it can refresh its sensors.
"""

import logging
from typing import Any

import aiohttp

from app.config import get_settings

_LOGGER = logging.getLogger(__name__)


class HomeAssistantNotifier:
    """Service to notify Home Assistant of data updates."""

    def __init__(self):
        self._settings = get_settings()

    @property
    def is_configured(self) -> bool:
        """Check if HA integration is configured."""
        return bool(self._settings.ha_url and self._settings.ha_token)

    async def notify_data_updated(self, contract_ids: list[str] | None = None) -> bool:
        """Notify Home Assistant that data has been updated.
        
        This will either:
        1. Call the HA webhook if configured
        2. Trigger entity refresh for configured entities
        
        Args:
            contract_ids: Optional list of contract IDs that were updated
            
        Returns:
            True if notification was sent successfully
        """
        if not self.is_configured:
            _LOGGER.debug("Home Assistant integration not configured, skipping notification")
            return False

        success = True

        # Try webhook first if configured
        if self._settings.ha_webhook_id:
            webhook_success = await self._call_webhook(contract_ids)
            success = success and webhook_success

        # Refresh entities if configured
        if self._settings.ha_entities_to_refresh:
            entities = [
                e.strip() 
                for e in self._settings.ha_entities_to_refresh.split(",")
                if e.strip()
            ]
            for entity_id in entities:
                entity_success = await self._refresh_entity(entity_id)
                success = success and entity_success

        return success

    async def _call_webhook(self, contract_ids: list[str] | None = None) -> bool:
        """Call a Home Assistant webhook."""
        if not self._settings.ha_webhook_id:
            return True

        url = f"{self._settings.ha_url}/api/webhook/{self._settings.ha_webhook_id}"
        
        payload = {
            "event": "contact_energy_data_updated",
            "contract_ids": contract_ids or [],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Successfully notified HA webhook")
                        return True
                    else:
                        _LOGGER.warning(
                            "HA webhook returned status %d: %s",
                            resp.status,
                            await resp.text()
                        )
                        return False
        except Exception as e:
            _LOGGER.warning("Failed to call HA webhook: %s", e)
            return False

    async def _refresh_entity(self, entity_id: str) -> bool:
        """Trigger a refresh for a specific Home Assistant entity."""
        url = f"{self._settings.ha_url}/api/services/homeassistant/update_entity"
        
        headers = {
            "Authorization": f"Bearer {self._settings.ha_token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "entity_id": entity_id,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, 
                    json=payload, 
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Successfully refreshed HA entity: %s", entity_id)
                        return True
                    else:
                        _LOGGER.warning(
                            "HA entity refresh returned status %d for %s: %s",
                            resp.status,
                            entity_id,
                            await resp.text()
                        )
                        return False
        except Exception as e:
            _LOGGER.warning("Failed to refresh HA entity %s: %s", entity_id, e)
            return False

    async def fire_event(self, event_type: str, data: dict[str, Any] | None = None) -> bool:
        """Fire a custom event in Home Assistant.
        
        This can be used to trigger automations based on data updates.
        """
        if not self.is_configured:
            return False

        url = f"{self._settings.ha_url}/api/events/{event_type}"
        
        headers = {
            "Authorization": f"Bearer {self._settings.ha_token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=data or {},
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Successfully fired HA event: %s", event_type)
                        return True
                    else:
                        _LOGGER.warning(
                            "HA event fire returned status %d: %s",
                            resp.status,
                            await resp.text()
                        )
                        return False
        except Exception as e:
            _LOGGER.warning("Failed to fire HA event %s: %s", event_type, e)
            return False


# Global instance
_notifier: HomeAssistantNotifier | None = None


def get_ha_notifier() -> HomeAssistantNotifier:
    """Get the global HA notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = HomeAssistantNotifier()
    return _notifier
