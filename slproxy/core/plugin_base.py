"""
SLProxy Plugin Base Interfaces and Data Models
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time


class ModelInfo(BaseModel):
    id: str
    name: str
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    pricing: Dict[str, float] = Field(default_factory=dict)  # prompt, completion per 1k tokens
    extra: Dict[str, Any] = Field(default_factory=dict)


class Account(BaseModel):
    id: str
    provider_id: str
    name: str
    api_key: str = ""
    base_url: Optional[str] = None
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_config: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 1
    weight: int = 1
    is_active: bool = True
    rate_limited_until: Optional[float] = None
    error_count: int = 0
    success_count: int = 0
    last_used_at: Optional[float] = None

    def is_available(self, now: Optional[float] = None) -> bool:
        if not self.is_active:
            return False
        current_time = now if now is not None else time.time()
        if self.rate_limited_until is not None and self.rate_limited_until > current_time:
            return False
        return True


class ProxyRequest(BaseModel):
    method: str = "POST"
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Any = Field(default_factory=dict)
    is_stream: bool = True
    model: str = ""
    client_format: str = "openai"  # "openai" or "anthropic"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProxyResponse(BaseModel):
    status_code: int
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Any = None
    raw_text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ErrorCheckResult(BaseModel):
    is_error: bool = False
    is_rate_limited: bool = False
    cooldown_seconds: float = 60.0
    error_message: str = ""
    should_fallback: bool = False


class BasePlugin:
    """
    Every SLProxy plugin is a simple Python program subclassing BasePlugin.
    It defines provider capabilities, headers, request transformations,
    stream interceptors, and custom error/quota detection.
    """

    id: str = "base"
    name: str = "Base Provider"
    description: str = "Base provider plugin description"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "cpu"
    color: str = "#6B7280"
    default_base_url: str = ""
    format: str = "openai"  # "openai", "anthropic", etc.
    models: List[ModelInfo] = []
    enabled: bool = True

    def __init__(self):
        pass

    def get_base_url(self, account: Optional[Account] = None) -> str:
        if account and account.base_url:
            return account.base_url.rstrip("/")
        return self.default_base_url.rstrip("/")

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SLProxy/1.0",
        }
        if stream:
            headers["Accept"] = "text/event-stream"
        else:
            headers["Accept"] = "application/json"

        if account.api_key:
            if self.format == "anthropic":
                headers["x-api-key"] = account.api_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = f"Bearer {account.api_key}"

        if account.extra_headers:
            headers.update(account.extra_headers)

        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Hook called before sending request upstream.
        Can rewrite URLs, mutate body, inject headers (e.g. Claude spoof headers).
        """
        return request

    def transform_response(self, response: ProxyResponse, account: Account) -> ProxyResponse:
        """
        Hook called for non-streaming responses before returning to caller.
        """
        return response

    def transform_stream_chunk(self, chunk: bytes, account: Account) -> bytes:
        """
        Hook called for each chunk in SSE streaming.
        """
        return chunk

    def detect_error_or_limit(self, status_code: int, response_text: str, headers: Dict[str, str]) -> ErrorCheckResult:
        """
        Hook to detect if the response is an error or quota/rate limit.
        Allows custom inspection (e.g. upstreams returning 200 OK with limit message text).
        """
        if status_code == 429:
            retry_after = 60.0
            if "retry-after" in headers:
                try:
                    retry_after = float(headers["retry-after"])
                except Exception:
                    pass
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=retry_after,
                error_message="HTTP 429 Rate Limited",
                should_fallback=True
            )
        elif status_code in (401, 403):
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=False,
                error_message=f"HTTP {status_code} Authentication / Authorization Error",
                should_fallback=True
            )
        elif status_code >= 500:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=False,
                cooldown_seconds=15.0,
                error_message=f"HTTP {status_code} Upstream Server Error",
                should_fallback=True
            )
        return ErrorCheckResult(is_error=False, should_fallback=False)

    def fetch_models(self, account: Optional[Account] = None) -> List[ModelInfo]:
        """
        Return the list of supported models. If account has custom models configured,
        returns those or merges them.
        """
        if account and "models" in account.extra_config and isinstance(account.extra_config["models"], list):
            custom_models = []
            for m in account.extra_config["models"]:
                if isinstance(m, dict):
                    custom_models.append(ModelInfo(**m))
                elif isinstance(m, str):
                    custom_models.append(ModelInfo(id=m, name=m))
            if custom_models:
                return custom_models
        return self.models

    def add_model(self, model: ModelInfo) -> bool:
        """
        Add a model to the plugin's supported models list if not already present.
        """
        for i, existing in enumerate(self.models):
            if existing.id == model.id:
                self.models[i] = model
                return True
        self.models.append(model)
        return True

    def remove_model(self, model_id: str) -> bool:
        """
        Remove a model from the plugin's supported models list.
        """
        initial_len = len(self.models)
        self.models = [m for m in self.models if m.id != model_id]
        return len(self.models) < initial_len
