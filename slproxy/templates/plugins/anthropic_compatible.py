"""
Anthropic Compatible Provider Plugin
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class AnthropicCompatiblePlugin(BasePlugin):
    id: str = "anthropic_compatible"
    name: str = "Anthropic Compatible"
    description: str = "Generic Anthropic Messages API compatible proxy"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "box"
    color: str = "#4F46E5"
    default_base_url: str = "https://api.anthropic.com/v1"
    format: str = "anthropic"

    models: List[ModelInfo] = [
        ModelInfo(
            id="claude-3-5-sonnet-20241022",
            name="Claude 3.5 Sonnet",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="claude-3-5-haiku-20241022",
            name="Claude 3.5 Haiku",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="claude-3-opus-20240229",
            name="Claude 3 Opus",
            context_window=200000,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
    ]

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        if request.url == self.default_base_url or request.url == self.default_base_url + "/":
            request.url = f"{self.default_base_url}/messages"
        return request
