"""
Async SQLite Database Manager for SLProxy
"""

import json
import uuid
from pathlib import Path
from typing import List, Optional, Union
import aiosqlite

from slproxy.config import DB_PATH
from slproxy.db.models import Account, ApiKey, CREATE_TABLES_SQL, RequestLog


def _row_to_account(row: aiosqlite.Row) -> Account:
    extra_headers = {}
    if row["extra_headers"]:
        try:
            extra_headers = json.loads(row["extra_headers"])
        except Exception:
            pass
    extra_config = {}
    if row["extra_config"]:
        try:
            extra_config = json.loads(row["extra_config"])
        except Exception:
            pass
    return Account(
        id=row["id"],
        provider_id=row["provider_id"],
        name=row["name"],
        api_key=row["api_key"] or "",
        base_url=row["base_url"],
        extra_headers=extra_headers,
        extra_config=extra_config,
        priority=row["priority"] if row["priority"] is not None else 1,
        weight=row["weight"] if row["weight"] is not None else 1,
        is_active=bool(row["is_active"]),
        rate_limited_until=row["rate_limited_until"],
        error_count=row["error_count"] or 0,
        success_count=row["success_count"] or 0,
        last_used_at=row["last_used_at"],
    )


def _row_to_api_key(row: aiosqlite.Row) -> ApiKey:
    allowed_plugins = []
    if row["allowed_plugins"]:
        try:
            allowed_plugins = json.loads(row["allowed_plugins"])
        except Exception:
            pass
    allowed_models = []
    if row["allowed_models"]:
        try:
            allowed_models = json.loads(row["allowed_models"])
        except Exception:
            pass
    extra_metadata = {}
    if row["extra_metadata"]:
        try:
            extra_metadata = json.loads(row["extra_metadata"])
        except Exception:
            pass
    return ApiKey(
        id=row["id"],
        key=row["key"],
        name=row["name"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        max_requests=row["max_requests"],
        max_tokens=row["max_tokens"],
        used_requests=row["used_requests"] or 0,
        used_tokens=row["used_tokens"] or 0,
        is_active=bool(row["is_active"]),
        allowed_plugins=allowed_plugins,
        allowed_models=allowed_models,
        extra_metadata=extra_metadata,
    )


def _row_to_request_log(row: aiosqlite.Row) -> RequestLog:
    return RequestLog(
        id=row["id"],
        timestamp=row["timestamp"],
        client_ip=row["client_ip"] or "",
        api_key_id=row["api_key_id"],
        endpoint=row["endpoint"],
        model=row["model"] or "",
        provider_id=row["provider_id"] or "",
        account_id=row["account_id"] or "",
        status_code=row["status_code"] if row["status_code"] is not None else 200,
        latency_ms=row["latency_ms"] if row["latency_ms"] is not None else 0.0,
        prompt_tokens=row["prompt_tokens"] or 0,
        completion_tokens=row["completion_tokens"] or 0,
        total_tokens=row["total_tokens"] or 0,
        is_stream=bool(row["is_stream"]),
        error=row["error"],
    )


class Database:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path or DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if not self._conn:
            path_str = str(self.db_path)
            if path_str != ":memory:" and isinstance(self.db_path, Path):
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(path_str)
            self._conn.row_factory = aiosqlite.Row
            await self.init_tables()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_tables(self):
        async with self.conn.cursor() as cursor:
            await cursor.executescript(CREATE_TABLES_SQL)
        await self.conn.commit()

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # --------------------------------------------------------------------------
    # Account CRUD
    # --------------------------------------------------------------------------

    async def create_account(self, account: Account) -> Account:
        if not account.id:
            account.id = f"acc_{uuid.uuid4().hex[:12]}"
        sql = """
        INSERT INTO accounts (
            id, provider_id, name, api_key, base_url, extra_headers, extra_config,
            priority, weight, is_active, rate_limited_until, error_count, success_count, last_used_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            account.id,
            account.provider_id,
            account.name,
            account.api_key,
            account.base_url,
            json.dumps(account.extra_headers),
            json.dumps(account.extra_config),
            account.priority,
            account.weight,
            1 if account.is_active else 0,
            account.rate_limited_until,
            account.error_count,
            account.success_count,
            account.last_used_at,
        )
        async with self.conn.execute(sql, params):
            await self.conn.commit()
        return account

    async def get_account(self, account_id: str) -> Optional[Account]:
        sql = "SELECT * FROM accounts WHERE id = ?"
        async with self.conn.execute(sql, (account_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_account(row)
        return None

    async def list_accounts(self, provider_id: Optional[str] = None) -> List[Account]:
        if provider_id:
            sql = "SELECT * FROM accounts WHERE provider_id = ? ORDER BY priority ASC, id ASC"
            params = (provider_id,)
        else:
            sql = "SELECT * FROM accounts ORDER BY priority ASC, id ASC"
            params = ()
        async with self.conn.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_account(r) for r in rows]

    async def update_account(self, account: Account) -> Account:
        sql = """
        UPDATE accounts SET
            provider_id = ?, name = ?, api_key = ?, base_url = ?,
            extra_headers = ?, extra_config = ?, priority = ?, weight = ?,
            is_active = ?, rate_limited_until = ?, error_count = ?,
            success_count = ?, last_used_at = ?
        WHERE id = ?
        """
        params = (
            account.provider_id,
            account.name,
            account.api_key,
            account.base_url,
            json.dumps(account.extra_headers),
            json.dumps(account.extra_config),
            account.priority,
            account.weight,
            1 if account.is_active else 0,
            account.rate_limited_until,
            account.error_count,
            account.success_count,
            account.last_used_at,
            account.id,
        )
        async with self.conn.execute(sql, params):
            await self.conn.commit()
        return account

    async def delete_account(self, account_id: str) -> bool:
        sql = "DELETE FROM accounts WHERE id = ?"
        async with self.conn.execute(sql, (account_id,)) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    # --------------------------------------------------------------------------
    # API Key CRUD
    # --------------------------------------------------------------------------

    async def create_api_key(self, api_key: ApiKey) -> ApiKey:
        if not api_key.id:
            api_key.id = f"key_{uuid.uuid4().hex[:12]}"
        sql = """
        INSERT INTO api_keys (
            id, key, name, created_at, expires_at, max_requests, max_tokens,
            used_requests, used_tokens, is_active, allowed_plugins, allowed_models, extra_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            api_key.id,
            api_key.key,
            api_key.name,
            api_key.created_at,
            api_key.expires_at,
            api_key.max_requests,
            api_key.max_tokens,
            api_key.used_requests,
            api_key.used_tokens,
            1 if api_key.is_active else 0,
            json.dumps(api_key.allowed_plugins),
            json.dumps(api_key.allowed_models),
            json.dumps(api_key.extra_metadata),
        )
        async with self.conn.execute(sql, params):
            await self.conn.commit()
        return api_key

    async def get_api_key(self, key_id: str) -> Optional[ApiKey]:
        sql = "SELECT * FROM api_keys WHERE id = ?"
        async with self.conn.execute(sql, (key_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_api_key(row)
        return None

    async def get_api_key_by_key(self, raw_key: str) -> Optional[ApiKey]:
        sql = "SELECT * FROM api_keys WHERE key = ?"
        async with self.conn.execute(sql, (raw_key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_api_key(row)
        return None

    async def list_api_keys(self) -> List[ApiKey]:
        sql = "SELECT * FROM api_keys ORDER BY created_at DESC"
        async with self.conn.execute(sql) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_api_key(r) for r in rows]

    async def update_api_key(self, api_key: ApiKey) -> ApiKey:
        sql = """
        UPDATE api_keys SET
            key = ?, name = ?, created_at = ?, expires_at = ?,
            max_requests = ?, max_tokens = ?, used_requests = ?, used_tokens = ?,
            is_active = ?, allowed_plugins = ?, allowed_models = ?, extra_metadata = ?
        WHERE id = ?
        """
        params = (
            api_key.key,
            api_key.name,
            api_key.created_at,
            api_key.expires_at,
            api_key.max_requests,
            api_key.max_tokens,
            api_key.used_requests,
            api_key.used_tokens,
            1 if api_key.is_active else 0,
            json.dumps(api_key.allowed_plugins),
            json.dumps(api_key.allowed_models),
            json.dumps(api_key.extra_metadata),
            api_key.id,
        )
        async with self.conn.execute(sql, params):
            await self.conn.commit()
        return api_key

    async def delete_api_key(self, key_id: str) -> bool:
        sql = "DELETE FROM api_keys WHERE id = ?"
        async with self.conn.execute(sql, (key_id,)) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    async def increment_key_usage(self, key_id: str, requests_inc: int = 1, tokens_inc: int = 0) -> None:
        sql = """
        UPDATE api_keys
        SET used_requests = used_requests + ?,
            used_tokens = used_tokens + ?
        WHERE id = ?
        """
        async with self.conn.execute(sql, (requests_inc, tokens_inc, key_id)):
            await self.conn.commit()

    # --------------------------------------------------------------------------
    # Request Logs
    # --------------------------------------------------------------------------

    async def insert_request_log(self, log: RequestLog) -> RequestLog:
        if not log.id:
            log.id = f"log_{uuid.uuid4().hex[:12]}"
        sql = """
        INSERT INTO request_logs (
            id, timestamp, client_ip, api_key_id, endpoint, model, provider_id,
            account_id, status_code, latency_ms, prompt_tokens, completion_tokens,
            total_tokens, is_stream, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            log.id,
            log.timestamp,
            log.client_ip,
            log.api_key_id,
            log.endpoint,
            log.model,
            log.provider_id,
            log.account_id,
            log.status_code,
            log.latency_ms,
            log.prompt_tokens,
            log.completion_tokens,
            log.total_tokens,
            1 if log.is_stream else 0,
            log.error,
        )
        async with self.conn.execute(sql, params):
            await self.conn.commit()
        return log

    async def get_request_log(self, log_id: str) -> Optional[RequestLog]:
        sql = "SELECT * FROM request_logs WHERE id = ?"
        async with self.conn.execute(sql, (log_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return _row_to_request_log(row)
        return None

    async def delete_request_log(self, log_id: str) -> bool:
        sql = "DELETE FROM request_logs WHERE id = ?"
        async with self.conn.execute(sql, (log_id,)) as cursor:
            await self.conn.commit()
            return cursor.rowcount > 0

    async def list_request_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        provider_id: Optional[str] = None,
        api_key_id: Optional[str] = None
    ) -> List[RequestLog]:
        conditions = []
        params = []
        if provider_id:
            conditions.append("provider_id = ?")
            params.append(provider_id)
        if api_key_id:
            conditions.append("api_key_id = ?")
            params.append(api_key_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"SELECT * FROM request_logs {where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.conn.execute(sql, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_request_log(r) for r in rows]
