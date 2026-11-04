"""
Tests for SLProxy Built-in Provider Plugins
Verifies headers, request transformations, model catalogs, and custom error/quota detection.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from slproxy.core.plugin_base import Account, ProxyRequest, ProxyResponse
from slproxy.templates.plugins.google_antigravity import GoogleAntigravityPlugin
from slproxy.templates.plugins.openai_codex import OpenAICodexPlugin
from slproxy.templates.plugins.anthropic_claude import AnthropicClaudePlugin
from slproxy.templates.plugins.openrouter import OpenRouterPlugin
from slproxy.templates.plugins.opencode import OpenCodePlugin
from slproxy.templates.plugins.agentrouter import AgentRouterPlugin
from slproxy.templates.plugins.moonmath_zro import MoonmathZroPlugin
from slproxy.templates.plugins.openai_compatible import OpenAICompatiblePlugin
from slproxy.templates.plugins.anthropic_compatible import AnthropicCompatiblePlugin


# 1. Google Antigravity
def test_google_antigravity():
    plugin = GoogleAntigravityPlugin()
    assert plugin.id == "google_antigravity"
    assert plugin.name == "Google Antigravity"
    assert plugin.format == "antigravity"
    assert plugin.default_base_url == "https://antigravity.google"

    # Verify models
    model_ids = {m.id for m in plugin.models}
    assert "gemini-3.8-flash-high" in model_ids
    assert "gemini-3.1-pro-high" in model_ids
    assert "claude-sonnet-5-5-high" in model_ids

    account = Account(id="acc_g", provider_id="google_antigravity", name="GTest", api_key="test-key")

    # Header generation contains trajectory and IDE request IDs
    headers = plugin.build_headers(account)
    assert "x-trajectory-id" in headers
    assert "x-ide-request-id" in headers
    assert headers["x-trajectory-id"].startswith("traj_")
    assert headers["x-ide-request-id"].startswith("ide_req_")

    # Request transformation strips disallowed fields and injects missing IDs
    req = ProxyRequest(
        url="https://antigravity.google/v1/generate",
        headers={},
        body={
            "prompt": "Hello world",
            "temperature": 0.7,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.2,
            "disallowed_field": "remove_me",
        },
    )
    transformed = plugin.transform_request(req, account)
    assert "x-trajectory-id" in transformed.headers
    assert "x-ide-request-id" in transformed.headers
    assert "frequency_penalty" not in transformed.body
    assert "presence_penalty" not in transformed.body
    assert "disallowed_field" not in transformed.body
    assert transformed.body["prompt"] == "Hello world"
    assert transformed.body["temperature"] == 0.7


# 2. OpenAI Codex
def test_openai_codex():
    plugin = OpenAICodexPlugin()
    assert plugin.id == "openai_codex"
    assert plugin.name == "OpenAI Codex"
    assert plugin.format == "openai"
    assert plugin.default_base_url == "https://api.openai.com/v1"

    model_ids = {m.id for m in plugin.models}
    assert "gpt-4o" in model_ids
    assert "o3-mini" in model_ids
    assert "codex" in model_ids

    account = Account(id="acc_codex", provider_id="openai_codex", name="CodexTest", api_key="sk-test")

    # Test tools normalization: legacy functions -> tools
    req_legacy = ProxyRequest(
        url="https://api.openai.com/v1/chat/completions",
        body={
            "model": "gpt-4o",
            "functions": [{"name": "get_weather", "description": "Weather info"}],
        },
    )
    transformed = plugin.transform_request(req_legacy, account)
    assert "tools" in transformed.body
    assert "functions" not in transformed.body
    assert transformed.body["tools"][0]["type"] == "function"
    assert transformed.body["tools"][0]["function"]["name"] == "get_weather"

    # Test tool_choice string normalization
    req_choice = ProxyRequest(
        url="https://api.openai.com/v1/chat/completions",
        body={
            "model": "gpt-4o",
            "tools": [{"type": "function", "function": {"name": "calculate"}}],
            "tool_choice": "calculate",
        },
    )
    transformed_choice = plugin.transform_request(req_choice, account)
    assert transformed_choice.body["tool_choice"] == {
        "type": "function",
        "function": {"name": "calculate"},
    }

    # Test chat completions into Responses API transformation
    req_responses = ProxyRequest(
        url="https://api.openai.com/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "hi"}]},
        metadata={"to_responses": True},
    )
    transformed_resp = plugin.transform_request(req_responses, account)
    assert transformed_resp.url == "https://api.openai.com/v1/responses"
    assert "input" in transformed_resp.body

    # Test transform_response creates responses array
    resp = ProxyResponse(
        status_code=200,
        body={"choices": [{"message": {"role": "assistant", "content": "Hello!"}}]},
    )
    transformed_res = plugin.transform_response(resp, account)
    assert transformed_res.body["responses"] == ["Hello!"]


# 3. Anthropic Claude Code
def test_anthropic_claude():
    plugin = AnthropicClaudePlugin()
    assert plugin.id == "anthropic_claude"
    assert plugin.name == "Anthropic Claude Code"
    assert plugin.format == "anthropic"
    assert plugin.default_base_url == "https://api.anthropic.com/v1"

    model_ids = {m.id for m in plugin.models}
    assert "claude-3-7-sonnet" in model_ids
    assert "claude-3-5-sonnet" in model_ids
    assert "claude-3-5-haiku" in model_ids

    account = Account(id="acc_claude", provider_id="anthropic_claude", name="ClaudeTest", api_key="sk-ant-test")

    # Injects CLAUDE_CLI_SPOOF_HEADERS and Anthropic-Beta
    headers = plugin.build_headers(account)
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["User-Agent"] == "claude-cli/1.0.0 (darwin-arm64) claude-code"
    assert headers["anthropic-client"] == "claude-code"
    assert "anthropic-beta" in headers
    assert "prompt-caching-2024-07-31" in headers["anthropic-beta"]

    # transform_request also injects spoof headers and rewrites base url
    req = ProxyRequest(
        url="https://api.anthropic.com/v1",
        headers={},
        body={"model": "claude-3-7-sonnet"},
    )
    transformed = plugin.transform_request(req, account)
    assert transformed.url == "https://api.anthropic.com/v1/messages"
    assert transformed.headers["User-Agent"] == "claude-cli/1.0.0 (darwin-arm64) claude-code"
    assert "anthropic-beta" in transformed.headers


# 4. OpenRouter
def test_openrouter():
    plugin = OpenRouterPlugin()
    assert plugin.id == "openrouter"
    assert plugin.name == "OpenRouter"
    assert plugin.format == "openai"
    assert plugin.default_base_url == "https://openrouter.ai/api/v1"

    model_ids = {m.id for m in plugin.models}
    assert "openai/gpt-4o" in model_ids
    assert "anthropic/claude-3.5-sonnet" in model_ids
    assert "deepseek/deepseek-r1" in model_ids

    account = Account(
        id="acc_openrouter",
        provider_id="openrouter",
        name="ORTest",
        api_key="sk-or-test",
        extra_config={"referer": "https://myproxy.app", "title": "MyProxy"},
    )

    headers = plugin.build_headers(account)
    assert headers["Authorization"] == "Bearer sk-or-test"
    assert headers["HTTP-Referer"] == "https://myproxy.app"
    assert headers["X-Title"] == "MyProxy"

    req = ProxyRequest(url="https://openrouter.ai/api/v1/chat/completions", headers={})
    transformed = plugin.transform_request(req, account)
    assert transformed.headers["HTTP-Referer"] == "https://myproxy.app"
    assert transformed.headers["X-Title"] == "MyProxy"


# 5. OpenCode
def test_opencode():
    plugin = OpenCodePlugin()
    assert plugin.id == "opencode"
    assert plugin.name == "OpenCode"
    assert plugin.format == "openai"
    assert plugin.default_base_url == "https://api.opencode.ai/v1"

    model_ids = {m.id for m in plugin.models}
    assert "opencode-v1" in model_ids
    assert "opencode-pro" in model_ids

    account = Account(id="acc_opencode", provider_id="opencode", name="OCTest", api_key="sk-oc-test")

    # Injects User-Agent and x-opencode-session
    headers = plugin.build_headers(account)
    assert headers["User-Agent"] == "opencode/latest/2.0.26/cli"
    assert headers["x-opencode-session"].startswith("ses_")

    req = ProxyRequest(url="https://api.opencode.ai/v1/chat/completions", headers={})
    transformed = plugin.transform_request(req, account)
    assert transformed.headers["User-Agent"] == "opencode/latest/2.0.26/cli"
    assert transformed.headers["x-opencode-session"].startswith("ses_")


# 6. AgentRouter
def test_agentrouter():
    plugin = AgentRouterPlugin()
    assert plugin.id == "agentrouter"
    assert plugin.name == "AgentRouter"
    assert plugin.format == "openai"
    assert plugin.default_base_url == "https://agentrouter.org/v1"

    model_ids = {m.id for m in plugin.models}
    assert "agentrouter-default" in model_ids
    assert "claude-3-5-sonnet" in model_ids
    assert "gpt-4o" in model_ids

    account = Account(id="acc_ar", provider_id="agentrouter", name="ARTest", api_key="sk-ar-test")

    # Verifies specifically injecting OpenCode client headers to bypass client restriction
    headers = plugin.build_headers(account)
    assert headers["User-Agent"] == "opencode/latest/2.0.26/cli"
    assert headers["x-opencode-session"].startswith("ses_")

    req = ProxyRequest(url="https://agentrouter.org/v1/chat/completions", headers={})
    transformed = plugin.transform_request(req, account)
    assert transformed.headers["User-Agent"] == "opencode/latest/2.0.26/cli"
    assert transformed.headers["x-opencode-session"].startswith("ses_")


# 7. Moonmath Zro
def test_moonmath_zro_quota_and_limit_detection():
    plugin = MoonmathZroPlugin()
    assert plugin.id == "moonmath_zro"
    assert plugin.name == "Moonmath Zro"
    assert plugin.format == "openai"
    assert plugin.default_base_url == "https://api.moonmath.ai/v1"

    model_ids = {m.id for m in plugin.models}
    assert "moonmath-zro-v1" in model_ids
    assert "moonmath-zro-pro" in model_ids

    # Case 1: Status 200 OK with "limit reached" in response text
    res1 = plugin.detect_error_or_limit(200, '{"error": "Account rate limit reached for today"}', {})
    assert res1.is_error is True
    assert res1.is_rate_limited is True
    assert res1.should_fallback is True

    # Case 2: Status 200 OK with "quota exceeded" in response text
    res2 = plugin.detect_error_or_limit(200, 'You have quota exceeded on this tier', {})
    assert res2.is_error is True
    assert res2.is_rate_limited is True
    assert res2.should_fallback is True

    # Case 3: Status 200 OK with "insufficient quota" in response text
    res3 = plugin.detect_error_or_limit(200, 'insufficient quota available', {})
    assert res3.is_error is True
    assert res3.is_rate_limited is True
    assert res3.should_fallback is True

    # Case 4: Status 429 HTTP rate limited
    res4 = plugin.detect_error_or_limit(429, "Too Many Requests", {"retry-after": "30"})
    assert res4.is_error is True
    assert res4.is_rate_limited is True
    assert res4.should_fallback is True
    assert res4.cooldown_seconds == 30.0

    # Case 5: Normal successful 200 OK response
    res5 = plugin.detect_error_or_limit(200, '{"id": "chatcmpl-123", "choices": []}', {})
    assert res5.is_error is False
    assert res5.is_rate_limited is False
    assert res5.should_fallback is False

    # Case 6: Stream chunk checking
    chunk_limit = b'data: {"error": "usage limit exceeded"}\n\n'
    stream_check = plugin.check_chunk_for_limit(chunk_limit)
    assert stream_check is not None
    assert stream_check.is_rate_limited is True
    assert stream_check.should_fallback is True

    chunk_normal = b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\n'
    assert plugin.check_chunk_for_limit(chunk_normal) is None


# 8. OpenAI Compatible
def test_openai_compatible():
    plugin = OpenAICompatiblePlugin()
    assert plugin.id == "openai_compatible"
    assert plugin.name == "OpenAI Compatible"
    assert plugin.format == "openai"
    assert plugin.default_base_url == "https://api.openai.com/v1"

    model_ids = {m.id for m in plugin.models}
    assert "default" in model_ids
    assert "gpt-4o" in model_ids

    account = Account(id="acc_compat", provider_id="openai_compatible", name="Compat", api_key="sk-compat")
    headers = plugin.build_headers(account)
    assert headers["Authorization"] == "Bearer sk-compat"
    assert headers["Content-Type"] == "application/json"


# 9. Anthropic Compatible
def test_anthropic_compatible():
    plugin = AnthropicCompatiblePlugin()
    assert plugin.id == "anthropic_compatible"
    assert plugin.name == "Anthropic Compatible"
    assert plugin.format == "anthropic"
    assert plugin.default_base_url == "https://api.anthropic.com/v1"

    model_ids = {m.id for m in plugin.models}
    assert "claude-3-5-sonnet-20241022" in model_ids
    assert "claude-3-5-haiku-20241022" in model_ids

    account = Account(id="acc_anth_compat", provider_id="anthropic_compatible", name="AnthCompat", api_key="sk-ant")
    headers = plugin.build_headers(account)
    assert headers["x-api-key"] == "sk-ant"
    assert headers["anthropic-version"] == "2023-06-01"

    req = ProxyRequest(url="https://api.anthropic.com/v1", headers={})
    transformed = plugin.transform_request(req, account)
    assert transformed.url == "https://api.anthropic.com/v1/messages"


def test_moonmath_zro_upstream_and_auth_errors():
    plugin = MoonmathZroPlugin()

    # Test HTTP 500 upstream server error
    res_500 = plugin.detect_error_or_limit(500, "Internal Server Error", {})
    assert res_500.is_error is True
    assert res_500.should_fallback is True
    assert "Upstream Server Error" in res_500.error_message

    # Test HTTP 401 Auth error
    res_401 = plugin.detect_error_or_limit(401, "Unauthorized", {})
    assert res_401.is_error is True
    assert res_401.should_fallback is True
    assert "Authentication" in res_401.error_message


def test_plugin_fetch_models_and_custom_base_url():
    plugins = [
        GoogleAntigravityPlugin(),
        OpenAICodexPlugin(),
        AnthropicClaudePlugin(),
        OpenRouterPlugin(),
        OpenCodePlugin(),
        AgentRouterPlugin(),
        MoonmathZroPlugin(),
        OpenAICompatiblePlugin(),
        AnthropicCompatiblePlugin(),
    ]

    for p in plugins:
        models = p.fetch_models()
        assert len(models) > 0
        assert all(m.id for m in models)
        assert all(m.name for m in models)

        # Base URL without account
        default_url = p.get_base_url()
        assert default_url == p.default_base_url.rstrip("/")

        # Custom base URL via account
        custom_acc = Account(
            id="acc_custom",
            provider_id=p.id,
            name="Custom",
            base_url="https://custom.endpoint.com/v1/",
        )
        assert p.get_base_url(custom_acc) == "https://custom.endpoint.com/v1"

