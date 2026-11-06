"""
Tests for ProxyEngine
"""

import sys
import json
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
import httpx
from slproxy.core.plugin_base import Account, BasePlugin, ErrorCheckResult, ProxyRequest, ProxyResponse
from slproxy.core.proxy_engine import ProxyEngine


class MockPlugin(BasePlugin):
    id = "mock_provider"
    name = "Mock Provider"


class FinalizeStreamPlugin(BasePlugin):
    id = "finalize_stream"
    name = "Finalize Stream Provider"

    def finalize_stream(self, account: Account, metadata: Optional[dict] = None) -> bytes:
        return b"data: [DONE]\n\n"


class AsyncFinalizeStreamPlugin(BasePlugin):
    id = "async_finalize_stream"
    name = "Async Finalize Stream Provider"

    async def finalize_stream(self, account: Account, metadata: Optional[dict] = None) -> bytes:
        return b"data: [DONE]\n\n"


class CustomTransformPlugin(BasePlugin):
    id = "custom_transform"
    name = "Custom Transform Provider"

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        new_headers = dict(request.headers)
        new_headers["X-Custom-Injected"] = "SLProxy-Injected"
        return ProxyRequest(
            method=request.method,
            url=request.url + "/transformed",
            headers=new_headers,
            body={"transformed": True, "original": request.body},
            is_stream=request.is_stream,
            model=request.model,
        )

    def transform_response(self, response: ProxyResponse, account: Account) -> ProxyResponse:
        response.headers["X-Custom-Response"] = "Hook-Applied"
        if isinstance(response.body, dict):
            response.body["transformed_by_plugin"] = True
        return response

    def transform_stream_chunk(self, chunk: bytes, account: Account) -> bytes:
        # Replace 'chunk' with '[TRANSFORMED]'
        text = chunk.decode("utf-8").replace("hello", "greetings")
        return text.encode("utf-8")


@pytest_asyncio.fixture(loop_scope="function")
async def account():
    return Account(
        id="acc_test",
        provider_id="mock_provider",
        name="Test Account",
        api_key="sk-test-key",
        base_url="https://api.mock.test/v1",
    )


@pytest.mark.asyncio
async def test_execute_request_success(account):
    """
    Test standard non-streaming proxy request upstream.
    """
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["method"] = request.method
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"id": "chatcmpl-123", "choices": [{"message": {"content": "Hello!"}}]},
            headers={"content-type": "application/json", "x-upstream-id": "up-999"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = ProxyEngine(client=client)
        plugin = MockPlugin()

        proxy_req = ProxyRequest(
            method="POST",
            url="https://api.mock.test/v1/chat/completions",
            headers={"authorization": "Bearer sk-test-key", "content-type": "application/json"},
            body={"model": "mock-model", "messages": [{"role": "user", "content": "Hi"}]},
            is_stream=False,
            model="mock-model",
        )

        response = await engine.execute_request(plugin, account, proxy_req)

        assert response.status_code == 200
        assert response.headers["x-upstream-id"] == "up-999"
        assert response.body["id"] == "chatcmpl-123"
        assert "choices" in response.body
        assert "Hello!" in response.raw_text
        assert "error_check" in response.metadata
        assert response.metadata["error_check"].is_error is False

        # Verify captured upstream request
        assert captured_request["method"] == "POST"
        assert captured_request["url"] == "https://api.mock.test/v1/chat/completions"
        assert captured_request["body"]["model"] == "mock-model"


@pytest.mark.asyncio
async def test_execute_request_transform_hooks(account):
    """
    Test that plugin.transform_request and plugin.transform_response are invoked.
    """
    captured_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"result": "ok"},
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = ProxyEngine(client=client)
        plugin = CustomTransformPlugin()

        proxy_req = ProxyRequest(
            method="POST",
            url="https://api.mock.test/v1/action",
            headers={"content-type": "application/json"},
            body={"original_data": 42},
            is_stream=False,
        )

        response = await engine.execute_request(plugin, account, proxy_req)

        # Verify transform_request effects on upstream call
        assert captured_request["url"] == "https://api.mock.test/v1/action/transformed"
        assert captured_request["headers"]["x-custom-injected"] == "SLProxy-Injected"
        assert captured_request["body"]["transformed"] is True
        assert captured_request["body"]["original"] == {"original_data": 42}

        # Verify transform_response effects on final response
        assert response.headers["X-Custom-Response"] == "Hook-Applied"
        assert response.body["transformed_by_plugin"] is True


