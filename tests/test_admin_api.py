"""
Tests for Admin API (/api)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from slproxy.core.account_router import AccountRouter
from slproxy.core.key_authenticator import KeyAuthenticator
from slproxy.core.metrics import MetricsManager, RequestLog
from slproxy.core.plugin_base import BasePlugin, ModelInfo
from slproxy.core.plugin_manager import PluginManager
from slproxy.core.proxy_engine import ProxyEngine
from slproxy.db.database import Database
from slproxy.main import app

pytestmark = pytest.mark.asyncio(loop_scope="function")


class SampleProviderPlugin(BasePlugin):
    id = "sampleplugin"
    name = "Sample Provider"
    default_base_url = "https://sample.provider"
    format = "openai"
    models = [
        ModelInfo(id="sample-model", name="Sample Model")
    ]


@pytest_asyncio.fixture(loop_scope="function")
async def setup_admin_app(tmp_path: Path):
    db_path = tmp_path / "test_admin.db"
    db = Database(db_path)
    await db.connect()

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    pm = PluginManager(plugins_dir)

    sample_plugin = SampleProviderPlugin()
    pm.plugins[sample_plugin.id] = sample_plugin

    account_router = AccountRouter()
    key_auth = KeyAuthenticator()
    key_auth.db = db
    proxy_engine = ProxyEngine()
    metrics = MetricsManager()

    app.state.db = db
    app.state.plugin_manager = pm
    app.state.account_router = account_router
    app.state.key_authenticator = key_auth
    app.state.proxy_engine = proxy_engine
    app.state.metrics_manager = metrics

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "db": db,
            "pm": pm,
            "metrics": metrics,
            "plugins_dir": plugins_dir,
        }

    await db.close()


async def test_get_plugins(setup_admin_app):
    client = setup_admin_app["client"]
    db = setup_admin_app["db"]

    # Add an account for sampleplugin
    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc1', 'sampleplugin', 'Acc 1', 'key1', 1)"
    )
    await db.conn.commit()

    resp = await client.get("/api/plugins")
    assert resp.status_code == 200
    plugins = resp.json()
    assert len(plugins) >= 1
    tp = next(p for p in plugins if p["id"] == "sampleplugin")
    assert tp["name"] == "Sample Provider"
    assert tp["enabled"] is True
    assert tp["account_count"] == 1
    assert len(tp["models"]) == 1
    assert tp["models"][0]["id"] == "sample-model"


async def test_toggle_plugin(setup_admin_app):
    client = setup_admin_app["client"]
    db = setup_admin_app["db"]
    pm = setup_admin_app["pm"]

    # Initially enabled
    assert pm.plugins["sampleplugin"].enabled is True

    # Toggle off
    resp = await client.post("/api/plugins/sampleplugin/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert pm.plugins["sampleplugin"].enabled is False

    # Check DB
    async with db.conn.execute("SELECT enabled FROM plugin_settings WHERE plugin_id = 'sampleplugin'") as cur:
        row = await cur.fetchone()
        assert row["enabled"] == 0

    # Toggle back on
    resp2 = await client.post("/api/plugins/sampleplugin/toggle")
    assert resp2.status_code == 200
    assert resp2.json()["enabled"] is True
    assert pm.plugins["sampleplugin"].enabled is True


async def test_get_and_update_plugin_code_hot_reload(setup_admin_app):
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]

    # 1. Get code
    resp_get = await client.get("/api/plugins/sampleplugin/code")
    assert resp_get.status_code == 200
    assert "code" in resp_get.json()

    # 2. Update code with hot-reload
    new_code = '''
from slproxy.core.plugin_base import BasePlugin, ModelInfo

class UpdatedPlugin(BasePlugin):
    id = "sampleplugin"
    name = "Hot Reloaded Provider"
    default_base_url = "https://updated.provider"
    format = "openai"
    models = [
        ModelInfo(id="updated-model-v2", name="Updated Model V2")
    ]
'''
    resp_post = await client.post("/api/plugins/sampleplugin/code", json={"code": new_code})
    assert resp_post.status_code == 200
    data = resp_post.json()
    assert data["status"] == "deployed"

    # Verify hot reload modified the live plugin in memory immediately
    reloaded = pm.plugins["sampleplugin"]
    assert reloaded.name == "Hot Reloaded Provider"
    assert len(reloaded.models) == 1
    assert reloaded.models[0].id == "updated-model-v2"

    # Test error handling on invalid code syntax
    bad_code_resp = await client.post("/api/plugins/sampleplugin/code", json={"code": "def bad_syntax(:"})
    assert bad_code_resp.status_code == 400


async def test_create_custom_plugin(setup_admin_app):
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]

    # Test error handling on invalid code syntax
    bad_create_resp = await client.post(
        "/api/plugins/create",
        json={"id": "bad-plugin", "name": "Bad Plugin", "code": "def broken(:"},
    )
    assert bad_create_resp.status_code == 400

    payload = {
        "id": "custom-ollama",
        "name": "Custom Ollama",
    }
    resp = await client.post("/api/plugins/create", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"

    # Verify plugin is now registered in plugin manager
    assert "custom-ollama" in pm.plugins
    assert pm.plugins["custom-ollama"].name == "Custom Ollama"


async def test_accounts_crud(setup_admin_app):
    client = setup_admin_app["client"]

    # 1. Create account
    create_payload = {
        "provider_id": "sampleplugin",
        "name": "Primary Account",
        "api_key": "sk-secret-123",
        "base_url": "https://api.custom.com/v1",
        "priority": 1,
        "weight": 2,
        "extra_headers": {"X-Custom": "val"},
        "extra_config": {"retries": 3},
    }
    resp_create = await client.post("/api/accounts", json=create_payload)
    assert resp_create.status_code == 201
    created_acc = resp_create.json()
    acc_id = created_acc["id"]
    assert created_acc["name"] == "Primary Account"
    assert created_acc["extra_headers"] == {"X-Custom": "val"}

    # 2. List accounts
    resp_list = await client.get("/api/accounts")
    assert resp_list.status_code == 200
    accounts = resp_list.json()
    assert len(accounts) == 1
    assert accounts[0]["id"] == acc_id

    # List with provider filter
    resp_filter = await client.get("/api/accounts?provider_id=sampleplugin")
    assert resp_filter.status_code == 200
    assert len(resp_filter.json()) == 1

    resp_filter_empty = await client.get("/api/accounts?provider_id=nonexistent")
    assert resp_filter_empty.status_code == 200
    assert len(resp_filter_empty.json()) == 0

    # 3. Update account
    update_payload = {
        "name": "Updated Account Name",
        "priority": 5,
    }
    resp_update = await client.put(f"/api/accounts/{acc_id}", json=update_payload)
    assert resp_update.status_code == 200
    updated_acc = resp_update.json()
    assert updated_acc["name"] == "Updated Account Name"
    assert updated_acc["priority"] == 5

    # 4. Delete account
    resp_delete = await client.delete(f"/api/accounts/{acc_id}")
    assert resp_delete.status_code == 200
    assert resp_delete.json()["status"] == "deleted"

    # Verify deleted
    resp_check = await client.get("/api/accounts")
    assert len(resp_check.json()) == 0


async def test_reset_account_cooldown(setup_admin_app):
    client = setup_admin_app["client"]
    db = setup_admin_app["db"]

    # Insert account with rate limit and errors
    await db.conn.execute(
        """INSERT INTO accounts 
        (id, provider_id, name, api_key, is_active, rate_limited_until, error_count)
        VALUES ('acc_cd', 'sampleplugin', 'CD Account', 'key', 1, ?, 7)""",
        (time.time() + 300,),
    )
    await db.conn.commit()

    resp = await client.post("/api/accounts/acc_cd/reset-cooldown")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify cleared in DB
    async with db.conn.execute("SELECT rate_limited_until, error_count FROM accounts WHERE id = 'acc_cd'") as cur:
        row = await cur.fetchone()
        assert row["rate_limited_until"] is None
        assert row["error_count"] == 0


async def test_keys_crud(setup_admin_app):
    client = setup_admin_app["client"]

    # 1. Create Key
    key_payload = {
        "name": "Team Dev Key",
        "max_requests": 100,
        "max_tokens": 50000,
        "allowed_plugins": ["sampleplugin"],
    }
    resp_create = await client.post("/api/keys", json=key_payload)
    assert resp_create.status_code == 201
    created_key = resp_create.json()
    key_id = created_key["id"]
    assert created_key["name"] == "Team Dev Key"
    assert created_key["key"].startswith("slp-live-")
    assert created_key["allowed_plugins"] == ["sampleplugin"]

    # 2. List Keys
    resp_list = await client.get("/api/keys")
    assert resp_list.status_code == 200
    keys = resp_list.json()
    assert len(keys) == 1
    assert keys[0]["id"] == key_id

    # 3. Delete Key
    resp_del = await client.delete(f"/api/keys/{key_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"

    # Verify deleted
    resp_after = await client.get("/api/keys")
    assert len(resp_after.json()) == 0


async def test_metrics_and_logs(setup_admin_app):
    client = setup_admin_app["client"]
    metrics: MetricsManager = setup_admin_app["metrics"]
    db: Database = setup_admin_app["db"]

    log1 = RequestLog(
        id="log-1",
        endpoint="/routerapi/v1/chat/completions",
        model="sample-model",
        provider_id="sampleplugin",
        status_code=200,
        latency_ms=120.5,
        total_tokens=42,
    )
    log2 = RequestLog(
        id="log-2",
        endpoint="/routerapi/v1/chat/completions",
        model="sample-model",
        provider_id="sampleplugin",
        status_code=500,
        latency_ms=80.0,
        error="Server error",
    )
    metrics.record_request(log1)
    metrics.record_request(log2)

    # 1. Check Metrics endpoint
    resp_metrics = await client.get("/api/metrics")
    assert resp_metrics.status_code == 200
    m_data = resp_metrics.json()
    assert m_data["total_requests"] == 2
    assert m_data["total_errors"] == 1
    assert m_data["total_tokens"] == 42
    assert "sampleplugin" in m_data["provider_stats"]

    # 2. Check Logs endpoint
    resp_logs = await client.get("/api/logs?limit=10")
    assert resp_logs.status_code == 200
    logs = resp_logs.json()
    assert len(logs) == 2
    assert logs[0]["id"] in ("log-1", "log-2")


async def test_templates_and_plugin_deletion(setup_admin_app):
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]

    # 1. Get templates list
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 9
    template_ids = {t["id"] for t in templates}
    assert "openai_compatible" in template_ids
    assert "moonmath_zro" in template_ids

    # 2. Install template
    install_resp = await client.post("/api/templates/openai_compatible/install")
    assert install_resp.status_code == 200
    assert install_resp.json()["status"] == "installed"

    # Verify plugin is now active
    plugins_resp = await client.get("/api/plugins")
    assert any(p["id"] == "openai_compatible" for p in plugins_resp.json())

    # 3. Delete plugin
    del_resp = await client.delete("/api/plugins/openai_compatible")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify plugin is removed
    plugins_resp_after = await client.get("/api/plugins")
    assert not any(p["id"] == "openai_compatible" for p in plugins_resp_after.json())
