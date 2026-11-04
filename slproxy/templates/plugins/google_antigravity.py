"""
Google Antigravity Provider Plugin
==================================

Educational Reference Implementation based on 9Router IDE protocols.

Overview
--------
The Google Antigravity provider acts as an IDE proxy bridge to Google's specialized
Gemini/Antigravity endpoints. Upstream endpoints strictly validate internal client telemetry,
trajectory step hierarchies, and reject typical consumer/OpenAI hyperparameter fields
(such as thinkingConfig, reasoning_effort, frequency_penalty).

Key Features:
1. 9Router IDE Trajectory Algorithm:
   Generates structured hierarchical trajectory paths:
     agent/<conversation_id>/<timestamp>/<trajectory_id>/<step>
   where conversation_id and trajectory_id are generated using deterministic SHA-256
   derived UUIDs seeded from session/model/client metadata.
2. Complete Field Sanitization:
   Strips all Google-rejected parameters (e.g. output_config, thinking, reasoning_effort,
   reasoning, enable_thinking, thinking_budget, thinkingConfig, presence_penalty, etc.).
3. Official Antigravity IDE Telemetry Headers:
   User-Agent: Antigravity-IDE/1.0
   Authorization: Bearer <token>
   x-goog-api-client: ide/antigravity
   x-trajectory-id: agent/...
   x-ide-request-id: ide_req_...
"""

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class GoogleAntigravityPlugin(BasePlugin):
    """
    Google Antigravity Provider Plugin with verbose 9Router reference algorithms.
    """

    id: str = "google_antigravity"
    name: str = "Google Antigravity"
    description: str = "Google Antigravity provider with 9Router IDE trajectory/session ID algorithms and complete field stripping"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "google"
    color: str = "#4285F4"
    default_base_url: str = "https://antigravity.google"
    format: str = "antigravity"

    # Exact list of parameters strictly rejected by Google Gemini/Antigravity APIs.
    # Passing any of these causes HTTP 400 'INVALID_ARGUMENT' or schema validation failures.
    REJECTED_GOOGLE_FIELDS: Set[str] = {
        # Google-rejected thinking/reasoning parameters
        "output_config",
        "thinking",
        "reasoning_effort",
        "reasoning",
        "enable_thinking",
        "thinking_budget",
        "thinkingConfig",
        # OpenAI-specific hyperparameters unsupported by Google
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
    # Backward-compatible alias
    DISALLOWED_FIELDS: Set[str] = REJECTED_GOOGLE_FIELDS

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

    @classmethod
    def generate_sha256_uuid(cls, seed: str) -> str:
        """
        Derives an RFC 4122 compliant UUID string deterministically from a SHA-256 digest.

        Educational Explanation:
        ------------------------
        In 9Router and Google IDE internals, conversations and trajectories must have stable,
        valid UUIDv4-like string structures. Rather than emitting truly random tokens that cannot
        be correlated across request re-tries or multi-step tool loops, 9Router computes a SHA-256
        hash of the session/model/client seed and maps the first 16 bytes into a standard UUID string.
        """
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        # Create standard UUID representation from the first 16 bytes
        return str(uuid.UUID(bytes=digest[:16]))

    @classmethod
    def generate_trajectory_id(
        cls,
        conversation_seed: Optional[str] = None,
        trajectory_seed: Optional[str] = None,
        step: int = 1,
        timestamp_ms: Optional[int] = None,
    ) -> str:
        """
        Implements the exact 9Router IDE trajectory ID algorithm:
          agent/<conversation_id>/<timestamp>/<trajectory_id>/<step>

        Components:
        -----------
        1. 'agent': Fixed prefix indicating an autonomous IDE agent trajectory context.
        2. conversation_id: A UUID derived from SHA-256 hash of session/client seed.
        3. timestamp: Millisecond UNIX epoch integer representing trajectory start.
        4. trajectory_id: A UUID derived from SHA-256 hash of trajectory/model seed.
        5. step: Positive integer indicating the sequence step within the agent trajectory.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        # Build seeds if not explicitly provided
        conv_seed = conversation_seed or f"session_{uuid.uuid4().hex}_{timestamp_ms}"
        traj_seed = trajectory_seed or f"traj_{uuid.uuid4().hex}_{step}"

        conversation_id = cls.generate_sha256_uuid(conv_seed)
        trajectory_id = cls.generate_sha256_uuid(traj_seed)

        return f"agent/{conversation_id}/{timestamp_ms}/{trajectory_id}/{step}"

    @classmethod
    def generate_ide_request_id(cls, seed: Optional[str] = None) -> str:
        """
        Generates the IDE request ID header required by Antigravity endpoints.
        Prefixed with 'ide_req_' and suffixed with a SHA-256 derived UUID hex.
        """
        req_seed = seed or f"req_{uuid.uuid4().hex}_{time.time()}"
        return f"ide_req_{cls.generate_sha256_uuid(req_seed).replace('-', '')}"

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        """
        Constructs complete HTTP headers required for Google Antigravity endpoints.

        Headers injected:
        - User-Agent: Antigravity-IDE/1.0
        - Authorization: Bearer <token>
        - x-goog-api-client: ide/antigravity
        - x-trajectory-id: agent/<conversation_id>/<timestamp>/<trajectory_id>/<step>
        - x-ide-request-id: ide_req_<sha256_hex>
        - x-request-id: matching x-ide-request-id
        """
        headers = super().build_headers(account, stream)

        # 1. Antigravity IDE identification
        headers["User-Agent"] = "Antigravity-IDE/1.0"
        headers["x-goog-api-client"] = "ide/antigravity"

        # 2. Authorization Bearer token
        if account.api_key:
            headers["Authorization"] = f"Bearer {account.api_key}"

        # 3. 9Router Trajectory and Request tracking IDs
        conv_seed = account.extra_config.get("session_id") or account.id
        traj_seed = account.extra_config.get("trajectory_seed") or f"traj_{account.id}_{time.time()}"
        step = int(account.extra_config.get("step", 1))

        trajectory_id = self.generate_trajectory_id(
            conversation_seed=conv_seed,
            trajectory_seed=traj_seed,
            step=step,
        )
        ide_req_id = self.generate_ide_request_id(seed=f"{account.id}_{time.time()}")

        headers["x-trajectory-id"] = trajectory_id
        headers["x-ide-request-id"] = ide_req_id
        headers["x-request-id"] = ide_req_id

        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Transforms incoming request to comply with Google Antigravity specifications:
        1. Ensures Antigravity-IDE/1.0 User-Agent and x-goog-api-client headers are present.
        2. Ensures Authorization Bearer token is populated if absent.
        3. Generates missing x-trajectory-id in 9Router format and x-ide-request-id.
        4. Strips all Google-rejected parameters from request body.
        """
        # Step 1: Ensure required headers
        if "User-Agent" not in request.headers or request.headers["User-Agent"] == "SLProxy/1.0":
            request.headers["User-Agent"] = "Antigravity-IDE/1.0"
        if "x-goog-api-client" not in request.headers:
            request.headers["x-goog-api-client"] = "ide/antigravity"
        if "Authorization" not in request.headers and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"

        # Step 2: Inject 9Router trajectory ID if not provided
        if "x-trajectory-id" not in request.headers:
            conv_seed = account.extra_config.get("session_id") or account.id
            traj_seed = account.extra_config.get("trajectory_seed") or request.model
            step = int(account.extra_config.get("step", 1))
            request.headers["x-trajectory-id"] = self.generate_trajectory_id(
                conversation_seed=conv_seed,
                trajectory_seed=traj_seed,
                step=step,
            )

        # Step 3: Inject IDE request ID
        if "x-ide-request-id" not in request.headers:
            ide_req_id = self.generate_ide_request_id()
            request.headers["x-ide-request-id"] = ide_req_id
            if "x-request-id" not in request.headers:
                request.headers["x-request-id"] = ide_req_id

        # Step 4: Complete field stripping of Google-rejected parameters
        if isinstance(request.body, dict):
            cleaned_body = {
                k: v for k, v in request.body.items()
                if k not in self.REJECTED_GOOGLE_FIELDS
            }
            request.body = cleaned_body

        return request
