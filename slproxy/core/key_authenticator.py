"""
Key Authenticator for SLProxy
"""

import secrets
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from slproxy.db.database import Database
from slproxy.db.models import ApiKey


class KeyAuthenticator:
    """
    Validates incoming request API keys against expiration,
    request limits, token limits, and model/provider restrictions.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db

    async def create_key(
        self,
        name: str = "Default Key",
        expires_at: Optional[float] = None,
        max_requests: Optional[int] = None,
        max_tokens: Optional[int] = None,
        allowed_plugins: Optional[List[str]] = None,
        allowed_models: Optional[List[str]] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
        key: Optional[str] = None,
        id: Optional[str] = None,
    ) -> ApiKey:
        """
        Generates secure random key slp-live-<32 hex> and saves to database.
        """
        raw_key = key or f"slp-live-{secrets.token_hex(16)}"
        key_id = id or f"key_{uuid.uuid4().hex[:12]}"

        api_key = ApiKey(
            id=key_id,
            key=raw_key,
            name=name,
            created_at=time.time(),
            expires_at=expires_at,
            max_requests=max_requests,
            max_tokens=max_tokens,
            used_requests=0,
            used_tokens=0,
            is_active=is_active,
            allowed_plugins=allowed_plugins or [],
            allowed_models=allowed_models or [],
            extra_metadata=extra_metadata or {},
        )

        if self.db:
            await self.db.create_api_key(api_key)

        return api_key

    async def authenticate(
        self,
        auth_header: Optional[str],
        requested_model: str = "",
        plugin_id: str = "",
    ) -> ApiKey:
        """
        Authenticates an incoming request:
        - Extracts token from `Bearer <key>` or raw key.
        - Checks `is_active`. If False, raises 401 Unauthorized.
        - Checks `expires_at`. If expired, raises 401 Unauthorized.
        - Checks `max_requests`. If `used_requests >= max_requests`, raises 429 Quota Exceeded.
        - Checks `max_tokens`. If `used_tokens >= max_tokens`, raises 429 Quota Exceeded.
        - Checks `allowed_plugins` and `allowed_models` if non-empty. If restricted, raises 403 Forbidden.
        """
        if not auth_header or not auth_header.strip():
            raise HTTPException(status_code=401, detail="Unauthorized: Missing API key")

        token = auth_header.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid API key format")

        if not self.db:
            raise HTTPException(status_code=500, detail="Database not configured")

        api_key = await self.db.get_api_key_by_key(token)
        if not api_key:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid API key")

        if not api_key.is_active:
            raise HTTPException(status_code=401, detail="Unauthorized: API key is inactive")

        if api_key.expires_at is not None and api_key.expires_at <= time.time():
            raise HTTPException(status_code=401, detail="Unauthorized: API key has expired")

        if api_key.max_requests is not None and api_key.used_requests >= api_key.max_requests:
            raise HTTPException(status_code=429, detail="Quota Exceeded: Request limit reached")

        if api_key.max_tokens is not None and api_key.used_tokens >= api_key.max_tokens:
            raise HTTPException(status_code=429, detail="Quota Exceeded: Token limit reached")

        if api_key.allowed_plugins and plugin_id:
            if plugin_id not in api_key.allowed_plugins:
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: Plugin '{plugin_id}' not allowed for this API key",
                )

        if api_key.allowed_models and requested_model:
            if requested_model not in api_key.allowed_models:
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: Model '{requested_model}' not allowed for this API key",
                )

        return api_key

    async def record_usage(self, key_id: str, requests_inc: int = 1, tokens_inc: int = 0):
        """
        Updates SQLite usage counters atomically.
        """
        if self.db:
            await self.db.increment_key_usage(key_id, requests_inc=requests_inc, tokens_inc=tokens_inc)
