"""Pytest fixtures and configuration for tests."""

from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.database import Database
from app.main import app
from app.models import UsageData


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("app.config.get_settings") as mock:
        settings = MagicMock()
        settings.username = "test@example.com"
        settings.password = "testpassword"
        settings.cache_ttl_minutes = 15
        settings.database_path = ":memory:"
        settings.host = "0.0.0.0"
        settings.port = 8000
        mock.return_value = settings
        yield settings


@pytest.fixture
def sample_usage_data() -> list[UsageData]:
    """Sample usage data for testing."""
    return [
        UsageData(
            date=datetime(2026, 2, 4, 0, 0),
            value=1.5,
            unit="kWh",
            dollar_value=0.45,
            offpeak_value=0.5,
            offpeak_dollar_value=0.10,
            uncharged_value=None,
        ),
        UsageData(
            date=datetime(2026, 2, 4, 1, 0),
            value=1.2,
            unit="kWh",
            dollar_value=0.36,
            offpeak_value=0.4,
            offpeak_dollar_value=0.08,
            uncharged_value=None,
        ),
    ]


@pytest.fixture
def mock_contact_api():
    """Mock the ContactEnergyApi class."""
    with patch("app.services.contact_api.ContactEnergyApi") as mock_cls:
        mock_api = AsyncMock()
        mock_api.account_id = "123456"
        mock_api.contract_id = "789012"
        mock_api.token = "mock_token"

        # Mock from_credentials to return the mock API
        mock_cls.from_credentials = AsyncMock(return_value=mock_api)

        # Mock account_summary
        mock_api.account_summary = AsyncMock()

        # Mock usage methods
        mock_api.get_hourly_usage = AsyncMock(return_value=[])
        mock_api.get_usage = AsyncMock(return_value=[])
        mock_api.get_latest_usage = AsyncMock(return_value=None)

        yield mock_api


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[Database, None]:
    """Create an in-memory database for testing."""
    db = Database(":memory:")
    await db.init()
    yield db


@pytest_asyncio.fixture
async def async_client(mock_settings, mock_contact_api) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing endpoints."""
    # Patch database to use in-memory
    with patch("app.db.database.get_settings") as db_settings_mock:
        db_settings_mock.return_value = mock_settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
