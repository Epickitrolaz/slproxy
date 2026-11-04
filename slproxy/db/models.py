"""
Database schema and models
"""

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
