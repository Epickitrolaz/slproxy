"""
AgentRouter Provider Plugin
"""

import uuid
from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class AgentRouterPlugin(BasePlugin):
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

    @staticmethod
    def generate_session_id() -> str:
        return f"ses_{uuid.uuid4().hex}"

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        headers = super().build_headers(account, stream)
        # Specifically injects opencode client headers to bypass client restriction
        headers["User-Agent"] = self.CLIENT_USER_AGENT
        session_id = account.extra_config.get("session_id") or self.generate_session_id()
        headers["x-opencode-session"] = session_id
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        # Specifically injects opencode client headers to bypass client restriction
        request.headers["User-Agent"] = self.CLIENT_USER_AGENT
        if "x-opencode-session" not in request.headers:
            session_id = account.extra_config.get("session_id") or self.generate_session_id()
            request.headers["x-opencode-session"] = session_id
        return request
