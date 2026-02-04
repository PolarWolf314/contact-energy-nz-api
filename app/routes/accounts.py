"""Account discovery endpoints."""

from fastapi import APIRouter

from app.models import AccountsResponse
from app.services.usage_service import get_usage_service

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=AccountsResponse)
async def get_accounts() -> AccountsResponse:
    """Get all accounts and contracts.

    Returns a list of accounts with their associated contracts.
    Use the contract_id from this response to query usage data.
    """
    service = get_usage_service()
    accounts = await service.get_accounts()
    return AccountsResponse(accounts=accounts)
