"""
Tests for SLProxy Built-in Provider Plugins
Verifies headers, request transformations, model catalogs, and custom error/quota detection.
"""

import json
import re
import sys
import time
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
ANTIGRAVITY_MODELS = {
    "gemini-3.8-flash-high": ("MODEL_PLACEHOLDER_M318", 65536),
    "gemini-3.8-flash-medium": ("MODEL_PLACEHOLDER_M319", 65536),
    "gemini-3.8-flash-low": ("MODEL_PLACEHOLDER_M320", 65536),
    "claude-sonnet-4-6": ("MODEL_PLACEHOLDER_M35", 64000),
    "claude-opus-4-6-thinking": ("MODEL_PLACEHOLDER_M26", 64000),
    "gpt-oss-120b-medium": ("MODEL_OPENAI_GPT_OSS_120B_MEDIUM", 32768),
}


def _antigravity_account(**overrides):
    values = {
        "id": "acc_g",
        "provider_id": "google_antigravity",
        "name": "GTest",
        "api_key": "test-key",
    }
    values.update(overrides)
    return Account(**values)


def _antigravity_messages():
    return [
        {"role": "system", "content": "You are a test assistant."},
        {"role": "user", "content": "List the files"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "toolu_abc",
                    "type": "function",
                    "function": {"name": "run_command", "arguments": '{"cmd":"ls"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "toolu_abc",
            "name": "run_command",
            "content": "a.txt\nb.txt",
        },
    ]


def _antigravity_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"],
                },
            },
        }
    ]


def test_google_antigravity():
    plugin = GoogleAntigravityPlugin()
    assert plugin.id == "google_antigravity"
    assert plugin.name == "Google Antigravity"
    assert plugin.format == "antigravity"
    assert plugin.default_base_url == "https://daily-cloudcode-pa.googleapis.com"
    assert plugin.DEFAULT_PROJECT == "aicode-consumers"
    assert plugin.USER_AGENT == (
        "antigravity/cli/1.5.2 "
        "(aidev_client; os_type=linux; arch=amd64; cl=1015175089; "
        "auth_method=consumer)"
    )

    # Verify the six model IDs exposed by `agy models`.
    model_ids = {m.id for m in plugin.models}
    assert model_ids == set(ANTIGRAVITY_MODELS)
    for model in plugin.models:
        model_enum, max_output = ANTIGRAVITY_MODELS[model.id]
        assert model.extra["model_enum"] == model_enum
        assert model.max_output_tokens == max_output
        assert model.supports_streaming is True
        assert model.supports_tools is True

    account = _antigravity_account()
    headers = plugin.build_headers(account)
    assert headers == {
        "Content-Type": "application/json",
        "User-Agent": plugin.USER_AGENT,
        "Accept-Encoding": "gzip",
        "Authorization": "Bearer test-key",
    }

    # agy does not send any of the old IDE / 9Router fingerprint headers.
    for stale in (
        "x-goog-api-client",
        "x-trajectory-id",
        "x-ide-request-id",
        "x-request-id",
        "Accept",
    ):
        assert stale not in headers


