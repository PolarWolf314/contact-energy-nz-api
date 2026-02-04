"""SQLite database setup and connection management."""

import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import get_settings

# SQL schema for usage data
SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    date TEXT NOT NULL,
    interval TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    dollar_value REAL,
    offpeak_value REAL,
    offpeak_dollar_value REAL,
    uncharged_value REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contract_id, date, interval)
);

CREATE INDEX IF NOT EXISTS idx_usage_lookup 
ON usage_data(contract_id, date, interval);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

CREATE INDEX IF NOT EXISTS idx_contracts_account 
ON contracts(account_id);
"""


class Database:
    """Database connection manager.
    
    For in-memory databases (:memory:), a persistent connection is maintained
    since each new connection to :memory: creates a separate database.
    """

    def __init__(self, db_path: str | None = None):
        """Initialize database with optional custom path."""
        self.db_path = db_path or get_settings().database_path
        self._initialized = False
        self._is_memory = self.db_path == ":memory:"
        self._persistent_conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Initialize the database schema."""
        if self._initialized:
            return

        if self._is_memory:
            # For in-memory databases, keep a persistent connection
            self._persistent_conn = await aiosqlite.connect(self.db_path)
            self._persistent_conn.row_factory = aiosqlite.Row
            await self._persistent_conn.executescript(SCHEMA)
            await self._persistent_conn.commit()
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(SCHEMA)
                await db.commit()

        self._initialized = True

    async def close(self) -> None:
        """Close the database connection (for in-memory databases)."""
        if self._persistent_conn:
            await self._persistent_conn.close()
            self._persistent_conn = None
            self._initialized = False

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a database connection context manager."""
        if not self._initialized:
            await self.init()

        if self._is_memory and self._persistent_conn:
            # For in-memory databases, reuse the persistent connection
            yield self._persistent_conn
        else:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                yield db


# Global database instance
_database: Database | None = None


def get_database() -> Database:
    """Get the global database instance."""
    global _database
    if _database is None:
        _database = Database()
    return _database


async def init_database() -> None:
    """Initialize the global database."""
    db = get_database()
    await db.init()
