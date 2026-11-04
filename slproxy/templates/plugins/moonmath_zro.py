"""
Moonmath Zro Provider Plugin
============================

Educational Reference Implementation for Conversational Quota Limit Interception.

Overview & Architectural Rationale
-----------------------------------
Moonmath Zro and certain specialized AI aggregators do not reliably signal quota exhaustion,
rate limits, or tier depletion using standard HTTP status codes (such as HTTP 429 Too Many Requests).
Instead, they frequently return HTTP 200 OK with a standard completion envelope containing
conversational refusal text (e.g., "Daily limit reached for today", "You have quota exceeded",
or "Your account limit was reached").

If an API gateway treats all HTTP 200 responses as successes, users receive useless error strings
as model completions, and the proxy fails to failover to backup accounts.

This plugin implements:
1. Deep Text Inspection on HTTP 200 OK:
   Detects subtle conversational quota exhaustion indicators:
   - "daily limit reached"
   - "quota exceeded"
   - "limit was reached"
   - "limit reached"
   - "rate limit"
   - "insufficient quota"
   - "exceeded your current quota"
   - "usage limit"
   - "out of credits"
   - "credit limit"
2. Conversion to Actionable Rate Limit:
   Converts conversational 200 OK refusals into an `ErrorCheckResult` with `is_rate_limited=True`,
   `should_fallback=True`, and an appropriate cooldown period, allowing the router to automatically
   cycle to the next available account.
3. Streaming Chunk Inspection:
   Inspects SSE chunks for inline quota error fragments before forwarding to clients.
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ErrorCheckResult, ModelInfo, ProxyRequest


class MoonmathZroPlugin(BasePlugin):
    """
    Moonmath Zro provider plugin with verbose conversational quota/rate limit detection.
    """

    id: str = "moonmath_zro"
    name: str = "Moonmath Zro"
    description: str = "Moonmath Zro provider plugin with in-depth conversational quota, limit, and silent error detection"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "zap"
    color: str = "#EC4899"
    default_base_url: str = "https://api.moonmath.ai/v1"
    format: str = "openai"

    # Conversational text patterns returned under HTTP 200 OK when limits are reached
    QUOTA_LIMIT_PATTERNS: List[str] = [
        "daily limit reached",
        "quota exceeded",
        "limit was reached",
        "limit reached",
        "rate limit",
        "insufficient quota",
        "exceeded your current quota",
        "usage limit",
        "out of credits",
        "credit limit",
        "daily limit",
    ]

    models: List[ModelInfo] = [
        ModelInfo(
            id="moonmath-zro-v1",
            name="Moonmath Zro V1",
            context_window=128000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
        ModelInfo(
            id="moonmath-zro-pro",
            name="Moonmath Zro Pro",
            context_window=200000,
            max_output_tokens=16384,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="moonmath-zro-ultra",
            name="Moonmath Zro Ultra",
            context_window=200000,
            max_output_tokens=32768,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
    ]

    def detect_error_or_limit(
        self,
        status_code: int,
        response_text: str,
        headers: Dict[str, str],
    ) -> ErrorCheckResult:
        """
        Inspects status codes and conversational response text for quota and rate limits.

        Conversational Detection:
        -------------------------
        If status is 200 OK, examines the response body text. If any conversational quota pattern
        is found (e.g. 'daily limit reached', 'quota exceeded', 'limit was reached'), marks the
        response as a rate limit error with should_fallback=True so the router seamlessly retries
        with the next account in line.
        """
        text_lower = response_text.lower() if response_text else ""

        # Check conversational quota strings even on HTTP 200 OK
        for pattern in self.QUOTA_LIMIT_PATTERNS:
            if pattern in text_lower:
                cooldown = 60.0
                if "retry-after" in headers:
                    try:
                        cooldown = float(headers["retry-after"])
                    except Exception:
                        pass
                return ErrorCheckResult(
                    is_error=True,
                    is_rate_limited=True,
                    cooldown_seconds=cooldown,
                    error_message=f"Moonmath Zro conversational quota or limit exceeded: '{pattern}'",
                    should_fallback=True,
                )

        # Delegate standard HTTP errors (HTTP 429, 401, 403, 500) to base plugin
        return super().detect_error_or_limit(status_code, response_text, headers)

    def check_chunk_for_limit(self, chunk: bytes) -> Optional[ErrorCheckResult]:
        """
        Inspects an individual SSE stream chunk for conversational quota limit messages.
        """
        chunk_str = chunk.decode("utf-8", errors="ignore").lower()
        for pattern in self.QUOTA_LIMIT_PATTERNS:
            if pattern in chunk_str:
                return ErrorCheckResult(
                    is_error=True,
                    is_rate_limited=True,
                    cooldown_seconds=60.0,
                    error_message=f"Moonmath Zro stream limit detected: '{pattern}'",
                    should_fallback=True,
                )
        return None

    def transform_stream_chunk(self, chunk: bytes, account: Account) -> bytes:
        """
        Passes through stream chunk after inspection.
        """
        return chunk
