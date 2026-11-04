"""
OpenRouter Provider Plugin
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class OpenRouterPlugin(BasePlugin):
    id: str = "openrouter"
    name: str = "OpenRouter"
    description: str = "OpenRouter AI model routing and aggregation service"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "globe"
    color: str = "#6366F1"
    default_base_url: str = "https://openrouter.ai/api/v1"
    format: str = "openai"

    models: List[ModelInfo] = [
        ModelInfo(
            id="openai/gpt-4o",
            name="OpenAI: GPT-4o",
            context_window=128000,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="anthropic/claude-3.5-sonnet",
            name="Anthropic: Claude 3.5 Sonnet",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="deepseek/deepseek-r1",
            name="DeepSeek: R1 Reasoning",
            context_window=64000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
        ModelInfo(
            id="meta-llama/llama-3.3-70b-instruct",
            name="Meta: Llama 3.3 70B Instruct",
            context_window=128000,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
        ModelInfo(
            id="google/gemini-2.0-flash-001",
            name="Google: Gemini 2.0 Flash",
            context_window=1048576,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="mistralai/mistral-large-2411",
            name="Mistral: Mistral Large 2411",
            context_window=128000,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
    ]

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        headers = super().build_headers(account, stream)
        headers["HTTP-Referer"] = account.extra_config.get("referer", "https://slproxy.ai")
        headers["X-Title"] = account.extra_config.get("title", "SLProxy")
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        if "HTTP-Referer" not in request.headers:
            request.headers["HTTP-Referer"] = account.extra_config.get("referer", "https://slproxy.ai")
        if "X-Title" not in request.headers:
            request.headers["X-Title"] = account.extra_config.get("title", "SLProxy")
        return request
