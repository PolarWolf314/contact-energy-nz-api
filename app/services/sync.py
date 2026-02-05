"""Background sync task for periodically fetching data from Contact Energy API."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.services.usage_service import get_usage_service
from app.services.ha_notify import get_ha_notifier

_LOGGER = logging.getLogger(__name__)

# Global task reference
_sync_task: asyncio.Task | None = None
_sync_running = False
_backfill_progress: dict[str, Any] = {}


def get_backfill_progress() -> dict[str, Any]:
    """Get the current backfill progress."""
    return _backfill_progress.copy()


async def _notify_ha_of_update(results: list[dict[str, Any]]) -> None:
    """Notify Home Assistant that data has been updated."""
    notifier = get_ha_notifier()
    
    if not notifier.is_configured:
        return
    
    # Extract contract IDs that had data synced
    updated_contracts = [
        r["contract_id"] 
        for r in results 
        if r.get("hourly_days_synced", 0) > 0 or r.get("months_synced", 0) > 0
    ]
    
    if updated_contracts:
        _LOGGER.info("Notifying Home Assistant of data update for contracts: %s", updated_contracts)
        await notifier.notify_data_updated(updated_contracts)
        
        # Also fire an event that automations can listen to
        await notifier.fire_event(
            "contact_energy_data_updated",
            {
                "contracts": updated_contracts,
                "timestamp": datetime.now().isoformat(),
            }
        )


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
    notify_ha: bool = True,
    adaptive: bool = False,
) -> list[dict[str, Any]]:
    """Run a sync operation for all contracts.
    
    Args:
        days_back: Number of days to sync (ignored if adaptive=True)
        include_months: Number of months to sync
        force: Force re-fetch even if data exists
        notify_ha: Notify Home Assistant after sync
        adaptive: If True, keep going back until no more data is available
    """
    global _sync_running
    
    if _sync_running:
        _LOGGER.warning("Sync already running, skipping")
        return []
    
    _sync_running = True
    try:
        if adaptive:
            _LOGGER.info("Starting adaptive backfill sync: include_months=%d, force=%s", include_months, force)
        else:
            _LOGGER.info("Starting data sync: days_back=%d, months=%d, force=%s", days_back, include_months, force)
        
        service = get_usage_service()
        
        if adaptive:
            results = await service.sync_all_contracts_adaptive(
                include_months=include_months,
                force=force,
            )
        else:
            results = await service.sync_all_contracts(
                days_back=days_back,
                include_months=include_months,
                force=force,
            )
        
        _LOGGER.info("Sync completed: %d contracts synced", len(results))
        
        # Notify Home Assistant if configured
        if notify_ha and results:
            await _notify_ha_of_update(results)
        
        return results
    except Exception as e:
        _LOGGER.exception("Sync failed: %s", e)
        return []
    finally:
        _sync_running = False


async def _background_sync_loop(interval_minutes: int | None = None) -> None:
    """Background loop that periodically syncs data."""
    settings = get_settings()
    interval = interval_minutes or settings.sync_interval_minutes
    
    _LOGGER.info("Background sync loop started (interval: %d minutes)", interval)
    
    # Wait a bit on startup before first sync
    await asyncio.sleep(30)
    
    # Check if this is a first run (no data in database)
    try:
        needs_backfill = await _check_needs_backfill()
        if needs_backfill:
            _LOGGER.info("First run detected - starting adaptive backfill")
            # Use adaptive backfill to fetch all available historical data
            await _run_sync(
                include_months=12,  # Fetch 12 months of monthly data
                adaptive=True,  # Keep going until API returns no more hourly data
            )
            _LOGGER.info("Backfill complete")
        else:
            # Regular sync
            await _run_sync(
                days_back=settings.regular_sync_days,
                include_months=settings.regular_sync_months,
            )
    except Exception as e:
        _LOGGER.exception("Initial sync error: %s", e)
    
    while True:
        # Wait for next sync
        await asyncio.sleep(interval * 60)
        
        try:
            await _run_sync(
                days_back=settings.regular_sync_days,
                include_months=settings.regular_sync_months,
            )
        except Exception as e:
            _LOGGER.exception("Background sync error: %s", e)


def start_background_sync(interval_minutes: int | None = None) -> None:
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


async def trigger_backfill(adaptive: bool = True) -> list[dict[str, Any]]:
    """Manually trigger a full backfill.
    
    Args:
        adaptive: If True, keep fetching until API returns no more data.
                  If False, fetch the configured maximum days.
    """
    settings = get_settings()
    
    if adaptive:
        _LOGGER.info("Manual adaptive backfill triggered - fetching all available historical data")
        return await _run_sync(include_months=12, adaptive=True)
    else:
        max_days = settings.backfill_max_days if settings.backfill_max_days > 0 else 365
        _LOGGER.info("Manual backfill triggered - fetching %d days of data", max_days)
        return await _run_sync(days_back=max_days, include_months=12)


async def trigger_adaptive_backfill() -> list[dict[str, Any]]:
    """Manually trigger an adaptive backfill that fetches all available data."""
    _LOGGER.info("Adaptive backfill triggered - fetching all available historical data")
    return await _run_sync(include_months=12, adaptive=True)


def is_sync_running() -> bool:
    """Check if a sync is currently running."""
    return _sync_running


def update_backfill_progress(contract_id: str, progress: dict[str, Any]) -> None:
    """Update the backfill progress for a contract."""
    global _backfill_progress
    _backfill_progress[contract_id] = {
        **progress,
        "updated_at": datetime.now().isoformat(),
    }


def clear_backfill_progress() -> None:
    """Clear all backfill progress."""
    global _backfill_progress
    _backfill_progress = {}
