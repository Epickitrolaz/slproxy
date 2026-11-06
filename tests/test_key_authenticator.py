"""
Tests for KeyAuthenticator and Database Key/Account/Log Operations
"""

import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from fastapi import HTTPException
from slproxy.core.key_authenticator import KeyAuthenticator
from slproxy.db.database import Database
from slproxy.db.models import Account, ApiKey, RequestLog


@pytest_asyncio.fixture(loop_scope="function")
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture(loop_scope="function")
async def auth(db):
    return KeyAuthenticator(db)


@pytest.mark.asyncio
async def test_create_key_format_and_persistence(auth, db):
    """
    create_key generates key matching `slp-live-<32 hex>` and persists to DB.
    """
    key_obj = await auth.create_key(name="test_key")
    assert key_obj.key.startswith("slp-live-")
    hex_part = key_obj.key[len("slp-live-"):]
    assert len(hex_part) == 32
    int(hex_part, 16)  # Verify hex characters

    # Verify retrieval from db
    saved_key = await db.get_api_key(key_obj.id)
    assert saved_key is not None
    assert saved_key.key == key_obj.key
    assert saved_key.name == "test_key"
    assert saved_key.is_active is True

    # Verify lookup by raw key
    by_key = await db.get_api_key_by_key(key_obj.key)
    assert by_key is not None
    assert by_key.id == key_obj.id


@pytest.mark.asyncio
async def test_authenticate_valid_key_bearer_and_raw(auth):
    """
    authenticate succeeds with both Bearer header and raw token.
    """
    key_obj = await auth.create_key(name="valid_key")

    # With Bearer prefix
    res1 = await auth.authenticate(f"Bearer {key_obj.key}")
    assert res1.id == key_obj.id

    # With lowercase bearer prefix
    res2 = await auth.authenticate(f"bearer {key_obj.key}")
    assert res2.id == key_obj.id

    # Raw key without prefix
    res3 = await auth.authenticate(key_obj.key)
    assert res3.id == key_obj.id


@pytest.mark.asyncio
async def test_authenticate_missing_or_invalid_key(auth):
    """
    authenticate raises 401 when key is missing, empty, or unknown.
    """
    with pytest.raises(HTTPException) as exc_none:
        await auth.authenticate(None)
    assert exc_none.value.status_code == 401

    with pytest.raises(HTTPException) as exc_empty:
        await auth.authenticate("")
    assert exc_empty.value.status_code == 401

    with pytest.raises(HTTPException) as exc_bearer_only:
        await auth.authenticate("Bearer ")
    assert exc_bearer_only.value.status_code == 401

    with pytest.raises(HTTPException) as exc_unknown:
        await auth.authenticate("Bearer slp-live-0123456789abcdef0123456789abcdef")
    assert exc_unknown.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_inactive_key(auth):
    """
    authenticate raises 401 Unauthorized if is_active is False.
    """
    key_obj = await auth.create_key(name="inactive_key", is_active=False)

    with pytest.raises(HTTPException) as exc:
        await auth.authenticate(key_obj.key)
    assert exc.value.status_code == 401
    assert "inactive" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_authenticate_expired_key(auth):
    """
    authenticate raises 401 Unauthorized if expires_at is in the past.
    """
    # Key expired 10 seconds ago
    past_time = time.time() - 10.0
    key_obj = await auth.create_key(name="expired_key", expires_at=past_time)

    with pytest.raises(HTTPException) as exc:
        await auth.authenticate(key_obj.key)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()

    # Key expiring in future succeeds
    future_time = time.time() + 3600.0
    valid_key = await auth.create_key(name="future_key", expires_at=future_time)
    res = await auth.authenticate(valid_key.key)
    assert res.id == valid_key.id


