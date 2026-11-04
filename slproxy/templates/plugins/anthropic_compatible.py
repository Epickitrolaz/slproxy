"""
Anthropic Compatible Provider Plugin
====================================

Educational Reference Implementation for Generic Anthropic Messages Compatible Endpoints.

Overview & Architectural Rationale
-----------------------------------
This plugin enables proxying to third-party providers or custom enterprise endpoints
implementing Anthropic's Messages API specification (`/v1/messages`).

It automatically appends `/messages` if the target URL only contains the base host,
and attaches standard Anthropic authentication and version headers (`x-api-key`,
`anthropic-version: 2023-06-01`).
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class AnthropicCompatiblePlugin(BasePlugin):
    """
    Generic Anthropic Compatible provider plugin.
    """

    id: str = "anthropic_compatible"
    name: str = "Anthropic Compatible"
    description: str = "Generic Anthropic Messages API compatible proxy for standard Claude endpoints"
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
        """
        Normalizes base URL to /messages.
        """
        base = self.get_base_url(account).rstrip("/")
        if request.url in (base, f"{base}/"):
            request.url = f"{base}/messages"
        return request
