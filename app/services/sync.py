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

# Backfill settings
BACKFILL_MONTHS = 12  # How far back to fetch on first run
REGULAR_SYNC_MONTHS = 2  # How far back to fetch on regular syncs
REGULAR_SYNC_DAYS = 7  # Days of hourly data on regular syncs


async def _check_needs_backfill() -> bool:
    """Check if any contract needs a backfill (no data in database)."""
    try:
        service = get_usage_service()
        accounts = await service.get_accounts()
        
        for account in accounts:
            for contract in account.contracts:
                stats = await service.get_data_stats(contract.contract_id)
                # If no hourly or daily data exists, we need a backfill
                if not stats or ("hourly" not in stats and "daily" not in stats):
                    _LOGGER.info(
                        "Contract %s has no data, backfill needed",
                        contract.contract_id,
                    )
                    return True
        return False
    except Exception as e:
        _LOGGER.warning("Error checking backfill status: %s", e)
        return False


async def _run_sync(
    days_back: int = 7,
    include_months: int = 2,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Run a sync operation for all contracts."""
    global _sync_running
    
    if _sync_running:
        _LOGGER.warning("Sync already running, skipping")
        return []
    
    _sync_running = True
    try:
        _LOGGER.info("Starting data sync: days_back=%d, months=%d, force=%s", days_back, include_months, force)
        service = get_usage_service()
        results = await service.sync_all_contracts(
            days_back=days_back,
            include_months=include_months,
            force=force,
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
    
    # Check if this is a first run (no data in database)
    try:
        needs_backfill = await _check_needs_backfill()
        if needs_backfill:
            _LOGGER.info(
                "First run detected - starting backfill of %d months of data",
                BACKFILL_MONTHS,
            )
            # Backfill: fetch more historical data
            # Use fewer days_back for hourly (API might not have old hourly data)
            # but fetch full 12 months of daily data
            await _run_sync(days_back=14, include_months=BACKFILL_MONTHS)
            _LOGGER.info("Backfill complete")
        else:
            # Regular sync
            await _run_sync(days_back=REGULAR_SYNC_DAYS, include_months=REGULAR_SYNC_MONTHS)
    except Exception as e:
        _LOGGER.exception("Initial sync error: %s", e)
    
    while True:
        # Wait for next sync
        await asyncio.sleep(interval_minutes * 60)
        
        try:
            await _run_sync(days_back=REGULAR_SYNC_DAYS, include_months=REGULAR_SYNC_MONTHS)
        except Exception as e:
            _LOGGER.exception("Background sync error: %s", e)


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


async def trigger_sync(
    days_back: int = 7,
    include_months: int = 2,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Manually trigger a sync operation."""
    return await _run_sync(days_back=days_back, include_months=include_months, force=force)


async def trigger_backfill() -> list[dict[str, Any]]:
    """Manually trigger a full backfill (12 months of data)."""
    _LOGGER.info("Manual backfill triggered - fetching %d months of data", BACKFILL_MONTHS)
    return await _run_sync(days_back=14, include_months=BACKFILL_MONTHS)


def is_sync_running() -> bool:
    """Check if a sync is currently running."""
    return _sync_running