def test_google_antigravity_request_envelope():
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account()
    req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        headers={},
        body={
            "model": "gemini-3.8-flash-medium",
            "messages": _antigravity_messages(),
            "tools": _antigravity_tools(),
        },
        is_stream=False,
        model="gemini-3.8-flash-medium",
    )

    transformed = plugin.transform_request(req, account)
    assert transformed.url == (
        "https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent"
    )
    assert transformed.headers["Authorization"] == "Bearer test-key"

    body = transformed.body
    assert body["project"] == "aicode-consumers"
    assert body["model"] == "gemini-3.8-flash-medium"
    assert body["userAgent"] == "antigravity"
    assert body["requestType"] == "agent"

    match = re.fullmatch(
        r"agent/([0-9a-f-]{36})/(\d+)/([0-9a-f-]{36})/(\d+)",
        body["requestId"],
    )
    assert match is not None
    conversation_id, timestamp, trajectory_id, step = match.groups()
    assert int(timestamp) > 0
    assert step == "3"

    inner = body["request"]
    assert inner["contents"] == [
        {"role": "user", "parts": [{"text": "List the files"}]},
        {
            "role": "model",
            "parts": [
                {
                    "functionCall": {
                        "name": "run_command",
                        "args": {"cmd": "ls"},
                        "id": "toolu_abc",
                    }
                }
            ],
        },
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "run_command",
                        "response": {"output": "a.txt\nb.txt"},
                        "id": "toolu_abc",
                    }
                }
            ],
        },
    ]
    assert inner["systemInstruction"] == {
        "role": "user",
        "parts": [{"text": "You are a test assistant."}],
    }
    assert inner["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "run_command",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {"cmd": {"type": "STRING"}},
                        "required": ["cmd"],
                    },
                }
            ]
        }
    ]

    labels = inner["labels"]
    assert labels["cascade_id"] == conversation_id
    assert labels["root_cascade_id"] == conversation_id
    assert labels["trajectory_id"] == trajectory_id
    assert labels["last_step_index"] == "2"
    assert labels["request_id"] == f"{trajectory_id}-1"
    assert labels["model_enum"] == "MODEL_PLACEHOLDER_M319"
    assert labels["used_claude"] == "false"
    assert labels["used_claude_conservative"] == "false"
    assert labels["used_non_gemini_model"] == "false"

    assert inner["generationConfig"] == {
        "maxOutputTokens": 65536,
        "thinkingConfig": {"includeThoughts": True, "thinkingLevel": "MEDIUM"},
    }
    assert int(inner["sessionId"]) == int(plugin._session_id(account))

    # The hook is idempotent: the router and proxy engine both call it.
    again = plugin.transform_request(transformed, account)
    assert again.body == body
    assert again.url == transformed.url

    # Conversation and trajectory IDs are deterministic for the same input.
    repeated = plugin.transform_request(
        ProxyRequest(
            url="https://ignored.example/v1/chat/completions",
            body={
                "model": "gemini-3.8-flash-medium",
                "messages": _antigravity_messages(),
                "tools": _antigravity_tools(),
            },
            is_stream=False,
            model="gemini-3.8-flash-medium",
        ),
        account,
    )
    repeated_match = re.fullmatch(
        r"agent/([0-9a-f-]{36})/(\d+)/([0-9a-f-]{36})/(\d+)",
        repeated.body["requestId"],
    )
    assert repeated_match is not None
    assert repeated_match.group(1) == conversation_id
    assert repeated_match.group(3) == trajectory_id

    # A different account produces a different conversation/session.
    other = plugin.transform_request(
        ProxyRequest(
            url="https://ignored.example/v1/chat/completions",
            body={
                "model": "gemini-3.8-flash-medium",
                "messages": _antigravity_messages(),
                "tools": _antigravity_tools(),
            },
            is_stream=False,
            model="gemini-3.8-flash-medium",
        ),
        _antigravity_account(id="acc_other"),
    )
    other_match = re.fullmatch(
        r"agent/([0-9a-f-]{36})/(\d+)/([0-9a-f-]{36})/(\d+)",
        other.body["requestId"],
    )
    assert other_match is not None
    assert other_match.group(1) != conversation_id
    assert other.body["request"]["sessionId"] != inner["sessionId"]


def test_google_antigravity_stream_url_and_overrides():
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account(
        id="acc_stream_url",
        base_url="https://custom.example",
        extra_config={"project": "custom-project", "session_id": "12345"},
    )
    req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        body={
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
        is_stream=True,
        model="claude-sonnet-4-6",
    )

    transformed = plugin.transform_request(req, account)
    assert transformed.url == "https://custom.example/v1internal:streamGenerateContent?alt=sse"
    assert transformed.body["project"] == "custom-project"
    assert transformed.body["request"]["sessionId"] == "12345"
    assert transformed.body["request"]["labels"]["model_enum"] == "MODEL_PLACEHOLDER_M35"

    # Clean up the streaming state created for this request.
    plugin.finalize_stream(account, transformed.metadata)


