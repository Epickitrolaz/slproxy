"""
Anthropic Claude Code Provider Plugin
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class AnthropicClaudePlugin(BasePlugin):
    id: str = "anthropic_claude"
    name: str = "Anthropic Claude Code"
    description: str = "Anthropic Claude Code provider plugin with CLI spoof headers and beta flags"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "anthropic"
    color: str = "#D97706"
    default_base_url: str = "https://api.anthropic.com/v1"
    format: str = "anthropic"

    CLAUDE_CLI_SPOOF_HEADERS: Dict[str, str] = {
        "User-Agent": "claude-cli/1.0.0 (darwin-arm64) claude-code",
        "anthropic-client": "claude-code",
        "x-app": "claude-code",
    }

    ANTHROPIC_BETA: str = "prompt-caching-2024-07-31,tools-2024-04-04,computer-use-2024-10-22,output-128k-2025-02-19"

    models: List[ModelInfo] = [
        ModelInfo(
            id="claude-3-7-sonnet",
            name="Claude 3.7 Sonnet",
            context_window=200000,
            max_output_tokens=64000,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="claude-3-5-sonnet",
            name="Claude 3.5 Sonnet",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="claude-3-5-haiku",
            name="Claude 3.5 Haiku",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="claude-3-5-sonnet-20241022",
            name="Claude 3.5 Sonnet (2024-10-22)",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
    ]

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        headers = super().build_headers(account, stream)
        headers["anthropic-version"] = "2023-06-01"
        headers.update(self.CLAUDE_CLI_SPOOF_HEADERS)
        headers["anthropic-beta"] = self.ANTHROPIC_BETA
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        for k, v in self.CLAUDE_CLI_SPOOF_HEADERS.items():
            if k not in request.headers:
                request.headers[k] = v

        if "anthropic-beta" not in request.headers:
            request.headers["anthropic-beta"] = self.ANTHROPIC_BETA

        if "anthropic-version" not in request.headers:
            request.headers["anthropic-version"] = "2023-06-01"

        if request.url == self.default_base_url or request.url == self.default_base_url + "/":
            request.url = f"{self.default_base_url}/messages"

        return request
