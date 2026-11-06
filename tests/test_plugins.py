"""
Tests for SLProxy Built-in Provider Plugins
Verifies headers, request transformations, model catalogs, and custom error/quota detection.
"""

import sys
import time
import uuid
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from slproxy.core.plugin_base import Account, ModelInfo, ProxyRequest, ProxyResponse
from slproxy.templates.plugins.anthropic_claude import AnthropicClaudePlugin
from slproxy.templates.plugins.anthropic_compatible import AnthropicCompatiblePlugin
from slproxy.templates.plugins.google_antigravity import GoogleAntigravityPlugin
from slproxy.templates.plugins.openai_codex import OpenAICodexPlugin
from slproxy.templates.plugins.openai_compatible import OpenAICompatiblePlugin
from slproxy.templates.plugins.opencode import OpenCodePlugin
from slproxy.templates.plugins.openrouter import OpenRouterPlugin


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

    # Header generation contains 9Router trajectory, request IDs, and client markers
    headers = plugin.build_headers(account)
    assert headers["User-Agent"] == "Antigravity-IDE/1.0"
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["x-goog-api-client"] == "ide/antigravity"
    assert "x-trajectory-id" in headers
    assert "x-ide-request-id" in headers
    assert "x-request-id" in headers

    # Verify 9Router trajectory ID format: agent/<conversation_id>/<timestamp>/<trajectory_id>/<step>
    traj_id = headers["x-trajectory-id"]
    parts = traj_id.split("/")
    assert len(parts) == 5
    assert parts[0] == "agent"
    uuid.UUID(parts[1])  # Valid conversation UUID derived from seed
    assert int(parts[2]) > 0  # Valid timestamp integer
    uuid.UUID(parts[3])  # Valid trajectory UUID derived from seed
    assert parts[4] == "1"  # Step counter

    assert headers["x-ide-request-id"].startswith("ide_req_")
    assert headers["x-request-id"] == headers["x-ide-request-id"]

    # Request transformation strips all Google-rejected parameters and injects missing telemetry
    req = ProxyRequest(
        url="https://antigravity.google/v1/generate",
        headers={},
        body={
            "prompt": "Hello world",
            "temperature": 0.7,
            "output_config": {"format": "json"},
            "thinking": {"enabled": True},
            "reasoning_effort": "high",
            "reasoning": "enabled",
            "enable_thinking": True,
            "thinking_budget": 2048,
            "thinkingConfig": {"thinkingBudget": 2048},
            "frequency_penalty": 0.5,
            "presence_penalty": 0.2,
            "disallowed_field": "remove_me",
        },
    )
    transformed = plugin.transform_request(req, account)
    assert transformed.headers["User-Agent"] == "Antigravity-IDE/1.0"
    assert transformed.headers["x-goog-api-client"] == "ide/antigravity"
    assert transformed.headers["Authorization"] == "Bearer test-key"
    assert transformed.headers["x-trajectory-id"].startswith("agent/")
    assert transformed.headers["x-ide-request-id"].startswith("ide_req_")

    # Completely stripped fields
    for rejected in [
        "output_config",
        "thinking",
        "reasoning_effort",
        "reasoning",
        "enable_thinking",
        "thinking_budget",
        "thinkingConfig",
        "frequency_penalty",
        "presence_penalty",
        "disallowed_field",
    ]:
        assert rejected not in transformed.body

    # Retained valid fields
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

    # Test explicit conversion of role: system -> role: developer,
    # stripping of server-generated IDs (rs_, fc_, msg_),
    # and regex pattern sanitization for function tool schemas
    req = ProxyRequest(
        url="https://api.openai.com/v1/chat/completions",
        body={
            "model": "codex",
            "messages": [
                {"id": "msg_12345", "role": "system", "content": "You are a code assistant."},
                {"id": "user_normal", "role": "user", "content": "Write code"},
                {"id": "rs_abc999", "role": "assistant", "content": "Sure", "tool_calls": [
                    {"id": "fc_call_888", "type": "function", "function": {"name": "run_cmd", "arguments": "{}"}}
                ]},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "validate_input",
                        "description": "Validation tool",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "email": {"type": "string", "pattern": r"(?i)^[a-z0-9]+$"},
                                "invalid_regex": {"type": "string", "pattern": r"(?<=[a-z"},
                            },
                        },
                    },
                }
            ],
        },
    )

    transformed = plugin.transform_request(req, account)

    # 1. System -> developer role conversion
    messages = transformed.body["messages"]
    assert messages[0]["role"] == "developer"
    assert messages[1]["role"] == "user"

    # 2. Stripping server-generated item IDs (rs_, fc_, msg_)
    assert "id" not in messages[0]  # was msg_12345
    assert messages[1]["id"] == "user_normal"  # user_ is preserved
    assert "id" not in messages[2]  # was rs_abc999
    assert "id" not in messages[2]["tool_calls"][0]  # was fc_call_888

    # 3. Regex pattern sanitization
    tool_params = transformed.body["tools"][0]["function"]["parameters"]["properties"]
    assert tool_params["email"]["pattern"] == r"^[a-z0-9]+$"  # (?i) stripped
    assert "pattern" not in tool_params["invalid_regex"]  # invalid regex dropped

    # Test tools normalization: legacy functions -> tools
    req_legacy = ProxyRequest(
        url="https://api.openai.com/v1/chat/completions",
        body={
            "model": "gpt-4o",
            "functions": [{"name": "get_weather", "description": "Weather info"}],
        },
    )
    transformed_legacy = plugin.transform_request(req_legacy, account)
    assert "tools" in transformed_legacy.body
    assert "functions" not in transformed_legacy.body
    assert transformed_legacy.body["tools"][0]["type"] == "function"
    assert transformed_legacy.body["tools"][0]["function"]["name"] == "get_weather"

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

    # Injects full Stainless SDK spoofing headers
    headers = plugin.build_headers(account)
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["User-Agent"] == "claude-cli/2.1.280 (external, sdk-cli)"
    assert headers["Anthropic-Version"] == "2023-06-01"
    assert headers["Anthropic-Beta"] == (
        "claude-code-20250219,"
        "interleaved-thinking-2025-05-14,"
        "context-management-2025-06-27,"
        "prompt-caching-scope-2026-01-05"
    )
    assert headers["X-App"] == "cli"
    assert headers["X-Stainless-Runtime-Version"] == "v24.14.0"
    assert headers["X-Stainless-Arch"] == "arm64"
    assert headers["X-Stainless-Os"] == "macOS"

    # transform_request also injects spoof headers and rewrites base url
    req = ProxyRequest(
        url="https://api.anthropic.com/v1",
        headers={},
        body={"model": "claude-3-7-sonnet"},
    )
    transformed = plugin.transform_request(req, account)
    assert transformed.url == "https://api.anthropic.com/v1/messages"
    assert transformed.headers["User-Agent"] == "claude-cli/2.1.280 (external, sdk-cli)"
    assert transformed.headers["Anthropic-Beta"] == headers["Anthropic-Beta"]
    assert transformed.headers["X-App"] == "cli"
    assert transformed.headers["X-Stainless-Runtime-Version"] == "v24.14.0"


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

    # Injects User-Agent and exact 9Router descending-time session ID
    headers = plugin.build_headers(account)
    assert headers["User-Agent"] == "opencode/latest/2.0.26/cli"
    session_id = headers["x-opencode-session"]
    assert session_id.startswith("ses_")

    # Verify descending time prefix algorithm:
    # ses_<descending_time_hex><random14>
    # descending_time_hex = (~(int(time_ms) * 0x1000 + counter) & 0xFFFFFFFFFFFF).to_bytes(6, 'big').hex()
    descending_hex = session_id[4:16]
    assert len(descending_hex) == 12
    suffix = session_id[16:]
    assert len(suffix) == 14

    # Recover timestamp from inverted 48 bits
    inverted_val = int(descending_hex, 16)
    recovered_packed = (~inverted_val) & 0xFFFFFFFFFFFF
    recovered_time_ms = recovered_packed // 0x1000
    recovered_counter = recovered_packed & 0x0FFF

    now_ms = int(time.time() * 1000)
    # 48 bits total = 36 bits timestamp + 12 bits counter
    expected_time_36 = now_ms & 0xFFFFFFFFF
    assert abs(expected_time_36 - recovered_time_ms) < 5000  # Within 5 seconds of generation
    assert recovered_counter < 10  # Counter is small

    req = ProxyRequest(url="https://api.opencode.ai/v1/chat/completions", headers={})
    transformed = plugin.transform_request(req, account)
    assert transformed.headers["User-Agent"] == "opencode/latest/2.0.26/cli"
    assert transformed.headers["x-opencode-session"].startswith("ses_")


