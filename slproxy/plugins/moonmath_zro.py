"""
Moonmath Zro Provider Plugin
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ErrorCheckResult, ModelInfo, ProxyRequest


class MoonmathZroPlugin(BasePlugin):
    id: str = "moonmath_zro"
    name: str = "Moonmath Zro"
    description: str = "Moonmath Zro provider plugin with in-depth quota, limit, and silent error detection"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "zap"
    color: str = "#EC4899"
    default_base_url: str = "https://api.moonmath.ai/v1"
    format: str = "openai"

    QUOTA_LIMIT_PATTERNS: List[str] = [
        "limit reached",
        "quota exceeded",
        "rate limit",
        "insufficient quota",
        "exceeded your current quota",
        "usage limit",
        "out of credits",
        "daily limit",
        "credit limit",
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
        headers: Dict[str, str]
    ) -> ErrorCheckResult:
        """
        Inspects status code and response body text for rate limits or quota exhaustion,
        including 200 OK responses containing quota/limit error messages.
        """
        text_lower = response_text.lower() if response_text else ""
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
                    error_message=f"Moonmath Zro limit or quota exceeded: '{pattern}'",
                    should_fallback=True,
                )

        # Delegate standard status code handling (429, 401, 500, etc.)
        return super().detect_error_or_limit(status_code, response_text, headers)

    def check_chunk_for_limit(self, chunk: bytes) -> Optional[ErrorCheckResult]:
        """
        Helper to inspect an SSE stream chunk for quota or limit errors.
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
        # Pass-through after inspection
        return chunk