@pytest.mark.asyncio
async def test_authenticate_request_quota_limit(auth, db):
    """
    authenticate raises 429 Quota Exceeded when used_requests >= max_requests.
    """
    key_obj = await auth.create_key(name="req_limit_key", max_requests=2)

    # First request: 0 < 2 -> succeeds
    res1 = await auth.authenticate(key_obj.key)
    assert res1.id == key_obj.id
    await auth.record_usage(key_obj.id, requests_inc=1)

    # Second request: 1 < 2 -> succeeds
    res2 = await auth.authenticate(key_obj.key)
    assert res2.id == key_obj.id
    await auth.record_usage(key_obj.id, requests_inc=1)

    # Third request: 2 >= 2 -> raises 429
    with pytest.raises(HTTPException) as exc:
        await auth.authenticate(key_obj.key)
    assert exc.value.status_code == 429
    assert "quota exceeded" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_authenticate_token_quota_limit(auth, db):
    """
    authenticate raises 429 Quota Exceeded when used_tokens >= max_tokens.
    """
    key_obj = await auth.create_key(name="token_limit_key", max_tokens=1000)

    # Authenticate before reaching quota -> succeeds
    res = await auth.authenticate(key_obj.key)
    assert res.id == key_obj.id

    # Record 999 tokens used
    await auth.record_usage(key_obj.id, requests_inc=1, tokens_inc=999)
    res = await auth.authenticate(key_obj.key)
    assert res.id == key_obj.id

    # Record 1 more token -> total 1000 >= 1000
    await auth.record_usage(key_obj.id, requests_inc=0, tokens_inc=1)
    with pytest.raises(HTTPException) as exc:
        await auth.authenticate(key_obj.key)
    assert exc.value.status_code == 429
    assert "quota exceeded" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_authenticate_restricted_plugins(auth):
    """
    authenticate raises 403 Forbidden when requested plugin is not in allowed_plugins.
    """
    key_obj = await auth.create_key(
        name="plugin_scoped_key",
        allowed_plugins=["openai", "anthropic"],
    )

    # Allowed plugin
    res = await auth.authenticate(key_obj.key, plugin_id="openai")
    assert res.id == key_obj.id

    res = await auth.authenticate(key_obj.key, plugin_id="anthropic")
    assert res.id == key_obj.id

    # Restricted plugin
    with pytest.raises(HTTPException) as exc:
        await auth.authenticate(key_obj.key, plugin_id="zro")
    assert exc.value.status_code == 403
    assert "forbidden" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_authenticate_restricted_models(auth):
    """
    authenticate raises 403 Forbidden when requested model is not in allowed_models.
    """
    key_obj = await auth.create_key(
        name="model_scoped_key",
        allowed_models=["gpt-4o", "claude-3-5-sonnet"],
    )

    # Allowed model
    res = await auth.authenticate(key_obj.key, requested_model="gpt-4o")
    assert res.id == key_obj.id

    # Restricted model
    with pytest.raises(HTTPException) as exc:
        await auth.authenticate(key_obj.key, requested_model="deepseek-v3")
    assert exc.value.status_code == 403
    assert "forbidden" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_record_usage_atomic_increments(auth, db):
    """
    record_usage correctly and atomically increments requests and tokens.
    """
    key_obj = await auth.create_key(name="usage_key")

    await auth.record_usage(key_obj.id, requests_inc=1, tokens_inc=150)
    updated = await db.get_api_key(key_obj.id)
    assert updated.used_requests == 1
    assert updated.used_tokens == 150

    await auth.record_usage(key_obj.id, requests_inc=4, tokens_inc=350)
    updated = await db.get_api_key(key_obj.id)
    assert updated.used_requests == 5
    assert updated.used_tokens == 500


@pytest.mark.asyncio
async def test_database_crud_accounts_and_logs(db):
    """
    Full verification of CRUD operations for accounts and request logs in Database.
    """
    # 1. Create account
    account = Account(
        id="acc_crud_1",
        provider_id="prov_test",
        name="Test Provider Account",
        api_key="sk-secret",
        base_url="https://api.example.com/v1",
        extra_headers={"X-Custom": "val"},
        extra_config={"route": "fast"},
        priority=1,
        weight=2,
    )
    created = await db.create_account(account)
    assert created.id == "acc_crud_1"

    # 2. Read account
    fetched = await db.get_account("acc_crud_1")
    assert fetched is not None
    assert fetched.name == "Test Provider Account"
    assert fetched.extra_headers == {"X-Custom": "val"}
    assert fetched.extra_config == {"route": "fast"}
    assert fetched.is_active is True

    # 3. List accounts
    accounts = await db.list_accounts(provider_id="prov_test")
    assert len(accounts) == 1
    assert accounts[0].id == "acc_crud_1"

    # 4. Update account
    fetched.name = "Renamed Account"
    fetched.error_count = 3
    updated = await db.update_account(fetched)
    assert updated.name == "Renamed Account"
    assert updated.error_count == 3

    # 5. Delete account
    deleted = await db.delete_account("acc_crud_1")
    assert deleted is True
    assert await db.get_account("acc_crud_1") is None

    # 6. Request logs CRUD
    log = RequestLog(
        id="log_1",
        client_ip="127.0.0.1",
        endpoint="/v1/chat/completions",
        model="gpt-4o",
        provider_id="openai",
        account_id="acc_1",
        status_code=200,
        latency_ms=145.2,
        prompt_tokens=50,
        completion_tokens=25,
        total_tokens=75,
        is_stream=True,
    )
    inserted = await db.insert_request_log(log)
    assert inserted.id == "log_1"

    fetched_log = await db.get_request_log("log_1")
    assert fetched_log is not None
    assert fetched_log.latency_ms == 145.2
    assert fetched_log.is_stream is True

    logs_list = await db.list_request_logs(provider_id="openai")
    assert len(logs_list) == 1
    assert logs_list[0].id == "log_1"

    # Delete log
    deleted_log = await db.delete_request_log("log_1")
    assert deleted_log is True
    assert await db.get_request_log("log_1") is None