@pytest.mark.parametrize(
    ("model", "model_enum", "used_claude", "used_non_gemini", "max_output", "thinking"),
    [
        (
            "gemini-3.8-flash-high",
            "MODEL_PLACEHOLDER_M318",
            "false",
            "false",
            65536,
            {"includeThoughts": True, "thinkingLevel": "HIGH"},
        ),
        (
            "gemini-3.8-flash-low",
            "MODEL_PLACEHOLDER_M320",
            "false",
            "false",
            65536,
            {"includeThoughts": True, "thinkingLevel": "LOW"},
        ),
        (
            "claude-sonnet-4-6",
            "MODEL_PLACEHOLDER_M35",
            "true",
            "true",
            64000,
            {"includeThoughts": True, "thinkingBudget": 1024},
        ),
        (
            "claude-opus-4-6-thinking",
            "MODEL_PLACEHOLDER_M26",
            "true",
            "true",
            64000,
            {"includeThoughts": True, "thinkingBudget": 1024},
        ),
        (
            "gpt-oss-120b-medium",
            "MODEL_OPENAI_GPT_OSS_120B_MEDIUM",
            "false",
            "true",
            32768,
            {"includeThoughts": True, "thinkingBudget": 8192},
        ),
    ],
)
def test_google_antigravity_model_envelopes(
    model, model_enum, used_claude, used_non_gemini, max_output, thinking
):
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account(id=f"acc_{model}")
    req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        body={"model": model, "messages": [{"role": "user", "content": "hello"}]},
        is_stream=False,
        model=model,
    )

    body = plugin.transform_request(req, account).body
    labels = body["request"]["labels"]
    assert body["model"] == model
    assert labels["model_enum"] == model_enum
    assert labels["used_claude"] == used_claude
    assert labels["used_claude_conservative"] == used_claude
    assert labels["used_non_gemini_model"] == used_non_gemini
    assert body["request"]["generationConfig"] == {
        "maxOutputTokens": max_output,
        "thinkingConfig": thinking,
    }


def test_google_antigravity_alias_and_unknown_model():
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account(id="acc_alias")

    alias_req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        body={"model": "gemini-3.8-flash", "messages": [{"role": "user", "content": "hi"}]},
        is_stream=False,
        model="gemini-3.8-flash",
    )
    alias_body = plugin.transform_request(alias_req, account).body
    assert alias_body["model"] == "gemini-3.8-flash-high"
    assert alias_body["request"]["labels"]["model_enum"] == "MODEL_PLACEHOLDER_M318"

    unknown_req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        body={
            "model": "claude-future-model",
            "messages": [{"role": "user", "content": "hi"}],
        },
        is_stream=False,
        model="claude-future-model",
    )
    unknown_body = plugin.transform_request(unknown_req, account).body
    assert unknown_body["model"] == "claude-future-model"
    assert unknown_body["request"]["labels"]["model_enum"] == "MODEL_PLACEHOLDER_M35"
    assert unknown_body["request"]["generationConfig"]["maxOutputTokens"] == 64000


def test_google_antigravity_stream_conversion():
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account(id="acc_stream_convert")
    req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        body={
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
        is_stream=True,
        model="claude-sonnet-4-6",
    )
    plugin.transform_request(req, account)

    events = [
        {
            "response": {
                "candidates": [{"content": {"role": "model", "parts": [{"text": ""}]}}],
                "modelVersion": "claude-sonnet-4-6",
            }
        },
        {
            "response": {
                "candidates": [
                    {"content": {"role": "model", "parts": [{"thought": True, "text": "Let me think"}]}}
                ]
            }
        },
        {
            "response": {
                "candidates": [{"content": {"role": "model", "parts": [{"text": "Hello"}]}}]
            }
        },
        {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": ""}]},
                        "finishReason": "STOP",
                    }
                ]
            }
        },
        # GPT-OSS style usage-only event after the finish event.
        {
            "response": {
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 8,
                    "totalTokenCount": 108,
                    "cachedContentTokenCount": 20,
                }
            }
        },
    ]
    raw = b"".join(
        b"data: " + json.dumps(event).encode("utf-8") + b"\n\n" for event in events
    )

    output = b""
    for index in range(0, len(raw), 17):
        output += plugin.transform_stream_chunk(raw[index:index + 17], account)
    output += plugin.finalize_stream(account, req.metadata)

    text = output.decode("utf-8")
    assert text.rstrip().endswith("data: [DONE]")
    frames = [
        json.loads(line[len("data: "):])
        for line in text.splitlines()
        if line.startswith("data: ") and line[len("data: "):] != "[DONE]"
    ]

    first = frames[0]["choices"][0]
    assert first["delta"]["role"] == "assistant"
    assert first["finish_reason"] is None

    deltas = [frame["choices"][0]["delta"] for frame in frames if frame["choices"]]
    assert any(delta.get("reasoning_content") == "Let me think" for delta in deltas)
    assert any(delta.get("content") == "Hello" for delta in deltas)

    finish = next(
        frame for frame in frames if frame["choices"] and frame["choices"][0]["finish_reason"]
    )
    assert finish["choices"][0]["finish_reason"] == "stop"
    assert "usage" not in finish

    # The usage-only event is emitted as a separate usage chunk, matching OpenAI.
    usage_only = [frame for frame in frames if frame["choices"] == []]
    assert len(usage_only) == 1
    assert usage_only[0]["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 8,
        "total_tokens": 108,
        "prompt_tokens_details": {"cached_tokens": 20},
    }
    assert len({frame["id"] for frame in frames}) == 1


