"""
Google Antigravity Provider Plugin
==================================

Wire-compatible implementation of the official Antigravity CLI (``agy``)
Cloud Code / Code Assist protocol.

Protocol observed from ``agy`` 1.5.2
------------------------------------
The official CLI does not talk to ``antigravity.google``.  It sends requests to
Google's Cloud Code backend:

* ``POST https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse``
* ``POST https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent``

Every generation request is wrapped in an Antigravity agent envelope::

    {
      "project": "aicode-consumers",
      "requestId": "agent/<conversation_id>/<timestamp_ms>/<trajectory_id>/<step>",
      "request": {
        "contents": [...],              # Gemini Content objects
        "systemInstruction": {...},     # Gemini Content (role "user")
        "tools": [...],                 # Gemini functionDeclarations
        "labels": {
          "cascade_id": "<conversation_id>",
          "root_cascade_id": "<conversation_id>",
          "trajectory_id": "<trajectory_id>",
          "last_step_index": "0",
          "request_id": "<trajectory_id>-0",
          "model_enum": "MODEL_PLACEHOLDER_M318",
          "used_claude": "false",
          "used_claude_conservative": "false",
          "used_non_gemini_model": "false"
        },
        "generationConfig": {
          "maxOutputTokens": 65536,
          "thinkingConfig": {"includeThoughts": true, "thinkingLevel": "HIGH"}
        },
        "sessionId": "-3750763034362895579"
      },
      "model": "gemini-3.8-flash-high",
      "userAgent": "antigravity",
      "requestType": "agent"
    }

The CLI identifies itself with a single fixed User-Agent and an OAuth Bearer
token; it does not send ``x-goog-api-client``, ``x-trajectory-id``, or any
other custom IDE headers.  Streaming responses are SSE frames of the form::

    data: {"response": {"candidates": [...]}, "traceId": "...", "metadata": {}}

This plugin translates OpenAI Chat Completions requests into that envelope and
converts the Gemini responses (including thoughts and tool calls) back into
OpenAI Chat Completions / SSE.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from slproxy.core.plugin_base import (
    Account,
    BasePlugin,
    ErrorCheckResult,
    ModelInfo,
    ProxyRequest,
    ProxyResponse,
)


# Per-request streaming state.  A ContextVar lets the plugin associate
# ``transform_stream_chunk`` calls with the request that created them even
# though that hook only receives an Account.  A registry is kept as a fallback
# for callers that consume a stream outside the originating async context.
_STREAM_STATE: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "google_antigravity_stream_state", default=None
)
_STREAM_STATES: Dict[str, Dict[str, Any]] = {}


class GoogleAntigravityPlugin(BasePlugin):
    """Google Antigravity provider using the official ``agy`` wire protocol."""

    id: str = "google_antigravity"
    name: str = "Google Antigravity"
    description: str = (
        "Google Antigravity Cloud Code provider matching the official agy CLI "
        "(v1internal streamGenerateContent, OAuth Bearer, agent envelope)"
    )
    version: str = "2.0.0"
    author: str = "SLProxy"
    icon: str = "google"
    color: str = "#4285F4"
    default_base_url: str = "https://daily-cloudcode-pa.googleapis.com"
    format: str = "antigravity"

    # Exact client fingerprint sent by agy 1.5.2 on Linux/amd64.
    USER_AGENT: str = (
        "antigravity/cli/1.5.2 "
        "(aidev_client; os_type=linux; arch=amd64; cl=1015175089; "
        "auth_method=consumer)"
    )
    DEFAULT_PROJECT: str = "aicode-consumers"
    DEFAULT_MODEL: str = "gemini-3.8-flash-high"

    # Model metadata is dynamic upstream, but these are the six model IDs the
    # official CLI exposes through ``agy models``.  Values match
    # ``v1internal:fetchAvailableModels``.
    models: List[ModelInfo] = [
        ModelInfo(
            id="gemini-3.8-flash-high",
            name="Gemini 3.8 Flash (High)",
            context_window=1048576,
            max_output_tokens=65536,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            extra={"model_enum": "MODEL_PLACEHOLDER_M318", "family": "gemini"},
        ),
        ModelInfo(
            id="gemini-3.8-flash-medium",
            name="Gemini 3.8 Flash (Medium)",
            context_window=1048576,
            max_output_tokens=65536,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            extra={"model_enum": "MODEL_PLACEHOLDER_M319", "family": "gemini"},
        ),
        ModelInfo(
            id="gemini-3.8-flash-low",
            name="Gemini 3.8 Flash (Low)",
            context_window=1048576,
            max_output_tokens=65536,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            extra={"model_enum": "MODEL_PLACEHOLDER_M320", "family": "gemini"},
        ),
        ModelInfo(
            id="claude-sonnet-4-6",
            name="Claude Sonnet 4.6 (Thinking)",
            context_window=250000,
            max_output_tokens=64000,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            extra={"model_enum": "MODEL_PLACEHOLDER_M35", "family": "claude"},
        ),
        ModelInfo(
            id="claude-opus-4-6-thinking",
            name="Claude Opus 4.6 (Thinking)",
            context_window=250000,
            max_output_tokens=64000,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            extra={"model_enum": "MODEL_PLACEHOLDER_M26", "family": "claude"},
        ),
        ModelInfo(
            id="gpt-oss-120b-medium",
            name="GPT-OSS 120B (Medium)",
            context_window=131072,
            max_output_tokens=32768,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
            extra={
                "model_enum": "MODEL_OPENAI_GPT_OSS_120B_MEDIUM",
                "family": "openai",
            },
        ),
    ]

    # Aliases accepted for convenience.  The canonical upstream model ID is the
    # value; the plugin still advertises only the six official IDs above.
    MODEL_ALIASES: Dict[str, str] = {
        "gemini-3.8-flash": "gemini-3.8-flash-high",
        "gemini-3-flash": "gemini-3.8-flash-high",
        "claude-sonnet-4-6-thinking": "claude-sonnet-4-6",
        "claude-opus-4-6": "claude-opus-4-6-thinking",
        "gpt-oss-120b": "gpt-oss-120b-medium",
    }

    # Per-model generation configuration observed from agy.
    MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
        "gemini-3.8-flash-high": {
            "model_enum": "MODEL_PLACEHOLDER_M318",
            "family": "gemini",
            "max_output_tokens": 65536,
            "thinking_config": {"includeThoughts": True, "thinkingLevel": "HIGH"},
        },
        "gemini-3.8-flash-medium": {
            "model_enum": "MODEL_PLACEHOLDER_M319",
            "family": "gemini",
            "max_output_tokens": 65536,
            "thinking_config": {"includeThoughts": True, "thinkingLevel": "MEDIUM"},
        },
        "gemini-3.8-flash-low": {
            "model_enum": "MODEL_PLACEHOLDER_M320",
            "family": "gemini",
            "max_output_tokens": 65536,
            "thinking_config": {"includeThoughts": True, "thinkingLevel": "LOW"},
        },
        "claude-sonnet-4-6": {
            "model_enum": "MODEL_PLACEHOLDER_M35",
            "family": "claude",
            "max_output_tokens": 64000,
            "thinking_config": {"includeThoughts": True, "thinkingBudget": 1024},
        },
        "claude-opus-4-6-thinking": {
            "model_enum": "MODEL_PLACEHOLDER_M26",
            "family": "claude",
            "max_output_tokens": 64000,
            "thinking_config": {"includeThoughts": True, "thinkingBudget": 1024},
        },
        "gpt-oss-120b-medium": {
            "model_enum": "MODEL_OPENAI_GPT_OSS_120B_MEDIUM",
            "family": "openai",
            "max_output_tokens": 32768,
            "thinking_config": {"includeThoughts": True, "thinkingBudget": 8192},
        },
    }

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------
    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        """
        Build the exact header set used by agy.

        Captured request headers:
            Host: daily-cloudcode-pa.googleapis.com
            User-Agent: antigravity/cli/1.5.2 (...)
            Authorization: Bearer <OAuth access token>
            Content-Type: application/json
            Accept-Encoding: gzip
        """
        token = (account.api_key or "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": self.USER_AGENT,
            "Accept-Encoding": "gzip",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if account.extra_headers:
            headers.update(account.extra_headers)
        return headers

    # ------------------------------------------------------------------
    # Request transformation
    # ------------------------------------------------------------------
    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Convert an OpenAI Chat Completions request into the agy envelope.

        The method is idempotent: the router and the proxy engine both invoke
        the hook on the same ``ProxyRequest`` object.
        """
        base_url = self._generation_url(account, request.is_stream)
        request.url = base_url
        request.headers = self.build_headers(account, request.is_stream)

        body = self._as_dict(request.body)
        model = request.model or str(body.get("model") or self.DEFAULT_MODEL)
        model = model.rsplit("/", 1)[-1]
        canonical_model, model_config = self._resolve_model(model)

        request.metadata["antigravity_model"] = canonical_model
        self._bind_stream_state(request, account, canonical_model)

        if self._is_wrapped(body):
            request.body = body
            return request

        messages = body.get("messages")
        if not isinstance(messages, list):
            messages = []

        contents, system_text = self._convert_messages(messages)
        if not contents:
            # Gemini requires at least one content entry.
            contents = [{"role": "user", "parts": [{"text": ""}]}]

        conversation_id = self._conversation_id(request, account, messages, system_text)
        trajectory_id = self._trajectory_id(conversation_id, contents)
        timestamp_ms = int(time.time() * 1000)

        last_step_index = len(contents) - 1
        step = last_step_index + 1
        model_turns = sum(1 for item in contents if item.get("role") == "model")
        request_id = (
            f"agent/{conversation_id}/{timestamp_ms}/{trajectory_id}/{step}"
        )

        family = str(model_config.get("family", "gemini"))
        labels = {
            "cascade_id": conversation_id,
            "last_step_index": str(last_step_index),
            "model_enum": str(model_config.get("model_enum", "")),
            "request_id": f"{trajectory_id}-{model_turns}",
            "root_cascade_id": conversation_id,
            "trajectory_id": trajectory_id,
            "used_claude": "true" if family == "claude" else "false",
            "used_claude_conservative": "true" if family == "claude" else "false",
            "used_non_gemini_model": "false" if family == "gemini" else "true",
        }

        generation_config: Dict[str, Any] = {
            "maxOutputTokens": int(model_config.get("max_output_tokens", 65536)),
            "thinkingConfig": dict(model_config.get("thinking_config") or {}),
        }

        inner: Dict[str, Any] = {"contents": contents}
        if system_text:
            inner["systemInstruction"] = {
                "role": "user",
                "parts": [{"text": system_text}],
            }

        tools = self._convert_tools(body.get("tools"))
        if tools:
            inner["tools"] = tools
            tool_config = self._convert_tool_config(body.get("tool_choice"), tools)
            if tool_config:
                inner["toolConfig"] = tool_config

        inner["labels"] = labels
        inner["generationConfig"] = generation_config
        inner["sessionId"] = self._session_id(account)

        request.body = {
            "project": self._project(account),
            "requestId": request_id,
            "request": inner,
            "model": canonical_model,
            "userAgent": "antigravity",
            "requestType": "agent",
        }
        return request

    # ------------------------------------------------------------------
    # Response transformation (non-streaming)
    # ------------------------------------------------------------------
    def transform_response(self, response: ProxyResponse, account: Account) -> ProxyResponse:
        """Convert a Gemini ``GenerateContentResponse`` into OpenAI format."""
        if response.status_code >= 400:
            return response

        body = response.body
        if not isinstance(body, dict):
            body = self._as_dict(response.raw_text)
        payload = self._unwrap_response(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
            return response

        candidate = payload["candidates"][0] if payload["candidates"] else {}
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text, reasoning, tool_calls = self._parts_to_message(parts)

        message: Dict[str, Any] = {"role": "assistant"}
        if tool_calls:
            message["content"] = text or None
            message["tool_calls"] = tool_calls
        else:
            message["content"] = text
        if reasoning:
            message["reasoning_content"] = reasoning

        finish_reason = self._finish_reason(candidate.get("finishReason"), bool(tool_calls))
        model = (
            response.metadata.get("antigravity_model")
            or payload.get("modelVersion")
            or ""
        )

        converted = {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": self._map_usage(payload.get("usageMetadata")),
        }
        response.body = converted
        response.raw_text = json.dumps(converted, ensure_ascii=False)
        return response

    # ------------------------------------------------------------------
    # Streaming transformation (Gemini SSE -> OpenAI SSE)
    # ------------------------------------------------------------------
    def transform_stream_chunk(self, chunk: bytes, account: Account) -> bytes:
        """Buffer Gemini SSE frames and emit OpenAI ChatCompletionChunks."""
        state = _STREAM_STATE.get() or self._fallback_stream_state(account)
        if state is None:
            return chunk
        if state.get("passthrough"):
            return chunk

        state["buffer"] = state.get("buffer", b"") + chunk
        out = self._drain_sse_buffer(state)

        # Upstream errors are usually a bare JSON document (not SSE).  Forward
        # them verbatim so ``detect_error_or_limit`` can parse the payload.
        buffer = state.get("buffer", b"")
        if (
            not state.get("started")
            and not out
            and buffer
            and b"data:" not in buffer
            and b'"error"' in buffer
        ):
            out = buffer
            state["buffer"] = b""
            state["passthrough"] = True
        return out

    def finalize_stream(
        self,
        account: Account,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Flush the final buffered event, emit a finish chunk, and send [DONE]."""
        state: Optional[Dict[str, Any]] = None
        stream_id = (metadata or {}).get("_antigravity_stream_id")
        if stream_id:
            state = _STREAM_STATES.pop(stream_id, None)
        if state is None:
            state = _STREAM_STATE.get()
        if state is None:
            return b""

        out = b""
        try:
            if state.get("passthrough"):
                return b""

            if state.get("buffer"):
                out += self._drain_sse_buffer(state, final=True)

            if state.get("started"):
                if not state.get("finish_sent"):
                    usage = state.get("usage") if not state.get("usage_sent") else None
                    out += self._chunk(state, {}, "stop", usage=usage)
                    state["finish_sent"] = True
                    if usage is not None:
                        state["usage_sent"] = True
                if state.get("usage") and not state.get("usage_sent"):
                    out += self._usage_chunk(state)
                    state["usage_sent"] = True
                out += b"data: [DONE]\n\n"
        finally:
            _STREAM_STATE.set(None)
        return out

    # ------------------------------------------------------------------
    # Error / quota detection
    # ------------------------------------------------------------------
    def detect_error_or_limit(
        self,
        status_code: int,
        response_text: str,
        headers: Dict[str, str],
    ) -> ErrorCheckResult:
        text = response_text or ""
        lowered = text.lower()
        message = self._error_message(text)

        is_quota = any(
            token in lowered
            for token in (
                "resource_exhausted",
                "quota_exhausted",
                "individual quota reached",
                "quota exceeded",
                "rate limit",
            )
        )
        if status_code == 429 or (status_code == 409 and is_quota) or is_quota:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=self._cooldown_seconds(text, headers),
                error_message=message or "HTTP 429 / RESOURCE_EXHAUSTED quota exhausted",
                # Do not move quota-limited traffic to another Google account.
                # The router should surface the limit and let the caller retry later.
                should_fallback=False,
            )

        is_auth = any(
            token in lowered
            for token in ("unauthenticated", "permission_denied", "invalid_grant")
        )
        if status_code in (401, 403) or is_auth:
            return ErrorCheckResult(
                is_error=True,
                # Temporarily quarantine the credential after auth/policy denial
                # so subsequent requests do not keep hitting the same account.
                is_rate_limited=True,
                cooldown_seconds=3600.0,
                error_message=message or f"HTTP {status_code} authentication error",
                # Credential/account restrictions should not trigger account hopping.
                should_fallback=False,
            )

        if status_code >= 500:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=False,
                cooldown_seconds=15.0,
                error_message=message or f"HTTP {status_code} upstream server error",
                should_fallback=True,
            )

        if status_code >= 400:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=False,
                error_message=message or f"HTTP {status_code} upstream error",
                should_fallback=True,
            )

        return ErrorCheckResult(is_error=False, should_fallback=False)

    # ------------------------------------------------------------------
    # Model helpers
    # ------------------------------------------------------------------
    def _resolve_model(self, model: str) -> Tuple[str, Dict[str, Any]]:
        canonical = self.MODEL_ALIASES.get(model, model)
        config = self.MODEL_CONFIGS.get(canonical)
        if config is not None:
            return canonical, config

        # Unknown IDs still get a plausible envelope; upstream will reject
        # truly invalid models.  Keep the requested ID in the top-level field.
        if canonical.startswith("claude"):
            return canonical, self.MODEL_CONFIGS["claude-sonnet-4-6"]
        if canonical.startswith("gpt"):
            return canonical, self.MODEL_CONFIGS["gpt-oss-120b-medium"]
        return canonical, self.MODEL_CONFIGS[self.DEFAULT_MODEL]

    def _session_id(self, account: Account) -> str:
        configured = account.extra_config.get("session_id") or account.extra_config.get(
            "sessionId"
        )
        if configured is not None:
            try:
                return str(int(str(configured).strip()))
            except (TypeError, ValueError):
                pass
        digest = hashlib.sha256(f"antigravity-session:{account.id}".encode("utf-8")).digest()
        return str(int.from_bytes(digest[:8], "big", signed=True))

    def _project(self, account: Account) -> str:
        configured = (
            account.extra_config.get("project")
            or account.extra_config.get("cloudaicompanion_project")
            or account.extra_config.get("cloudaicompanionProject")
        )
        return str(configured or self.DEFAULT_PROJECT)

    # ------------------------------------------------------------------
    # Envelope helpers
    # ------------------------------------------------------------------
    def _generation_url(self, account: Account, stream: bool) -> str:
        base = self.get_base_url(account).rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        if ":streamGenerateContent" in base or ":generateContent" in base:
            return base
        if stream:
            return f"{base}/v1internal:streamGenerateContent?alt=sse"
        return f"{base}/v1internal:generateContent"

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, (str, bytes, bytearray)):
            try:
                decoded = json.loads(value)
            except Exception:
                return {}
            return decoded if isinstance(decoded, dict) else {}
        return {}

    @staticmethod
    def _is_wrapped(body: Dict[str, Any]) -> bool:
        return (
            isinstance(body.get("request"), dict)
            and "requestType" in body
            and "project" in body
        )

    def _conversation_id(
        self,
        request: ProxyRequest,
        account: Account,
        messages: List[Dict[str, Any]],
        system_text: str,
    ) -> str:
        for source in (
            request.metadata.get("conversation_id"),
            request.metadata.get("cascade_id"),
            account.extra_config.get("conversation_id"),
            account.extra_config.get("cascade_id"),
        ):
            if source:
                return str(source)

        first_user = ""
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "user":
                first_user = self._content_to_text(message.get("content"))
                if first_user:
                    break

        seed = f"{account.id}\0{system_text}\0{first_user}"
        if not first_user and not system_text:
            return str(uuid.uuid4())
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(uuid.UUID(bytes=digest[:16], version=4))

    def _trajectory_id(self, conversation_id: str, contents: List[Dict[str, Any]]) -> str:
        user_turns = 0
        for item in contents:
            if item.get("role") != "user":
                continue
            parts = item.get("parts") or []
            if not any("functionResponse" in part for part in parts if isinstance(part, dict)):
                user_turns += 1
        user_turns = max(user_turns, 1)
        seed = f"antigravity-trajectory:{conversation_id}:{user_turns}"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(uuid.UUID(bytes=digest[:16], version=4))

    # ------------------------------------------------------------------
    # OpenAI -> Gemini conversion
    # ------------------------------------------------------------------
    def _convert_messages(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], str]:
        system_chunks: List[str] = []
        contents: List[Dict[str, Any]] = []
        tool_names: Dict[str, str] = {}

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")

            if role in ("system", "developer"):
                text = self._content_to_text(content)
                if text:
                    system_chunks.append(text)
                continue

            if role == "tool":
                call_id = str(message.get("tool_call_id") or "")
                name = str(message.get("name") or tool_names.get(call_id) or "tool")
                text = self._content_to_text(content)
                function_response: Dict[str, Any] = {
                    "name": name,
                    "response": {"output": text},
                }
                if call_id:
                    function_response["id"] = call_id
                self._append_content(
                    contents, "user", [{"functionResponse": function_response}]
                )
                continue

            if role == "assistant":
                parts: List[Dict[str, Any]] = []
                text = self._content_to_text(content)
                if text:
                    parts.append({"text": text})
                for call in message.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") or {}
                    if not isinstance(function, dict):
                        continue
                    name = str(function.get("name") or "")
                    arguments = self._parse_arguments(function.get("arguments"))
                    function_call: Dict[str, Any] = {
                        "name": name,
                        "args": arguments,
                    }
                    call_id = call.get("id")
                    if call_id:
                        call_id = str(call_id)
                        function_call["id"] = call_id
                        tool_names[call_id] = name
                    parts.append({"functionCall": function_call})
                if parts:
                    self._append_content(contents, "model", parts)
                continue

            # user and any unknown client role becomes a user turn
            parts = self._content_to_parts(content)
            if parts:
                self._append_content(contents, "user", parts)

        return contents, "\n\n".join(system_chunks)

    @staticmethod
    def _append_content(
        contents: List[Dict[str, Any]], role: str, parts: List[Dict[str, Any]]
    ) -> None:
        if contents and contents[-1].get("role") == role:
            contents[-1].setdefault("parts", []).extend(parts)
        else:
            contents.append({"role": role, "parts": parts})

    @staticmethod
    def _parse_arguments(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except Exception:
                return {"value": value}
        if value is None:
            return {}
        return {"value": value}

    def _content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            pieces: List[str] = []
            for item in content:
                if isinstance(item, str):
                    pieces.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        pieces.append(text)
            return "".join(pieces)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
        return ""

    def _content_to_parts(self, content: Any) -> List[Dict[str, Any]]:
        if content is None:
            return []
        if isinstance(content, str):
            return [{"text": content}]
        if isinstance(content, dict):
            content = [content]
        if not isinstance(content, list):
            return [{"text": str(content)}]

        parts: List[Dict[str, Any]] = []
        for block in content:
            if isinstance(block, str):
                parts.append({"text": block})
                continue
            if not isinstance(block, dict):
                parts.append({"text": str(block)})
                continue

            block_type = block.get("type")
            if block_type in ("text", "input_text", "output_text") or "text" in block:
                text = block.get("text")
                if isinstance(text, str) and text:
                    parts.append({"text": text})
                continue

            if block_type == "image_url":
                image_url = block.get("image_url")
                if isinstance(image_url, dict):
                    image_url = image_url.get("url")
                inline = self._image_part(str(image_url or ""), block.get("mime_type"))
                if inline:
                    parts.append(inline)
                continue

            if block_type in ("image", "document"):
                source = block.get("source") or {}
                if isinstance(source, dict) and source.get("type") == "base64":
                    parts.append(
                        {
                            "inlineData": {
                                "mimeType": source.get("media_type")
                                or block.get("mime_type")
                                or "application/octet-stream",
                                "data": source.get("data") or "",
                            }
                        }
                    )
                elif isinstance(source, dict) and source.get("type") == "url":
                    parts.append(
                        {
                            "fileData": {
                                "fileUri": source.get("url") or "",
                                "mimeType": source.get("media_type")
                                or block.get("mime_type")
                                or "application/octet-stream",
                            }
                        }
                    )
                continue

        return parts

    @staticmethod
    def _image_part(url: str, mime_type: Any = None) -> Optional[Dict[str, Any]]:
        if not url:
            return None
        if url.startswith("data:"):
            header, _, data = url.partition(",")
            mime = "image/jpeg"
            if ";" in header:
                mime = header[5:].split(";", 1)[0] or mime
            return {"inlineData": {"mimeType": str(mime_type or mime), "data": data}}
        return {
            "fileData": {
                "fileUri": url,
                "mimeType": str(mime_type or "image/jpeg"),
            }
        }

    def _convert_tools(self, tools: Any) -> List[Dict[str, Any]]:
        if not isinstance(tools, list):
            return []
        converted: List[Dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function") if tool.get("type") == "function" else tool
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not name:
                continue
            declaration: Dict[str, Any] = {"name": str(name)}
            description = function.get("description")
            if description:
                declaration["description"] = str(description)
            parameters = function.get("parameters") or function.get("input_schema")
            if isinstance(parameters, dict):
                declaration["parameters"] = self._convert_schema(parameters)
            converted.append({"functionDeclarations": [declaration]})
        return converted

    def _convert_schema(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return schema

        allowed = {
            "type",
            "description",
            "enum",
            "items",
            "properties",
            "required",
            "nullable",
            "format",
            "minimum",
            "maximum",
            "minItems",
            "maxItems",
            "minLength",
            "maxLength",
            "pattern",
            "anyOf",
            "oneOf",
            "allOf",
        }
        converted: Dict[str, Any] = {}
        for key, value in schema.items():
            if key not in allowed:
                continue
            if key == "type" and isinstance(value, str):
                converted[key] = value.upper()
            elif key == "properties" and isinstance(value, dict):
                converted[key] = {
                    str(prop): self._convert_schema(prop_schema)
                    for prop, prop_schema in value.items()
                }
            elif key == "items":
                converted[key] = self._convert_schema(value)
            elif key in ("anyOf", "oneOf", "allOf") and isinstance(value, list):
                converted[key] = [self._convert_schema(item) for item in value]
            else:
                converted[key] = value

        if "properties" in converted and "type" not in converted:
            converted["type"] = "OBJECT"
        return converted

    def _convert_tool_config(self, tool_choice: Any, tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if tool_choice is None:
            return None
        if isinstance(tool_choice, str):
            mode = {
                "auto": "AUTO",
                "none": "NONE",
                "required": "ANY",
                "any": "ANY",
            }.get(tool_choice.lower())
            if not mode or mode == "AUTO":
                return None
            return {"functionCallingConfig": {"mode": mode}}
        if isinstance(tool_choice, dict):
            function = tool_choice.get("function")
            name = None
            if isinstance(function, dict):
                name = function.get("name")
            name = name or tool_choice.get("name")
            if name:
                return {
                    "functionCallingConfig": {
                        "mode": "ANY",
                        "allowedFunctionNames": [str(name)],
                    }
                }
        return None

    # ------------------------------------------------------------------
    # Gemini -> OpenAI response helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _unwrap_response(body: Any) -> Any:
        if isinstance(body, dict) and isinstance(body.get("response"), dict):
            return body["response"]
        return body

    def _parts_to_message(
        self, parts: Any
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        text_chunks: List[str] = []
        reasoning_chunks: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        for part in parts or []:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                if part.get("thought"):
                    reasoning_chunks.append(text)
                else:
                    text_chunks.append(text)
                continue
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                call_id = function_call.get("id") or f"call_{uuid.uuid4().hex[:24]}"
                tool_calls.append(
                    {
                        "id": str(call_id),
                        "type": "function",
                        "function": {
                            "name": str(function_call.get("name") or ""),
                            "arguments": json.dumps(
                                function_call.get("args") or {},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    }
                )

        return "".join(text_chunks), "".join(reasoning_chunks), tool_calls

    @staticmethod
    def _finish_reason(reason: Any, has_tool_calls: bool) -> str:
        if has_tool_calls:
            return "tool_calls"
        return {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "BLOCKLIST": "content_filter",
            "PROHIBITED_CONTENT": "content_filter",
            "SPII": "content_filter",
        }.get(str(reason or ""), "stop")

    @staticmethod
    def _map_usage(usage: Any) -> Dict[str, Any]:
        if not isinstance(usage, dict):
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        prompt_tokens = int(usage.get("promptTokenCount") or 0)
        completion_tokens = int(usage.get("candidatesTokenCount") or 0)
        total_tokens = int(
            usage.get("totalTokenCount") or prompt_tokens + completion_tokens
        )
        mapped: Dict[str, Any] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        cached = usage.get("cachedContentTokenCount")
        if cached is not None:
            mapped["prompt_tokens_details"] = {"cached_tokens": int(cached or 0)}
        thoughts = usage.get("thoughtsTokenCount")
        if thoughts is not None:
            mapped["completion_tokens_details"] = {
                "reasoning_tokens": int(thoughts or 0)
            }
        return mapped

    @staticmethod
    def _error_message(text: str) -> str:
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except Exception:
            return text.strip()[:500]
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if parsed.get("message"):
                return str(parsed["message"])
        return text.strip()[:500]

    @staticmethod
    def _cooldown_seconds(text: str, headers: Dict[str, str]) -> float:
        # Google may report reset details in ErrorInfo/RetryInfo metadata rather
        # than the top-level message. Parse JSON first so nested fields and
        # absolute reset timestamps are handled without brittle regex matching.
        try:
            payload = json.loads(text or "")
        except (TypeError, ValueError):
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")
            details = error.get("details") if isinstance(error, dict) else None
            if isinstance(details, list):
                now = time.time()
                for detail in details:
                    if not isinstance(detail, dict):
                        continue
                    metadata = detail.get("metadata")
                    if isinstance(metadata, dict):
                        for key in ("quotaResetTimeStamp", "quotaResetTimestamp"):
                            value = metadata.get(key)
                            if isinstance(value, str):
                                try:
                                    from datetime import datetime
                                    reset_at = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
                                    if reset_at > now:
                                        return max(reset_at - now, 1.0)
                                except (TypeError, ValueError, OverflowError):
                                    pass
                    retry_delay = detail.get("retryDelay")
                    if isinstance(retry_delay, str):
                        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)s\s*", retry_delay)
                        if match:
                            return max(float(match.group(1)), 1.0)

        for pattern in (
            r'"retryDelay"\s*:\s*"([0-9.]+)s"',
            r'"quotaResetDelay"\s*:\s*"([0-9.]+)s"',
        ):
            match = re.search(pattern, text or "")
            if match:
                try:
                    return max(float(match.group(1)), 1.0)
                except ValueError:
                    pass
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
        return 60.0

    # ------------------------------------------------------------------
    # Stream state helpers
    # ------------------------------------------------------------------
    def _bind_stream_state(
        self, request: ProxyRequest, account: Account, model: str
    ) -> None:
        if not request.is_stream:
            return
        stream_id = request.metadata.get("_antigravity_stream_id")
        if not stream_id:
            stream_id = uuid.uuid4().hex
            request.metadata["_antigravity_stream_id"] = stream_id
            self._prune_stream_states()
            _STREAM_STATES[stream_id] = {
                "id": stream_id,
                "account_id": account.id,
                "model": model,
                "response_id": f"chatcmpl-{uuid.uuid4().hex}",
                "created": int(time.time()),
                "created_at": time.time(),
                "buffer": b"",
                "started": False,
                "finish_sent": False,
                "usage": None,
                "usage_sent": False,
                "tool_indices": {},
                "next_tool_index": 0,
                "tool_call_seen": False,
                "passthrough": False,
            }
        state = _STREAM_STATES.get(stream_id)
        if state is not None:
            state["model"] = model
            _STREAM_STATE.set(state)

    def _fallback_stream_state(self, account: Account) -> Optional[Dict[str, Any]]:
        matches = [
            state
            for state in _STREAM_STATES.values()
            if state.get("account_id") == account.id
        ]
        return matches[-1] if len(matches) == 1 else None

    @staticmethod
    def _prune_stream_states() -> None:
        if len(_STREAM_STATES) < 256:
            return
        cutoff = time.time() - 900
        for stream_id, state in list(_STREAM_STATES.items()):
            if state.get("created_at", 0) < cutoff:
                _STREAM_STATES.pop(stream_id, None)

    def _drain_sse_buffer(
        self, state: Dict[str, Any], final: bool = False
    ) -> bytes:
        buffer = state.get("buffer", b"")
        out = b""
        while True:
            index, separator_length = self._next_event_boundary(buffer)
            if index < 0:
                break
            event = buffer[:index]
            buffer = buffer[index + separator_length:]
            out += self._convert_sse_event(event, state)
        state["buffer"] = buffer

        if final and buffer.strip():
            out += self._convert_sse_event(buffer, state)
            state["buffer"] = b""
        return out

    @staticmethod
    def _next_event_boundary(buffer: bytes) -> Tuple[int, int]:
        candidates = []
        for separator in (b"\r\n\r\n", b"\n\n"):
            index = buffer.find(separator)
            if index >= 0:
                candidates.append((index, len(separator)))
        if not candidates:
            return -1, 0
        return min(candidates, key=lambda item: item[0])

    def _convert_sse_event(self, event: bytes, state: Dict[str, Any]) -> bytes:
        try:
            text = event.decode("utf-8")
        except UnicodeDecodeError:
            return event

        out = b""
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                out += b"data: [DONE]\n\n"
                continue
            try:
                parsed = json.loads(data)
            except Exception:
                continue
            if isinstance(parsed, dict) and "error" in parsed:
                out += b"data: " + json.dumps(parsed, ensure_ascii=False).encode("utf-8") + b"\n\n"
                continue
            payload = parsed.get("response", parsed) if isinstance(parsed, dict) else {}
            out += self._convert_stream_payload(payload, state)
        return out

    def _convert_stream_payload(self, payload: Any, state: Dict[str, Any]) -> bytes:
        if not isinstance(payload, dict):
            return b""

        usage = payload.get("usageMetadata")
        if isinstance(usage, dict):
            state["usage"] = self._map_usage(usage)

        out = b""
        candidates = payload.get("candidates")
        if isinstance(candidates, list) and candidates:
            candidate = candidates[0] if isinstance(candidates[0], dict) else {}
            content = candidate.get("content") or {}
            parts = content.get("parts") or []

            if not state.get("started"):
                out += self._chunk(state, {"role": "assistant", "content": ""}, None)
                state["started"] = True

            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    if part.get("thought"):
                        out += self._chunk(state, {"reasoning_content": text}, None)
                    else:
                        out += self._chunk(state, {"content": text}, None)
                    continue

                function_call = part.get("functionCall")
                if isinstance(function_call, dict):
                    call_id = str(
                        function_call.get("id") or f"call_{uuid.uuid4().hex[:24]}"
                    )
                    indices = state.setdefault("tool_indices", {})
                    if call_id not in indices:
                        indices[call_id] = state.get("next_tool_index", 0)
                        state["next_tool_index"] = indices[call_id] + 1
                    tool_delta = {
                        "tool_calls": [
                            {
                                "index": indices[call_id],
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": str(function_call.get("name") or ""),
                                    "arguments": json.dumps(
                                        function_call.get("args") or {},
                                        ensure_ascii=False,
                                        separators=(",", ":"),
                                    ),
                                },
                            }
                        ]
                    }
                    state["tool_call_seen"] = True
                    out += self._chunk(state, tool_delta, None)

            reason = candidate.get("finishReason")
            if reason and not state.get("finish_sent"):
                finish_reason = self._finish_reason(
                    reason, bool(state.get("tool_call_seen"))
                )
                finish_usage = None
                if state.get("usage") and not state.get("usage_sent"):
                    finish_usage = state["usage"]
                    state["usage_sent"] = True
                out += self._chunk(state, {}, finish_reason, usage=finish_usage)
                state["finish_sent"] = True

        if (
            state.get("finish_sent")
            and state.get("usage")
            and not state.get("usage_sent")
        ):
            out += self._usage_chunk(state)
            state["usage_sent"] = True

        return out

    @staticmethod
    def _chunk(
        state: Dict[str, Any],
        delta: Dict[str, Any],
        finish_reason: Optional[str],
        usage: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        payload: Dict[str, Any] = {
            "id": state["response_id"],
            "object": "chat.completion.chunk",
            "created": state["created"],
            "model": state["model"],
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        if usage is not None:
            payload["usage"] = usage
        return b"data: " + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8") + b"\n\n"

    @staticmethod
    def _usage_chunk(state: Dict[str, Any]) -> bytes:
        payload = {
            "id": state["response_id"],
            "object": "chat.completion.chunk",
            "created": state["created"],
            "model": state["model"],
            "choices": [],
            "usage": state.get("usage"),
        }
        return b"data: " + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8") + b"\n\n"
