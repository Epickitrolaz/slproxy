"""
Tests for Router API (/routerapi)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import time
from typing import AsyncGenerator, Tuple

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from slproxy.core.account_router import AccountRouter
from slproxy.core.key_authenticator import KeyAuthenticator
from slproxy.core.metrics import MetricsManager
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest, ProxyResponse
from slproxy.core.plugin_manager import PluginManager
from slproxy.core.proxy_engine import ProxyEngine
from slproxy.db.database import Database
from slproxy.main import app

pytestmark = pytest.mark.asyncio(loop_scope="function")


class DummyOpenAIPlugin(BasePlugin):
    id = "dummyopenai"
    name = "Dummy OpenAI"
    default_base_url = "https://dummy.openai"
    format = "openai"
    models = [
        ModelInfo(id="dummy-gpt", name="Dummy GPT"),
        ModelInfo(id="dummy-embed", name="Dummy Embed"),
    ]


class DummyAnthropicPlugin(BasePlugin):
    id = "dummyanthropic"
    name = "Dummy Anthropic"
    default_base_url = "https://dummy.anthropic"
    format = "anthropic"
    models = [
        ModelInfo(id="claude-3-test", name="Claude 3 Test")
    ]


class MockProxyEngine(ProxyEngine):
    def __init__(self):
        super().__init__()
        self.request_history = []
        self.fail_account_ids = set()

    async def execute_request(
        self,
        plugin: BasePlugin,
        account: Account,
        request: ProxyRequest,
    ) -> ProxyResponse:
        self.request_history.append((account.id, request))
        if account.id in self.fail_account_ids:
            return ProxyResponse(
                status_code=429,
                headers={"retry-after": "30"},
                raw_text=json.dumps({"error": {"message": "Rate limit reached", "code": 429}}),
                body={"error": {"message": "Rate limit reached", "code": 429}},
            )

        if "embeddings" in request.url:
            return ProxyResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body={"object": "list", "data": [{"embedding": [0.1, 0.2, 0.3], "index": 0}], "usage": {"prompt_tokens": 5, "total_tokens": 5}},
            )

        if plugin.format == "anthropic":
            return ProxyResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body={
                    "id": "msg_test123",
                    "type": "message",
                    "role": "assistant",
                    "model": request.model,
                    "content": [{"type": "text", "text": "Anthropic response"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 12, "output_tokens": 8},
                },
            )

        return ProxyResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body={
                "id": "chatcmpl-test123",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"Hello from account {account.id}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            },
        )

    async def execute_stream(
        self,
        plugin: BasePlugin,
        account: Account,
        request: ProxyRequest,
    ) -> Tuple[int, dict, AsyncGenerator[bytes, None]]:
        self.request_history.append((account.id, request))
        if account.id in self.fail_account_ids:
            async def err_stream():
                yield json.dumps({"error": "Rate limit"}).encode("utf-8")
            return 429, {"retry-after": "30"}, err_stream()

        async def ok_stream():
            if plugin.format == "anthropic":
                msg = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "streamed anthropic"}}
                yield f"event: content_block_delta\ndata: {json.dumps(msg)}\n\n".encode("utf-8")
            else:
                chunk = {
                    "id": "chatcmpl-chunk",
                    "choices": [{"delta": {"content": f"streamed from {account.id}"}}],
                }
                yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"

        return 200, {"content-type": "text/event-stream"}, ok_stream()


@pytest_asyncio.fixture(loop_scope="function")
async def setup_app(tmp_path: Path):
    db_path = tmp_path / "test_router.db"
    db = Database(db_path)
    await db.connect()

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    pm = PluginManager(plugins_dir)

    dummy_openai = DummyOpenAIPlugin()
    dummy_anthropic = DummyAnthropicPlugin()
    pm.plugins[dummy_openai.id] = dummy_openai
    pm.plugins[dummy_anthropic.id] = dummy_anthropic

    account_router = AccountRouter()
    key_auth = KeyAuthenticator()
    key_auth.db = db
    mock_proxy = MockProxyEngine()
    metrics = MetricsManager()

    app.state.db = db
    app.state.plugin_manager = pm
    app.state.account_router = account_router
    app.state.key_authenticator = key_auth
    app.state.proxy_engine = mock_proxy
    app.state.metrics_manager = metrics

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "db": db,
            "pm": pm,
            "proxy_engine": mock_proxy,
            "metrics": metrics,
        }

    await db.close()


async def test_health(setup_app):
    client = setup_app["client"]
    resp = await client.get("/routerapi/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "SLProxy", "version": "1.0.0"}


async def test_models_list(setup_app):
    client = setup_app["client"]
    resp = await client.get("/routerapi/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    model_ids = [m["id"] for m in data["data"]]
    assert "dummy-gpt" in model_ids
    assert "dummyopenai/dummy-gpt" in model_ids
    assert "claude-3-test" in model_ids


async def test_chat_completions_non_streaming(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1)"
    )
    await db.conn.commit()

    payload = {
        "model": "dummyopenai/dummy-gpt",
        "messages": [{"role": "user", "content": "Hello!"}],
        "stream": False,
    }
    resp = await client.post("/routerapi/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
    assert data["choices"][0]["message"]["content"] == "Hello from account acc1"

    # Verify telemetry
    metrics = setup_app["metrics"]
    summary = metrics.get_summary()
    assert summary["total_requests"] == 1
    assert summary["total_errors"] == 0
    assert summary["total_tokens"] == 16


async def test_chat_completions_streaming(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1)"
    )
    await db.conn.commit()

    payload = {
        "model": "dummy-gpt",
        "messages": [{"role": "user", "content": "Hello streaming!"}],
        "stream": True,
    }
    resp = await client.post("/routerapi/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "streamed from acc1" in body


async def test_chat_completions_streaming_fallback_on_429(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]
    proxy_engine = setup_app["proxy_engine"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, priority, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1, 1)"
    )
    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, priority, is_active) VALUES ('acc2', 'dummyopenai', 'Acc 2', 'key2', 2, 1)"
    )
    await db.conn.commit()

    proxy_engine.fail_account_ids.add("acc1")

    payload = {
        "model": "dummy-gpt",
        "messages": [{"role": "user", "content": "Test streaming fallback"}],
        "stream": True,
    }
    resp = await client.post("/routerapi/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    assert "streamed from acc2" in resp.text


async def test_chat_completions_account_fallback_on_429(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]
    proxy_engine = setup_app["proxy_engine"]

    # Insert 2 accounts: acc1 (priority 1) and acc2 (priority 2)
    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, priority, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1, 1)"
    )
    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, priority, is_active) VALUES ('acc2', 'dummyopenai', 'Acc 2', 'key2', 2, 1)"
    )
    await db.conn.commit()

    # Configure acc1 to fail with 429
    proxy_engine.fail_account_ids.add("acc1")

    payload = {
        "model": "dummy-gpt",
        "messages": [{"role": "user", "content": "Test fallback"}],
        "stream": False,
    }
    resp = await client.post("/routerapi/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # It must have fallen back to acc2!
    assert data["choices"][0]["message"]["content"] == "Hello from account acc2"

    # Verify acc1 in DB was marked rate limited
    async with db.conn.execute("SELECT rate_limited_until, error_count FROM accounts WHERE id = 'acc1'") as cur:
        row = await cur.fetchone()
        assert row["rate_limited_until"] is not None
        assert row["error_count"] >= 1

    # Verify acc2 in DB was marked success
    async with db.conn.execute("SELECT success_count FROM accounts WHERE id = 'acc2'") as cur:
        row = await cur.fetchone()
        assert row["success_count"] >= 1


async def test_chat_completions_all_accounts_exhausted_returns_503(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]
    proxy_engine = setup_app["proxy_engine"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1)"
    )
    await db.conn.commit()

    proxy_engine.fail_account_ids.add("acc1")

    payload = {
        "model": "dummy-gpt",
        "messages": [{"role": "user", "content": "Will fail"}],
        "stream": False,
    }
    resp = await client.post("/routerapi/v1/chat/completions", json=payload)
    assert resp.status_code in (429, 503)


async def test_anthropic_messages_direct_and_translated(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc_ant', 'dummyanthropic', 'Anthropic Acc', 'antkey', 1)"
    )
    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc_oai', 'dummyopenai', 'OpenAI Acc', 'oaikey', 1)"
    )
    await db.conn.commit()

    # 1. Direct Anthropic plugin call
    resp = await client.post(
        "/routerapi/v1/messages",
        json={
            "model": "claude-3-test",
            "messages": [{"role": "user", "content": "Hi Claude"}],
            "stream": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["content"][0]["text"] == "Anthropic response"

    # 2. Translated Anthropic call (routed to dummyopenai)
    resp2 = await client.post(
        "/routerapi/v1/messages",
        json={
            "model": "dummyopenai/dummy-gpt",
            "system": "You are a test helper",
            "messages": [{"role": "user", "content": "Translate me"}],
            "stream": False,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["type"] == "message"
    assert "Hello from account acc_oai" in data2["content"][0]["text"]

    # 3. Anthropic streaming call (direct)
    resp3 = await client.post(
        "/routerapi/v1/messages",
        json={
            "model": "claude-3-test",
            "messages": [{"role": "user", "content": "Stream Anthropic"}],
            "stream": True,
        },
    )
    assert resp3.status_code == 200
    assert "streamed anthropic" in resp3.text

    # 4. Anthropic streaming call (translated from OpenAI)
    resp4 = await client.post(
        "/routerapi/v1/messages",
        json={
            "model": "dummyopenai/dummy-gpt",
            "messages": [{"role": "user", "content": "Stream Translated"}],
            "stream": True,
        },
    )
    assert resp4.status_code == 200
    assert "content_block_delta" in resp4.text
    assert "streamed from acc_oai" in resp4.text


async def test_root_fallback(setup_app, monkeypatch, tmp_path):
    client = setup_app["client"]
    # When index.html exists, it serves HTML WebUI
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower() or "slproxy" in resp.text.lower()

    # When index.html does not exist, it falls back to JSON status
    from slproxy import main
    monkeypatch.setattr(main, "web_dir", tmp_path / "empty_web")
    resp_fallback = await client.get("/")
    assert resp_fallback.status_code == 200
    data = resp_fallback.json()
    assert data["message"] == "SLProxy is running."
    assert "router_api" in data


async def test_embeddings(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1)"
    )
    await db.conn.commit()

    resp = await client.post(
        "/routerapi/v1/embeddings",
        json={"model": "dummy-embed", "input": "Hello embedding"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["embedding"] == [0.1, 0.2, 0.3]


async def test_auth_enforcement_and_usage(setup_app):
    client = setup_app["client"]
    db = setup_app["db"]

    await db.conn.execute(
        "INSERT INTO accounts (id, provider_id, name, api_key, is_active) VALUES ('acc1', 'dummyopenai', 'Acc 1', 'key1', 1)"
    )
    secret = "slp-live-testkey123"
    await db.conn.execute(
        """INSERT INTO api_keys (id, key, name, created_at, is_active, max_requests, used_requests)
        VALUES ('k1', ?, 'Test Key', ?, 1, 5, 0)""",
        (secret, time.time()),
    )
    await db.conn.commit()

    # 1. Missing auth header -> 401
    resp_no_auth = await client.post(
        "/routerapi/v1/chat/completions",
        json={"model": "dummy-gpt", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp_no_auth.status_code == 401

    # 2. Invalid auth header -> 401
    resp_bad_auth = await client.post(
        "/routerapi/v1/chat/completions",
        headers={"Authorization": "Bearer bad-key"},
        json={"model": "dummy-gpt", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp_bad_auth.status_code == 401

    # 3. Valid auth header -> 200
    resp_ok = await client.post(
        "/routerapi/v1/chat/completions",
        headers={"Authorization": f"Bearer {secret}"},
        json={"model": "dummy-gpt", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert resp_ok.status_code == 200

    # 4. Verify used_requests incremented in DB
    async with db.conn.execute("SELECT used_requests, used_tokens FROM api_keys WHERE id = 'k1'") as cur:
        row = await cur.fetchone()
        assert row["used_requests"] == 1
        assert row["used_tokens"] == 16
