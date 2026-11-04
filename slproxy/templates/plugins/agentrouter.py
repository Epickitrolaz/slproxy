"""
AgentRouter Provider Plugin
===========================

Educational Reference Implementation for OpenCode Header Injection.

Overview & Architectural Rationale
-----------------------------------
AgentRouter provides routed multi-model access behind gateways that restrict access
strictly to verified OpenCode clients. Direct API requests or non-CLI HTTP clients
receive HTTP 403 Forbidden or redirect challenges.

To bypass these client restrictions transparently:
1. Injects the strict OpenCode CLI User-Agent:
   `opencode/latest/2.0.26/cli`
2. Generates and injects the 48-bit descending-time session header:
   `x-opencode-session: ses_<descending_time_hex><random14>`
3. Upstream gateway decodes the descending timestamp, verifies client authenticity,
   and permits unrestricted model execution.
"""

import secrets
import time
from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest

BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class AgentRouterPlugin(BasePlugin):
    """
    AgentRouter provider plugin injecting OpenCode client fingerprints to bypass restrictions.
    """

    id: str = "agentrouter"
    name: str = "AgentRouter"
    description: str = "AgentRouter provider plugin injecting OpenCode client headers to bypass client restrictions"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "shield"
    color: str = "#8B5CF6"
    default_base_url: str = "https://agentrouter.org/v1"
    format: str = "openai"

    CLIENT_USER_AGENT: str = "opencode/latest/2.0.26/cli"

    models: List[ModelInfo] = [
        ModelInfo(
            id="agentrouter-default",
            name="AgentRouter Default",
            context_window=128000,
            max_output_tokens=8192,
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
            id="gpt-4o",
            name="GPT-4o",
            context_window=128000,
            max_output_tokens=16384,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="deepseek-coder",
            name="DeepSeek Coder",
            context_window=64000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
    ]

    @classmethod
    def generate_random_base62(cls, length: int = 14) -> str:
        """
        Generates random base62 characters for session suffix.
        """
        return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))

    @classmethod
    def generate_descending_time_hex(cls, time_ms: Optional[int] = None, counter: int = 0) -> str:
        """
        Computes 48-bit descending time hex token for OpenCode session generation.
        """
        if time_ms is None:
            time_ms = int(time.time() * 1000)
        safe_counter = counter & 0x0FFF
        packed = (int(time_ms) * 0x1000 + safe_counter)
        inverted = (~packed) & 0xFFFFFFFFFFFF
        return inverted.to_bytes(6, "big").hex()

    @classmethod
    def generate_session_id(cls, time_ms: Optional[int] = None, counter: int = 0) -> str:
        """
        Generates a valid OpenCode session ID token: ses_<descending_time_hex><random14>.
        """
        descending_hex = cls.generate_descending_time_hex(time_ms=time_ms, counter=counter)
        suffix = cls.generate_random_base62(14)
        return f"ses_{descending_hex}{suffix}"

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        """
        Builds headers injecting OpenCode client fingerprints:
        - User-Agent: opencode/latest/2.0.26/cli
        - x-opencode-session: ses_<descending_time_hex><random14>
        """
        headers = super().build_headers(account, stream)
        headers["User-Agent"] = self.CLIENT_USER_AGENT
        session_id = account.extra_config.get("session_id") or self.generate_session_id()
        headers["x-opencode-session"] = session_id
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Injects OpenCode client headers into outgoing request to bypass client restrictions.
        """
        request.headers["User-Agent"] = self.CLIENT_USER_AGENT
        if "x-opencode-session" not in request.headers:
            session_id = account.extra_config.get("session_id") or self.generate_session_id()
            request.headers["x-opencode-session"] = session_id
        return request
