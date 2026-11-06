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

    def __init__(self):
        super().__init__()
        self.models = [
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
            "proxy_engine": proxy_engine,
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
    assert len(templates) >= 7
    template_ids = {t["id"] for t in templates}
    assert "openai_compatible" in template_ids

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


async def test_plugin_models_add_and_delete(setup_admin_app):
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]
    db = setup_admin_app["db"]

    # 1. Add model to sampleplugin
    model_payload = {
        "id": "sample-pro-model",
        "name": "Sample Pro Model",
        "context_window": 128000,
        "max_output_tokens": 8192,
        "supports_streaming": True,
        "supports_tools": True,
        "supports_vision": True,
        "pricing": {"prompt": 0.005, "completion": 0.015},
    }

    add_resp = await client.post("/api/plugins/sampleplugin/models", json=model_payload)
    assert add_resp.status_code == 200
    add_data = add_resp.json()
    assert add_data["status"] == "added"
    assert add_data["model"]["id"] == "sample-pro-model"
    assert add_data["model"]["name"] == "Sample Pro Model"
    assert add_data["model"]["context_window"] == 128000
    assert add_data["model"]["supports_vision"] is True

    # Verify in live plugin instance
    sample_plugin = pm.plugins["sampleplugin"]
    assert any(m.id == "sample-pro-model" for m in sample_plugin.models)

    # Verify in GET /api/plugins
    plugins_resp = await client.get("/api/plugins")
    assert plugins_resp.status_code == 200
    tp = next(p for p in plugins_resp.json() if p["id"] == "sampleplugin")
    model_ids = [m["id"] for m in tp["models"]]
    assert "sample-pro-model" in model_ids

    # 2. Add model to non-existent plugin returns 404
    bad_add_resp = await client.post("/api/plugins/nonexistent/models", json=model_payload)
    assert bad_add_resp.status_code == 404

    # 3. Delete model from sampleplugin
    del_resp = await client.delete("/api/plugins/sampleplugin/models/sample-pro-model")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"status": "removed", "model_id": "sample-pro-model"}

    # Verify removed from live plugin instance
    assert not any(m.id == "sample-pro-model" for m in sample_plugin.models)

    # Verify in GET /api/plugins
    plugins_resp_after = await client.get("/api/plugins")
    tp_after = next(p for p in plugins_resp_after.json() if p["id"] == "sampleplugin")
    model_ids_after = [m["id"] for m in tp_after["models"]]
    assert "sample-pro-model" not in model_ids_after

    # 4. Delete non-existent model returns 404
    bad_del_resp = await client.delete("/api/plugins/sampleplugin/models/already-deleted-model")
    assert bad_del_resp.status_code == 404

    # 5. Delete model from non-existent plugin returns 404
    bad_del_plugin_resp = await client.delete("/api/plugins/nonexistent/models/some-model")
    assert bad_del_plugin_resp.status_code == 404


async def test_account_level_model_overrides_in_router(setup_admin_app):
    client = setup_admin_app["client"]
    db = setup_admin_app["db"]

    # Insert an account with custom model overrides
    account_payload = {
        "provider_id": "sampleplugin",
        "name": "Account With Models",
        "api_key": "sk-override-123",
        "extra_config": {
            "models": [
                {"id": "account-override-model", "name": "Account Override Model"},
                "account-string-model",
            ]
        },
    }
    resp = await client.post("/api/accounts", json=account_payload)
    assert resp.status_code == 201

    # Verify GET /routerapi/v1/models includes the account-level overridden models
    models_resp = await client.get("/routerapi/v1/models")
    assert models_resp.status_code == 200
    models_data = models_resp.json()["data"]
    model_ids = {m["id"] for m in models_data}
    assert "account-override-model" in model_ids
    assert "account-string-model" in model_ids
    assert "sampleplugin/account-override-model" in model_ids


async def test_plugin_models_persistence_across_reload(setup_admin_app):
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]
    db = setup_admin_app["db"]

    # 1. Add model via Admin API
    payload = {
        "id": "persisted-restart-model",
        "name": "Persisted Restart Model",
        "context_window": 64000,
    }
    add_resp = await client.post("/api/plugins/sampleplugin/models", json=payload)
    assert add_resp.status_code == 200

    # 2. Simulate server restart: reset in-memory plugin to initial models
    fresh_plugin = SampleProviderPlugin()
    assert not any(m.id == "persisted-restart-model" for m in fresh_plugin.models)
    pm.plugins["sampleplugin"] = fresh_plugin

    # 3. Verify router API restores persisted models from SQLite
    models_resp = await client.get("/routerapi/v1/models")
    assert models_resp.status_code == 200
    model_ids = {m["id"] for m in models_resp.json()["data"]}
    assert "persisted-restart-model" in model_ids

    # 4. Verify admin API also reflects persisted models
    plugins_resp = await client.get("/api/plugins")
    assert plugins_resp.status_code == 200
    sample_p = next(p for p in plugins_resp.json() if p["id"] == "sampleplugin")
    assert any(m["id"] == "persisted-restart-model" for m in sample_p["models"])


