"""Data access layer for usage data."""

from datetime import datetime
from typing import Any

from app.db.database import get_database
from app.models import UsageData


class UsageRepository:
    """Repository for usage data operations."""

    def __init__(self):
        """Initialize repository with database instance."""
        self.db = get_database()

    async def upsert_usage(
        self,
        contract_id: str,
        date: datetime,
        interval: str,
        value: float,
        unit: str,
        dollar_value: float | None = None,
        offpeak_value: float | None = None,
        offpeak_dollar_value: float | None = None,
        uncharged_value: float | None = None,
    ) -> None:
        """Insert or update usage data."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO usage_data 
                    (contract_id, date, interval, value, unit, dollar_value, 
                     offpeak_value, offpeak_dollar_value, uncharged_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contract_id, date, interval) DO UPDATE SET
                    value = excluded.value,
                    unit = excluded.unit,
                    dollar_value = excluded.dollar_value,
                    offpeak_value = excluded.offpeak_value,
                    offpeak_dollar_value = excluded.offpeak_dollar_value,
                    uncharged_value = excluded.uncharged_value
                """,
                (
                    contract_id,
                    date.isoformat(),
                    interval,
                    value,
                    unit,
                    dollar_value,
                    offpeak_value,
                    offpeak_dollar_value,
                    uncharged_value,
                ),
            )
            await conn.commit()

    async def get_usage(
        self,
        contract_id: str,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> list[UsageData]:
        """Get usage data for a date range."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT date, value, unit, dollar_value, offpeak_value, 
                       offpeak_dollar_value, uncharged_value
                FROM usage_data
                WHERE contract_id = ? 
                  AND date >= ? 
                  AND date <= ?
                  AND interval = ?
                ORDER BY date ASC
                """,
                (contract_id, start_date.isoformat(), end_date.isoformat(), interval),
            )
            rows = await cursor.fetchall()

            return [
                UsageData(
                    date=datetime.fromisoformat(row["date"]),
                    value=row["value"],
                    unit=row["unit"],
                    dollar_value=row["dollar_value"],
                    offpeak_value=row["offpeak_value"],
                    offpeak_dollar_value=row["offpeak_dollar_value"],
                    uncharged_value=row["uncharged_value"],
                )
                for row in rows
            ]

    async def get_usage_for_date(
        self,
        contract_id: str,
        date: datetime,
        interval: str,
    ) -> UsageData | None:
        """Get usage data for a specific date."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT date, value, unit, dollar_value, offpeak_value, 
                       offpeak_dollar_value, uncharged_value
                FROM usage_data
                WHERE contract_id = ? 
                  AND date LIKE ?
                  AND interval = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (contract_id, f"{date.strftime('%Y-%m-%d')}%", interval),
            )
            row = await cursor.fetchone()

            if row is None:
                return None

            return UsageData(
                date=datetime.fromisoformat(row["date"]),
                value=row["value"],
                unit=row["unit"],
                dollar_value=row["dollar_value"],
                offpeak_value=row["offpeak_value"],
                offpeak_dollar_value=row["offpeak_dollar_value"],
                uncharged_value=row["uncharged_value"],
            )


class AccountRepository:
    """Repository for account and contract operations."""

    def __init__(self):
        """Initialize repository with database instance."""
        self.db = get_database()

    async def upsert_account(self, account_id: str) -> None:
        """Insert or update an account."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO accounts (account_id)
                VALUES (?)
                ON CONFLICT(account_id) DO NOTHING
                """,
                (account_id,),
            )
            await conn.commit()

    async def upsert_contract(self, contract_id: str, account_id: str) -> None:
        """Insert or update a contract."""
        async with self.db.connection() as conn:
            # Ensure account exists
            await conn.execute(
                """
                INSERT INTO accounts (account_id)
                VALUES (?)
                ON CONFLICT(account_id) DO NOTHING
                """,
                (account_id,),
            )

            await conn.execute(
                """
                INSERT INTO contracts (contract_id, account_id)
                VALUES (?, ?)
                ON CONFLICT(contract_id) DO UPDATE SET
                    account_id = excluded.account_id
                """,
                (contract_id, account_id),
            )
            await conn.commit()

    async def get_all_contracts(self) -> list[dict[str, Any]]:
        """Get all stored contracts with their accounts."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT contract_id, account_id
                FROM contracts
                ORDER BY account_id, contract_id
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def contract_exists(self, contract_id: str) -> bool:
        """Check if a contract exists."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM contracts WHERE contract_id = ?",
                (contract_id,),
            )
            row = await cursor.fetchone()
            return row is not None
