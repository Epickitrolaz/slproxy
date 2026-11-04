"""
Anthropic Claude Code Provider Plugin
=====================================

Educational Reference Implementation with Stainless SDK Spoofing.

Overview & Architectural Rationale
-----------------------------------
Anthropic Claude Code is a CLI agent that interacts with Anthropic's Messages API
via the Stainless TypeScript SDK wrapper. Anthropic applies strict gateway heuristics
to differentiate official CLI instances from third-party automation.

To ensure seamless interoperability and bypass arbitrary client barriers,
this plugin injects the exact Stainless SDK headers and latest beta feature flags:

1. Headers Injected:
   - User-Agent: `claude-cli/2.1.280 (external, sdk-cli)`
     (Identifies the client as Claude Code CLI build 2.1.280 using external SDK wrappers).
   - Anthropic-Version: `2023-06-01`
     (The standard stable API version for Messages API).
   - Anthropic-Beta:
     `claude-code-20250219,interleaved-thinking-2025-05-14,context-management-2025-06-27,prompt-caching-scope-2026-01-05`
     (Enables Claude Code system tools, interleaved thinking tokens, 128k output,
      and prompt caching scopes).
   - X-App: `cli`
     (Informs upstream routing that traffic originates from the command-line interface).
   - X-Stainless-Runtime-Version: `v24.14.0`
     (Stainless runtime environment version, typically matching Node.js LTS).
   - X-Stainless-Arch: `arm64`
     (Architecture fingerprint).
   - X-Stainless-Os: `macOS`
     (Operating system fingerprint).
"""

import platform
from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class AnthropicClaudePlugin(BasePlugin):
    """
    Anthropic Claude Code provider plugin with comprehensive Stainless SDK spoofing.
    """

    id: str = "anthropic_claude"
    name: str = "Anthropic Claude Code"
    description: str = "Anthropic Claude Code provider plugin with Stainless SDK spoof headers and latest beta capabilities"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "anthropic"
    color: str = "#D97706"
    default_base_url: str = "https://api.anthropic.com/v1"
    format: str = "anthropic"

    # Exact Stainless SDK headers and flags
    STAINLESS_USER_AGENT: str = "claude-cli/2.1.280 (external, sdk-cli)"
    ANTHROPIC_VERSION: str = "2023-06-01"
    ANTHROPIC_BETA: str = (
        "claude-code-20250219,"
        "interleaved-thinking-2025-05-14,"
        "context-management-2025-06-27,"
        "prompt-caching-scope-2026-01-05"
    )
    X_APP: str = "cli"
    X_STAINLESS_RUNTIME_VERSION: str = "v24.14.0"
    DEFAULT_STAINLESS_ARCH: str = "arm64"
    DEFAULT_STAINLESS_OS: str = "macOS"

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

    @classmethod
    def get_stainless_headers(cls, arch: Optional[str] = None, os_name: Optional[str] = None) -> Dict[str, str]:
        """
        Returns full dictionary of Stainless spoof headers.
        """
        resolved_arch = arch or cls.DEFAULT_STAINLESS_ARCH
        resolved_os = os_name or cls.DEFAULT_STAINLESS_OS
        return {
            "User-Agent": cls.STAINLESS_USER_AGENT,
            "Anthropic-Version": cls.ANTHROPIC_VERSION,
            "Anthropic-Beta": cls.ANTHROPIC_BETA,
            "X-App": cls.X_APP,
            "anthropic-client": "claude-code",
            "X-Stainless-Runtime-Version": cls.X_STAINLESS_RUNTIME_VERSION,
            "X-Stainless-Arch": resolved_arch,
            "X-Stainless-Os": resolved_os,
        }

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        """
        Builds headers including auth, content type, and full Stainless SDK spoof headers.
        """
        headers = super().build_headers(account, stream)

        # Remove lowercase variants from base to prevent duplicate headers on the wire
        headers.pop("anthropic-version", None)
        headers.pop("anthropic-beta", None)
        headers.pop("x-app", None)

        arch = account.extra_config.get("stainless_arch", self.DEFAULT_STAINLESS_ARCH)
        os_name = account.extra_config.get("stainless_os", self.DEFAULT_STAINLESS_OS)

        spoof_headers = self.get_stainless_headers(arch=arch, os_name=os_name)
        headers.update(spoof_headers)

        # Standard Anthropic authentication
        if account.api_key:
            headers["x-api-key"] = account.api_key

        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Injects Stainless spoof headers into outgoing ProxyRequest and normalizes endpoint URL.
        """
        # Remove lowercase variants to prevent duplicate headers on the wire
        request.headers.pop("anthropic-version", None)
        request.headers.pop("anthropic-beta", None)
        request.headers.pop("x-app", None)

        arch = account.extra_config.get("stainless_arch", self.DEFAULT_STAINLESS_ARCH)
        os_name = account.extra_config.get("stainless_os", self.DEFAULT_STAINLESS_OS)
        spoof_headers = self.get_stainless_headers(arch=arch, os_name=os_name)

        for k, v in spoof_headers.items():
            if k not in request.headers:
                request.headers[k] = v

        # Normalize Anthropic messages endpoint URL
        base = self.get_base_url(account).rstrip("/")
        if request.url in (base, f"{base}/"):
            request.url = f"{base}/messages"

        return request
