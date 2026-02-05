"""Sync control endpoints for manual sync and status checking."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.services.sync import (
    is_sync_running,
    trigger_sync,
    trigger_backfill,
    trigger_adaptive_backfill,
    get_backfill_progress,
)
from app.services.usage_service import get_usage_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("")
async def trigger_sync_all(
    days_back: int = Query(default=7, ge=1, le=365, description="Days of hourly data to sync"),
    months: int = Query(default=2, ge=1, le=24, description="Months of daily data to sync"),
    force: bool = Query(default=False, description="Force re-fetch even if data exists"),
) -> dict[str, Any]:
    """Trigger a manual sync for all contracts.
    
    Only fetches data that is missing from the database, unless force=True.
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
            "progress": get_backfill_progress(),
        }
    
    results = await trigger_sync(days_back=days_back, include_months=months, force=force)
    
    return {
        "status": "completed",
        "contracts_synced": len(results),
        "results": results,
    }


@router.post("/{contract_id}")
async def trigger_sync_contract(
    contract_id: str,
    days_back: int = Query(default=7, ge=1, le=365, description="Days of hourly data to sync"),
    months: int = Query(default=2, ge=1, le=24, description="Months of daily data to sync"),
    force: bool = Query(default=False, description="Force re-fetch even if data exists"),
) -> dict[str, Any]:
    """Trigger a manual sync for a specific contract.
    
    Only fetches data that is missing from the database, unless force=True.
    """
    service = get_usage_service()
    result = await service.sync_contract_data(
        contract_id=contract_id,
        days_back=days_back,
        include_months=months,
        force=force,
    )
    
    return {
        "status": "completed",
        "result": result,
    }


@router.get("/status")
async def get_sync_status() -> dict[str, Any]:
    """Get current sync status.
    
    Returns whether a sync is currently running and any backfill progress.
    """
    return {
        "running": is_sync_running(),
        "progress": get_backfill_progress(),
    }


@router.post("/backfill")
async def trigger_backfill_all(
    adaptive: bool = Query(default=True, description="Use adaptive backfill (keeps going until no more data)"),
) -> dict[str, Any]:
    """Trigger a full backfill of historical data.
    
    By default, uses adaptive backfill which keeps fetching data going back in time
    until the API returns no more data. This ensures you get ALL available historical
    hourly data.
    
    Set adaptive=False to use the configured maximum days instead.
    
    Note: This operation may take several minutes to complete depending on how much
    historical data is available.
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
            "progress": get_backfill_progress(),
        }
    
    results = await trigger_backfill(adaptive=adaptive)
    
    return {
        "status": "completed",
        "contracts_synced": len(results),
        "results": results,
    }


@router.post("/backfill/adaptive")
async def trigger_adaptive_backfill_all(
    start_date: str | None = Query(
        default=None,
        description="Start date for backfill (YYYY-MM-DD). Defaults to 5 days ago since Contact Energy data is typically 3-4 days delayed.",
    ),
) -> dict[str, Any]:
    """Trigger an adaptive backfill that fetches ALL available historical data.
    
    This will keep fetching hourly data going back in time until the Contact Energy
    API returns no more data. This is the most thorough backfill option.
    
    The process will stop when it encounters several consecutive days with no data,
    indicating we've reached the limit of available historical data.
    
    Note: This operation may take 10-30 minutes depending on how much historical
    data is available (typically 6-12 months of hourly data).
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
            "progress": get_backfill_progress(),
        }
    
    # Parse start_date if provided
    parsed_start_date = None
    if start_date:
        try:
            parsed_start_date = date.fromisoformat(start_date)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid start_date format: {start_date}. Use YYYY-MM-DD.",
            }
    
    results = await trigger_adaptive_backfill(start_date=parsed_start_date)
    
    return {
        "status": "completed",
        "contracts_synced": len(results),
        "results": results,
    }


@router.post("/{contract_id}/backfill/adaptive")
async def trigger_adaptive_backfill_contract(
    contract_id: str,
    force: bool = Query(default=False, description="Force re-fetch even if data exists"),
    start_date: str | None = Query(
        default=None,
        description="Start date for backfill (YYYY-MM-DD). Defaults to 5 days ago since Contact Energy data is typically 3-4 days delayed.",
    ),
) -> dict[str, Any]:
    """Trigger an adaptive backfill for a specific contract.
    
    Fetches ALL available historical hourly data for the specified contract.
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
            "progress": get_backfill_progress(),
        }
    
    # Parse start_date if provided
    parsed_start_date = None
    if start_date:
        try:
            parsed_start_date = date.fromisoformat(start_date)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid start_date format: {start_date}. Use YYYY-MM-DD.",
            }
    
    service = get_usage_service()
    result = await service.sync_contract_data_adaptive(
        contract_id=contract_id,
        include_months=12,
        force=force,
        start_date=parsed_start_date,
    )
    
    return {
        "status": "completed",
        "result": result,
    }


# Stats endpoint under contracts
stats_router = APIRouter(prefix="/contracts/{contract_id}", tags=["usage"])


@stats_router.get("/stats")
async def get_contract_stats(contract_id: str) -> dict[str, Any]:
    """Get statistics about stored data for a contract.
    
    Returns information about the data stored in the local database,
    including date ranges and record counts.
    """
    service = get_usage_service()
    return await service.get_data_stats(contract_id)
