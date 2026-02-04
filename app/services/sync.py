"""Background sync task for periodically fetching data from Contact Energy API."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.services.usage_service import get_usage_service

_LOGGER = logging.getLogger(__name__)

# Global task reference
_sync_task: asyncio.Task | None = None
_sync_running = False


async def _run_sync(days_back: int = 7, include_months: int = 2) -> list[dict[str, Any]]:
    """Run a sync operation for all contracts."""
    global _sync_running
    
    if _sync_running:
        _LOGGER.warning("Sync already running, skipping")
        return []
    
    _sync_running = True
    try:
        _LOGGER.info("Starting data sync: days_back=%d, months=%d", days_back, include_months)
        service = get_usage_service()
        results = await service.sync_all_contracts(
            days_back=days_back,
            include_months=include_months,
        )
        _LOGGER.info("Sync completed: %d contracts synced", len(results))
        return results
    except Exception as e:
        _LOGGER.exception("Sync failed: %s", e)
        return []
    finally:
        _sync_running = False


async def _background_sync_loop(interval_minutes: int = 60) -> None:
    """Background loop that periodically syncs data."""
    _LOGGER.info("Background sync loop started (interval: %d minutes)", interval_minutes)
    
    # Wait a bit on startup before first sync
    await asyncio.sleep(30)
    
    while True:
        try:
            await _run_sync(days_back=7, include_months=2)
        except Exception as e:
            _LOGGER.exception("Background sync error: %s", e)
        
        # Wait for next sync
        await asyncio.sleep(interval_minutes * 60)


def start_background_sync(interval_minutes: int = 60) -> None:
    """Start the background sync task."""
    global _sync_task
    
    if _sync_task is not None:
        _LOGGER.warning("Background sync already running")
        return
    
    _sync_task = asyncio.create_task(_background_sync_loop(interval_minutes))
    _LOGGER.info("Background sync task started")


def stop_background_sync() -> None:
    """Stop the background sync task."""
    global _sync_task
    
    if _sync_task is not None:
        _sync_task.cancel()
        _sync_task = None
        _LOGGER.info("Background sync task stopped")


async def trigger_sync(days_back: int = 7, include_months: int = 2) -> list[dict[str, Any]]:
    """Manually trigger a sync operation."""
    return await _run_sync(days_back=days_back, include_months=include_months)


def is_sync_running() -> bool:
    """Check if a sync is currently running."""
    return _sync_running
