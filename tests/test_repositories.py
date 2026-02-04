"""Tests for database repositories."""

from datetime import datetime

import pytest
import pytest_asyncio

from app.db.database import Database
from app.db.repositories import AccountRepository, UsageRepository


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    await database.init()
    return database


@pytest_asyncio.fixture
async def usage_repo(db):
    """Create a usage repository with test database."""
    repo = UsageRepository()
    repo.db = db  # Inject test database
    return repo


@pytest_asyncio.fixture
async def account_repo(db):
    """Create an account repository with test database."""
    repo = AccountRepository()
    repo.db = db  # Inject test database
    return repo


class TestUsageRepository:
    """Tests for the usage repository."""

    @pytest.mark.asyncio
    async def test_upsert_and_get_usage(self, usage_repo, db):
        """Test inserting and retrieving usage data."""
        # Insert data
        await usage_repo.upsert_usage(
            contract_id="123",
            date=datetime(2026, 2, 4, 10, 0),
            interval="hourly",
            value=5.5,
            unit="kWh",
            dollar_value=1.65,
        )

        # Retrieve data
        result = await usage_repo.get_usage(
            contract_id="123",
            start_date=datetime(2026, 2, 4, 0, 0),
            end_date=datetime(2026, 2, 4, 23, 59),
            interval="hourly",
        )

        assert len(result) == 1
        assert result[0].value == 5.5
        assert result[0].unit == "kWh"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, usage_repo, db):
        """Test that upsert updates existing records."""
        # Insert initial data
        await usage_repo.upsert_usage(
            contract_id="123",
            date=datetime(2026, 2, 4, 10, 0),
            interval="hourly",
            value=5.5,
            unit="kWh",
        )

        # Update with new value
        await usage_repo.upsert_usage(
            contract_id="123",
            date=datetime(2026, 2, 4, 10, 0),
            interval="hourly",
            value=7.5,
            unit="kWh",
            dollar_value=2.25,
        )

        # Retrieve data
        result = await usage_repo.get_usage(
            contract_id="123",
            start_date=datetime(2026, 2, 4, 0, 0),
            end_date=datetime(2026, 2, 4, 23, 59),
            interval="hourly",
        )

        assert len(result) == 1
        assert result[0].value == 7.5
        assert result[0].dollar_value == 2.25

    @pytest.mark.asyncio
    async def test_get_usage_for_date(self, usage_repo, db):
        """Test getting usage for a specific date."""
        # Insert data
        await usage_repo.upsert_usage(
            contract_id="123",
            date=datetime(2026, 2, 4, 10, 0),
            interval="hourly",
            value=5.5,
            unit="kWh",
        )

        # Get for specific date
        result = await usage_repo.get_usage_for_date(
            contract_id="123",
            date=datetime(2026, 2, 4),
            interval="hourly",
        )

        assert result is not None
        assert result.value == 5.5


class TestAccountRepository:
    """Tests for the account repository."""

    @pytest.mark.asyncio
    async def test_upsert_contract(self, account_repo, db):
        """Test inserting a contract creates account and contract."""
        await account_repo.upsert_contract("contract123", "account456")

        exists = await account_repo.contract_exists("contract123")
        assert exists is True

    @pytest.mark.asyncio
    async def test_get_all_contracts(self, account_repo, db):
        """Test getting all contracts."""
        await account_repo.upsert_contract("contract1", "account1")
        await account_repo.upsert_contract("contract2", "account1")
        await account_repo.upsert_contract("contract3", "account2")

        contracts = await account_repo.get_all_contracts()

        assert len(contracts) == 3
        assert any(c["contract_id"] == "contract1" for c in contracts)
        assert any(c["contract_id"] == "contract2" for c in contracts)
        assert any(c["contract_id"] == "contract3" for c in contracts)

    @pytest.mark.asyncio
    async def test_contract_not_exists(self, account_repo, db):
        """Test checking for non-existent contract."""
        exists = await account_repo.contract_exists("nonexistent")
        assert exists is False