# 6. OpenAI Compatible
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


# 7. Anthropic Compatible
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


def test_plugin_fetch_models_and_custom_base_url():
    plugins = [
        GoogleAntigravityPlugin(),
        OpenAICodexPlugin(),
        AnthropicClaudePlugin(),
        OpenRouterPlugin(),
        OpenCodePlugin(),
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


def test_plugin_add_and_remove_model():
    plugin = GoogleAntigravityPlugin()
    initial_count = len(plugin.models)

    # 1. Add model
    new_model = ModelInfo(
        id="gemini-custom-enterprise",
        name="Gemini Custom Enterprise",
        context_window=2000000,
        max_output_tokens=16384,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=True,
    )
    added = plugin.add_model(new_model)
    assert added is True
    assert len(plugin.models) == initial_count + 1
    assert any(m.id == "gemini-custom-enterprise" for m in plugin.fetch_models())

    # 2. Update existing model
    updated_model = ModelInfo(
        id="gemini-custom-enterprise",
        name="Gemini Custom Enterprise Updated",
        context_window=4000000,
    )
    plugin.add_model(updated_model)
    assert len(plugin.models) == initial_count + 1
    found = next(m for m in plugin.models if m.id == "gemini-custom-enterprise")
    assert found.name == "Gemini Custom Enterprise Updated"
    assert found.context_window == 4000000

    # 3. Remove model
    removed = plugin.remove_model("gemini-custom-enterprise")
    assert removed is True
    assert len(plugin.models) == initial_count
    assert not any(m.id == "gemini-custom-enterprise" for m in plugin.fetch_models())

    # Remove non-existent model returns False
    assert plugin.remove_model("non-existent-id") is False

    # 4. Account-level model overrides
    account_with_override = Account(
        id="acc_custom_models",
        provider_id="google_antigravity",
        name="Account With Override",
        extra_config={"models": ["override-model-1", {"id": "override-model-2", "name": "Override Model 2"}]},
    )
    custom_models = plugin.fetch_models(account_with_override)
    assert len(custom_models) == 2
    assert custom_models[0].id == "override-model-1"
    assert custom_models[1].id == "override-model-2"