@pytest.mark.asyncio
async def test_execute_request_detect_error_or_limit(account):
    """
    Test that plugin.detect_error_or_limit detects rate limits and errors.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit reached"}},
            headers={"retry-after": "45"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = ProxyEngine(client=client)
        plugin = MockPlugin()

        proxy_req = ProxyRequest(
            method="POST",
            url="https://api.mock.test/v1/chat/completions",
            body={},
        )

        response = await engine.execute_request(plugin, account, proxy_req)
        assert response.status_code == 429
        error_check = response.metadata.get("error_check")
        assert error_check is not None
        assert error_check.is_error is True
        assert error_check.is_rate_limited is True
        assert error_check.cooldown_seconds == 45.0
        assert error_check.should_fallback is True


@pytest.mark.asyncio
async def test_execute_stream_forwarding(account):
    """
    Test streaming SSE proxying and chunk reception.
    """
    stream_chunks = [
        b'data: {"choices": [{"delta": {"content": "hello"}}]}\n\n',
        b'data: {"choices": [{"delta": {"content": " world"}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(stream_chunks),
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = ProxyEngine(client=client)
        plugin = MockPlugin()

        proxy_req = ProxyRequest(
            method="POST",
            url="https://api.mock.test/v1/chat/completions",
            headers={"accept": "text/event-stream"},
            body={"stream": True},
            is_stream=True,
        )

        status_code, headers, stream_gen = await engine.execute_stream(plugin, account, proxy_req)

        assert status_code == 200
        assert headers["content-type"] == "text/event-stream"

        received = []
        async for chunk in stream_gen:
            received.append(chunk)

        combined = b"".join(received)
        assert b"hello" in combined
        assert b" world" in combined
        assert b"[DONE]" in combined


@pytest.mark.asyncio
async def test_execute_stream_transform_chunk(account):
    """
    Test streaming SSE chunk transformation with plugin.transform_stream_chunk hook.
    """
    raw_content = b'data: {"delta": "hello world"}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=raw_content,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = ProxyEngine(client=client)
        plugin = CustomTransformPlugin()

        proxy_req = ProxyRequest(
            method="POST",
            url="https://api.mock.test/v1/chat/completions",
            is_stream=True,
        )

        status_code, headers, stream_gen = await engine.execute_stream(plugin, account, proxy_req)
        assert status_code == 200

        received = []
        async for chunk in stream_gen:
            received.append(chunk)

        combined = b"".join(received).decode("utf-8")
        # 'hello' transformed into 'greetings'
        assert "greetings world" in combined
        assert "hello" not in combined


@pytest.mark.asyncio
@pytest.mark.parametrize("plugin_class", [FinalizeStreamPlugin, AsyncFinalizeStreamPlugin])
async def test_execute_stream_finalize_hook(account, plugin_class):
    """
    Test that the plugin.finalize_stream hook runs after the upstream stream ends.
    """
    raw_content = b'data: {"delta": "hello"}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=raw_content,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = ProxyEngine(client=client)
        plugin = plugin_class()

        proxy_req = ProxyRequest(
            method="POST",
            url="https://api.mock.test/v1/chat/completions",
            is_stream=True,
        )

        status_code, _headers, stream_gen = await engine.execute_stream(
            plugin, account, proxy_req
        )
        assert status_code == 200

        received = []
        async for chunk in stream_gen:
            received.append(chunk)

        combined = b"".join(received)
        assert b"hello" in combined
        assert combined.endswith(b"data: [DONE]\n\n")


@pytest.mark.asyncio
async def test_proxy_engine_connection_pooling_and_close():
    """
    Test ProxyEngine initialization, connection pooling limits, and cleanup.
    """
    engine = ProxyEngine(client_timeout=45.0)
    assert engine.client_timeout == 45.0
    client = engine.client
    assert not client.is_closed
    assert client.timeout.read == 45.0

    await engine.close()
    assert client.is_closed
