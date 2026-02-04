"""Usage data endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.models import (
    CurrentUsageResponse,
    HourlyUsageData,
    MonthlyUsageResponse,
    UsageSummary,
)
from app.services.usage_service import get_usage_service

router = APIRouter(prefix="/contracts/{contract_id}", tags=["usage"])


@router.get("/usage/current", response_model=CurrentUsageResponse)
async def get_current_usage(contract_id: str) -> CurrentUsageResponse:
    """Get current month's usage and today's data.

    Returns the current month's aggregate usage and today's usage so far.
    """
    service = get_usage_service()
    current_month, today = await service.get_current_usage(contract_id)

    return CurrentUsageResponse(
        contract_id=contract_id,
        current_month=current_month,
        today=today,
    )


@router.get("/usage/hourly", response_model=HourlyUsageData)
async def get_hourly_usage(
    contract_id: str,
    target_date: Annotated[
        date | None,
        Query(alias="date", description="Date to get hourly usage for (YYYY-MM-DD)"),
    ] = None,
) -> HourlyUsageData:
    """Get hourly usage breakdown for a specific day.

    Defaults to today if no date is provided.
    """
    if target_date is None:
        target_date = date.today()

    service = get_usage_service()

    try:
        return await service.get_hourly_usage(contract_id, target_date)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch hourly usage: {str(e)}",
        )


@router.get("/usage/monthly", response_model=MonthlyUsageResponse)
async def get_monthly_usage(
    contract_id: str,
    start: Annotated[
        str,
        Query(description="Start month (YYYY-MM)"),
    ],
    end: Annotated[
        str,
        Query(description="End month (YYYY-MM)"),
    ],
) -> MonthlyUsageResponse:
    """Get monthly usage for a date range.

    Returns aggregated usage data for each month in the range.
    """
    # Validate month format
    try:
        _validate_month_format(start)
        _validate_month_format(end)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    service = get_usage_service()

    try:
        months = await service.get_monthly_usage(contract_id, start, end)
        return MonthlyUsageResponse(
            contract_id=contract_id,
            start_month=start,
            end_month=end,
            months=months,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch monthly usage: {str(e)}",
        )


@router.get("/summary", response_model=UsageSummary)
async def get_usage_summary(contract_id: str) -> UsageSummary:
    """Get complete usage summary with comparisons.

    Returns today's usage, yesterday's usage, current and last month aggregates,
    and percentage comparisons (vs yesterday, vs last month, vs same day last week).

    This is the recommended endpoint for Home Assistant REST sensors as it
    provides all metrics in a single request.
    """
    service = get_usage_service()

    try:
        return await service.get_summary(contract_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch usage summary: {str(e)}",
        )


def _validate_month_format(month: str) -> None:
    """Validate that a string is in YYYY-MM format."""
    if len(month) != 7 or month[4] != "-":
        raise ValueError(f"Invalid month format: {month}. Expected YYYY-MM")

    try:
        year = int(month[:4])
        month_num = int(month[5:])
        if not (1 <= month_num <= 12):
            raise ValueError(f"Invalid month: {month_num}")
        if not (2000 <= year <= 2100):
            raise ValueError(f"Invalid year: {year}")
    except ValueError as e:
        raise ValueError(f"Invalid month format: {month}. {e}")