async def test_account_level_model_overrides_priority_filtering(setup_admin_app):
    from slproxy.api.router_api import filter_accounts_for_model
    pm = setup_admin_app["pm"]
    client = setup_admin_app["client"]
    db = setup_admin_app["db"]

    plugin = pm.plugins["sampleplugin"]

    # Acc 1: Priority 1 (higher priority), default models (no overrides)
    acc1_payload = {
        "provider_id": "sampleplugin",
        "name": "Default Priority 1",
        "api_key": "sk-acc1",
        "priority": 1,
        "extra_config": {},
    }
    resp1 = await client.post("/api/accounts", json=acc1_payload)
    assert resp1.status_code == 201
    acc1_id = resp1.json()["id"]

    # Acc 2: Priority 2 (lower priority), custom overridden model
    acc2_payload = {
        "provider_id": "sampleplugin",
        "name": "Special Priority 2",
        "api_key": "sk-acc2",
        "priority": 2,
        "extra_config": {"models": ["special-exclusive-model"]},
    }
    resp2 = await client.post("/api/accounts", json=acc2_payload)
    assert resp2.status_code == 201
    acc2_id = resp2.json()["id"]

    accounts = await db.list_accounts("sampleplugin")
    assert len(accounts) >= 2

    # Verify filter_accounts_for_model routes special-exclusive-model strictly to Acc 2
    filtered_special = filter_accounts_for_model(plugin, accounts, "special-exclusive-model")
    assert len(filtered_special) == 1
    assert filtered_special[0].id == acc2_id

    # Verify default plugin model routes strictly to Acc 1
    filtered_default = filter_accounts_for_model(plugin, accounts, "sample-model")
    assert any(a.id == acc1_id for a in filtered_default)
    assert not any(a.id == acc2_id for a in filtered_default)

    # Verify chat completion with special-exclusive-model successfully resolves and executes strictly via Acc 2
    from slproxy.core.plugin_base import ProxyResponse
    routed_accounts = []
    async def mock_execute(plugin_arg, account_arg, req_arg):
        routed_accounts.append(account_arg.id)
        return ProxyResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body={"id": "chatcmpl-test", "choices": [{"message": {"role": "assistant", "content": "Hello"}}]},
        )
    setup_admin_app["proxy_engine"].execute_request = mock_execute

    chat_resp = await client.post(
        "/routerapi/v1/chat/completions",
        json={
            "model": "special-exclusive-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        },
    )
    assert chat_resp.status_code == 200
    assert "choices" in chat_resp.json()
    assert routed_accounts == [acc2_id]

# -----------------------------------------------------------------------------
# Editor code pipeline (Issue #16): code in plugin list, template fallbacks
# -----------------------------------------------------------------------------

async def test_get_plugins_includes_code_and_code_available(setup_admin_app):
    """Plugin entries expose code/code_available when source is on disk."""
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]
    plugins_dir = setup_admin_app["plugins_dir"]

    # Give the sample plugin a real source file on disk (the fixture registers
    # the instance in-memory only).
    (plugins_dir / "sampleplugin.py").write_text(
        "from slproxy.core.plugin_base import BasePlugin\n\n"
        "class SampleProviderPlugin(BasePlugin):\n"
        "    id = \"sampleplugin\"\n"
        "    name = \"Sample Provider\"\n",
        encoding="utf-8",
    )
    pm.plugin_files["sampleplugin"] = plugins_dir / "sampleplugin.py"

    resp = await client.get("/api/plugins")
    assert resp.status_code == 200
    plugins = resp.json()
    assert len(plugins) >= 1
    entry = next(p for p in plugins if p["id"] == "sampleplugin")
    assert entry.get("code_available") is True
    assert isinstance(entry.get("code"), str)
    assert "BasePlugin" in entry["code"]


async def test_get_plugin_code_for_uninstalled_template(setup_admin_app):
    """GET /api/plugins/{id}/code must work for templates that are not installed."""
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]

    assert "google_antigravity" not in pm.plugins
    resp = await client.get("/api/plugins/google_antigravity/code")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "google_antigravity"
    assert "BasePlugin" in data["code"]
    assert '"google_antigravity"' in data["code"]
    # Real template source, not the synthesized fallback
    assert data.get("fallback") is not True


async def test_get_plugin_code_unknown_id_returns_template_fallback(setup_admin_app):
    """Unknown ids degrade to a marked synthesized template, never a 404."""
    client = setup_admin_app["client"]

    resp = await client.get("/api/plugins/definitely_not_a_real_plugin/code")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "definitely_not_a_real_plugin"
    assert "definitely_not_a_real_plugin" in data["code"]
    assert data["fallback"] is True


async def test_deploy_code_installs_uninstalled_template_plugin(setup_admin_app):
    """Save & Deploy on a template id installs it: subsequent listing includes it."""
    client = setup_admin_app["client"]
    pm = setup_admin_app["pm"]

    assert "google_antigravity" not in pm.plugins

    code = '''
from slproxy.core.plugin_base import BasePlugin, ModelInfo

class AntigravityDeployed(BasePlugin):
    id = "google_antigravity"
    name = "Google Antigravity (deployed)"
    default_base_url = "https://deployed.google"
    format = "openai"
    models = [ModelInfo(id="gemini-deployed", name="Gemini Deployed")]
'''
    resp = await client.post("/api/plugins/google_antigravity/code", json={"code": code})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deployed"
    assert "google_antigravity" in pm.plugins

    listing = await client.get("/api/plugins")
    ids = {p["id"] for p in listing.json()}
    assert "google_antigravity" in ids
