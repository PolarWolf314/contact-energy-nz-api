"""Sync control endpoints for manual sync and status checking."""

from typing import Any

from fastapi import APIRouter, Query

from app.services.sync import is_sync_running, trigger_sync, trigger_backfill
from app.services.usage_service import get_usage_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("")
async def trigger_sync_all(
    days_back: int = Query(default=7, ge=1, le=30, description="Days of hourly data to sync"),
    months: int = Query(default=2, ge=1, le=12, description="Months of daily data to sync"),
    force: bool = Query(default=False, description="Force re-fetch even if data exists"),
) -> dict[str, Any]:
    """Trigger a manual sync for all contracts.
    
    Only fetches data that is missing from the database, unless force=True.
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
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
    days_back: int = Query(default=7, ge=1, le=30, description="Days of hourly data to sync"),
    months: int = Query(default=2, ge=1, le=12, description="Months of daily data to sync"),
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
    
    Returns whether a sync is currently running.
    """
    return {
        "running": is_sync_running(),
    }


@router.post("/backfill")
async def trigger_backfill_all() -> dict[str, Any]:
    """Trigger a full backfill of historical data (12 months).
    
    This will fetch up to 12 months of historical data from the Contact 
    Energy API for all contracts. This is automatically done on first run,
    but can be triggered manually if needed.
    
    Note: This operation may take several minutes to complete.
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
        }
    
    results = await trigger_backfill()
    
    return {
        "status": "completed",
        "contracts_synced": len(results),
        "results": results,
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
