"""
Google Antigravity Provider Plugin
"""

import uuid
from typing import Dict, List, Optional, Set
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class GoogleAntigravityPlugin(BasePlugin):
    id: str = "google_antigravity"
    name: str = "Google Antigravity"
    description: str = "Google Antigravity provider with IDE request/trajectory ID generation and field stripping"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "google"
    color: str = "#4285F4"
    default_base_url: str = "https://antigravity.google"
    format: str = "antigravity"

    DISALLOWED_FIELDS: Set[str] = {
        "frequency_penalty",
        "presence_penalty",
        "logprobs",
        "top_logprobs",
        "logit_bias",
        "user",
        "seed",
        "service_tier",
        "disallowed_field",
        "unsupported_field",
    }

    models: List[ModelInfo] = [
        ModelInfo(
            id="gemini-3.8-flash-high",
            name="Gemini 3.8 Flash High",
            context_window=1048576,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="gemini-3.1-pro-high",
            name="Gemini 3.1 Pro High",
            context_window=2097152,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="claude-sonnet-5-5-high",
            name="Claude Sonnet 5.5 High",
            context_window=200000,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="gemini-2.5-pro",
            name="Gemini 2.5 Pro",
            context_window=1048576,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="gemini-2.5-flash",
            name="Gemini 2.5 Flash",
            context_window=1048576,
            max_output_tokens=8192,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
    ]

    @staticmethod
    def generate_trajectory_id() -> str:
        return f"traj_{uuid.uuid4().hex}"

    @staticmethod
    def generate_ide_request_id() -> str:
        return f"ide_req_{uuid.uuid4().hex}"

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        headers = super().build_headers(account, stream)
        headers["x-trajectory-id"] = self.generate_trajectory_id()
        ide_req_id = self.generate_ide_request_id()
        headers["x-ide-request-id"] = ide_req_id
        headers["x-request-id"] = ide_req_id
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        if "x-trajectory-id" not in request.headers:
            request.headers["x-trajectory-id"] = self.generate_trajectory_id()
        if "x-ide-request-id" not in request.headers:
            ide_req_id = self.generate_ide_request_id()
            request.headers["x-ide-request-id"] = ide_req_id
            if "x-request-id" not in request.headers:
                request.headers["x-request-id"] = ide_req_id

        # Strip disallowed fields from request body
        if isinstance(request.body, dict):
            cleaned_body = {
                k: v for k, v in request.body.items()
                if k not in self.DISALLOWED_FIELDS
            }
            request.body = cleaned_body

        return request
