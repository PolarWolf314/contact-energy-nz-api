"""Tests for API routes."""

import pytest
from httpx import AsyncClient


class TestHealthRoutes:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, async_client: AsyncClient):
        """Test the health check endpoint returns OK."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestAccountRoutes:
    """Tests for account discovery endpoints."""

    @pytest.mark.asyncio
    async def test_get_accounts(self, async_client: AsyncClient, mock_contact_api):
        """Test getting accounts returns expected structure."""
        response = await async_client.get("/accounts")

        assert response.status_code == 200
        data = response.json()
        assert "accounts" in data
        assert isinstance(data["accounts"], list)


class TestUsageRoutes:
    """Tests for usage data endpoints."""

    @pytest.mark.asyncio
    async def test_get_current_usage(self, async_client: AsyncClient, mock_contact_api):
        """Test getting current usage returns expected structure."""
        response = await async_client.get("/contracts/789012/usage/current")

        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == "789012"
        assert "current_month" in data
        assert "today" in data

    @pytest.mark.asyncio
    async def test_get_hourly_usage(self, async_client: AsyncClient, mock_contact_api):
        """Test getting hourly usage returns expected structure."""
        response = await async_client.get("/contracts/789012/usage/hourly")

        assert response.status_code == 200
        data = response.json()
        assert "date" in data
        assert "hours" in data
        assert isinstance(data["hours"], list)

    @pytest.mark.asyncio
    async def test_get_hourly_usage_with_date(
        self, async_client: AsyncClient, mock_contact_api
    ):
        """Test getting hourly usage with specific date."""
        response = await async_client.get(
            "/contracts/789012/usage/hourly?date=2026-02-04"
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_monthly_usage(self, async_client: AsyncClient, mock_contact_api):
        """Test getting monthly usage returns expected structure."""
        response = await async_client.get(
            "/contracts/789012/usage/monthly?start=2026-01&end=2026-02"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == "789012"
        assert data["start_month"] == "2026-01"
        assert data["end_month"] == "2026-02"
        assert "months" in data

    @pytest.mark.asyncio
    async def test_get_monthly_usage_invalid_format(
        self, async_client: AsyncClient, mock_contact_api
    ):
        """Test that invalid month format returns 422."""
        response = await async_client.get(
            "/contracts/789012/usage/monthly?start=2026-1&end=2026-02"
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_summary(self, async_client: AsyncClient, mock_contact_api):
        """Test getting usage summary returns expected structure."""
        response = await async_client.get("/contracts/789012/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == "789012"
        assert "today" in data
        assert "yesterday" in data
        assert "this_month" in data
        assert "last_month" in data
        assert "comparisons" in data
