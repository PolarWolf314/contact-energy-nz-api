"""Sync control endpoints for manual sync and status checking."""

from typing import Any

from fastapi import APIRouter, Query

from app.services.sync import is_sync_running, trigger_sync
from app.services.usage_service import get_usage_service

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("")
async def trigger_sync_all(
    days_back: int = Query(default=7, ge=1, le=30, description="Days of hourly data to sync"),
    months: int = Query(default=2, ge=1, le=12, description="Months of daily data to sync"),
) -> dict[str, Any]:
    """Trigger a manual sync for all contracts.
    
    This will fetch recent data from the Contact Energy API and store it
    in the local database. Useful after a server restart or to force
    a refresh of cached data.
    """
    if is_sync_running():
        return {
            "status": "already_running",
            "message": "A sync is already in progress",
        }
    
    results = await trigger_sync(days_back=days_back, include_months=months)
    
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
) -> dict[str, Any]:
    """Trigger a manual sync for a specific contract.
    
    This will fetch recent data for the specified contract from the 
    Contact Energy API and store it in the local database.
    """
    service = get_usage_service()
    result = await service.sync_contract_data(
        contract_id=contract_id,
        days_back=days_back,
        include_months=months,
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
