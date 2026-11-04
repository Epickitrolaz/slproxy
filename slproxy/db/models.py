"""
Database schema and models
"""

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Re-export Account from plugin_base to keep a single definition of Account
from slproxy.core.plugin_base import Account


class ApiKey(BaseModel):
    id: str
    key: str  # e.g. "slp-live-..."
    name: str
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None  # None = never expires
    max_requests: Optional[int] = None
    max_tokens: Optional[int] = None
    used_requests: int = 0
    used_tokens: int = 0
    is_active: bool = True
    allowed_plugins: List[str] = Field(default_factory=list)  # empty = all allowed
    allowed_models: List[str] = Field(default_factory=list)   # empty = all allowed
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class RequestLog(BaseModel):
    id: str
    timestamp: float = Field(default_factory=time.time)
    client_ip: str = ""
    api_key_id: Optional[str] = None
    endpoint: str = ""
    model: str = ""
    provider_id: str = ""
    account_id: str = ""
    status_code: int = 200
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    is_stream: bool = False
    error: Optional[str] = None


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    name TEXT NOT NULL,
    api_key TEXT DEFAULT '',
    base_url TEXT,
    extra_headers TEXT DEFAULT '{}',
    extra_config TEXT DEFAULT '{}',
    priority INTEGER DEFAULT 1,
    weight INTEGER DEFAULT 1,
    is_active INTEGER DEFAULT 1,
    rate_limited_until REAL,
    error_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_used_at REAL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL,
    max_requests INTEGER,
    max_tokens INTEGER,
    used_requests INTEGER DEFAULT 0,
    used_tokens INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    allowed_plugins TEXT DEFAULT '[]',
    allowed_models TEXT DEFAULT '[]',
    extra_metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS request_logs (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    client_ip TEXT,
    api_key_id TEXT,
    endpoint TEXT NOT NULL,
    model TEXT,
    provider_id TEXT,
    account_id TEXT,
    status_code INTEGER,
    latency_ms REAL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    is_stream INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS plugin_settings (
    plugin_id TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    custom_code TEXT,
    updated_at REAL
);
"""