def test_google_antigravity_stream_tool_calls():
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account(id="acc_stream_tools")
    req = ProxyRequest(
        url="https://ignored.example/v1/chat/completions",
        body={
            "model": "gemini-3.8-flash-high",
            "messages": [{"role": "user", "content": "run ls"}],
            "stream": True,
        },
        is_stream=True,
        model="gemini-3.8-flash-high",
    )
    plugin.transform_request(req, account)

    events = [
        {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "id": "toolu_stream",
                                        "name": "run_command",
                                        "args": {"cmd": "ls"},
                                    }
                                }
                            ],
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2},
            }
        },
        {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": ""}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2},
            }
        },
    ]
    raw = b"".join(
        b"data: " + json.dumps(event).encode("utf-8") + b"\n\n" for event in events
    )

    output = plugin.transform_stream_chunk(raw, account)
    output += plugin.finalize_stream(account, req.metadata)
    frames = [
        json.loads(line[len("data: "):])
        for line in output.decode("utf-8").splitlines()
        if line.startswith("data: ") and line[len("data: "):] != "[DONE]"
    ]

    tool_delta = next(
        frame["choices"][0]["delta"]["tool_calls"][0]
        for frame in frames
        if frame["choices"] and frame["choices"][0]["delta"].get("tool_calls")
    )
    assert tool_delta["id"] == "toolu_stream"
    assert tool_delta["function"] == {"name": "run_command", "arguments": '{"cmd":"ls"}'}

    finish = next(
        frame for frame in frames if frame["choices"] and frame["choices"][0]["finish_reason"]
    )
    assert finish["choices"][0]["finish_reason"] == "tool_calls"


def test_google_antigravity_nonstream_response():
    plugin = GoogleAntigravityPlugin()
    account = _antigravity_account(id="acc_response")
    response = ProxyResponse(
        status_code=200,
        body={
            "response": {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {"thought": True, "text": "thinking"},
                                {"text": "I will run that."},
                                {
                                    "functionCall": {
                                        "id": "toolu_resp",
                                        "name": "run_command",
                                        "args": {"cmd": "ls"},
                                    }
                                },
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 15,
                    "thoughtsTokenCount": 2,
                },
                "modelVersion": "gemini-3.8-flash-high",
            }
        },
    )

    converted = plugin.transform_response(response, account)
    assert converted.body["object"] == "chat.completion"
    assert converted.body["model"] == "gemini-3.8-flash-high"
    choice = converted.body["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] == "I will run that."
    assert choice["message"]["reasoning_content"] == "thinking"
    assert choice["message"]["tool_calls"] == [
        {
            "id": "toolu_resp",
            "type": "function",
            "function": {"name": "run_command", "arguments": '{"cmd":"ls"}'},
        }
    ]
    assert converted.body["usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
        "completion_tokens_details": {"reasoning_tokens": 2},
    }


def test_google_antigravity_error_detection():
    plugin = GoogleAntigravityPlugin()

    quota = plugin.detect_error_or_limit(
        429,
        json.dumps(
            {
                "error": {
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Individual quota reached. Please upgrade.",
                    "details": [{"retryDelay": "120s"}],
                }
            }
        ),
        {},
    )
    assert quota.is_error is True
    assert quota.is_rate_limited is True
    assert quota.should_fallback is False
    assert quota.cooldown_seconds == 120.0

    auth = plugin.detect_error_or_limit(
        401,
        json.dumps({"error": {"status": "UNAUTHENTICATED", "message": "Bad token"}}),
        {},
    )
    assert auth.is_error is True
    assert auth.is_rate_limited is True
    assert auth.cooldown_seconds == 3600.0
    assert auth.should_fallback is False
    assert auth.error_message == "Bad token"

    quota_reset_at = time.time() + 90
    quota_409 = plugin.detect_error_or_limit(
        409,
        json.dumps({
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exhausted",
                "details": [{
                    "metadata": {
                        "quotaResetTimeStamp": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(quota_reset_at)
                        )
                    }
                }],
            }
        }),
        {},
    )
    assert quota_409.is_rate_limited is True
    assert quota_409.should_fallback is False
    assert 85 <= quota_409.cooldown_seconds <= 90

    server = plugin.detect_error_or_limit(503, "", {})
    assert server.is_error is True
    assert server.is_rate_limited is False
    assert server.cooldown_seconds == 15.0

    ok = plugin.detect_error_or_limit(200, "{}", {})
    assert ok.is_error is False
    assert ok.should_fallback is False


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
