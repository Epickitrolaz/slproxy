"""
Async SQLite Database Manager for SLProxy
"""

import aiosqlite
from pathlib import Path
from typing import Optional
from slproxy.config import DB_PATH
from slproxy.db.models import CREATE_TABLES_SQL


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if not self._conn:
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self.init_tables()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_tables(self):
        async with self._conn.cursor() as cursor:
            await cursor.executescript(CREATE_TABLES_SQL)
        await self._conn.commit()

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn
