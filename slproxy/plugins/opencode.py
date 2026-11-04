"""
OpenCode Provider Plugin
"""

import uuid
from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class OpenCodePlugin(BasePlugin):
    id: str = "opencode"
    name: str = "OpenCode"
    description: str = "OpenCode CLI provider plugin with automated session and user-agent injection"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "terminal"
    color: str = "#10B981"
    default_base_url: str = "https://api.opencode.ai/v1"
    format: str = "openai"

    USER_AGENT: str = "opencode/latest/2.0.26/cli"

    models: List[ModelInfo] = [
        ModelInfo(
            id="opencode-v1",
            name="OpenCode V1",
            context_window=128000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
        ModelInfo(
            id="opencode-pro",
            name="OpenCode Pro",
            context_window=200000,
            max_output_tokens=16384,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="opencode-fast",
            name="OpenCode Fast",
            context_window=64000,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
    ]

    @staticmethod
    def generate_session_id() -> str:
        return f"ses_{uuid.uuid4().hex}"

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        headers = super().build_headers(account, stream)
        headers["User-Agent"] = self.USER_AGENT
        session_id = account.extra_config.get("session_id") or self.generate_session_id()
        headers["x-opencode-session"] = session_id
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        request.headers["User-Agent"] = self.USER_AGENT
        if "x-opencode-session" not in request.headers:
            session_id = account.extra_config.get("session_id") or self.generate_session_id()
            request.headers["x-opencode-session"] = session_id
        return request
