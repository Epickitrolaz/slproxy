"""
OpenCode Provider Plugin
========================

Educational Reference Implementation based on 9Router OpenCode Protocols.

Overview & Architectural Rationale
-----------------------------------
OpenCode CLI connects to upstream orchestrators that enforce strict session token
structures and client fingerprinting. Unlike standard UUIDv4 tokens, OpenCode uses
a specialized 48-bit descending-time session token paired with a high-entropy base62 suffix.

1. The 48-bit Descending Time Algorithm:
   `descending_time_hex = (~(int(time_ms) * 0x1000 + counter) & 0xFFFFFFFFFFFF).to_bytes(6, 'big').hex()`
   Paired with a 14-character base62 suffix:
   `ses_<descending_time_hex><random14>`

2. Why Upstream Validates the Timestamp:
   The first 36 bits of the 48-bit inverted integer encode the millisecond epoch timestamp.
   Upstream reconstructs the timestamp by performing bitwise inversion:
     recovered_time_ms = ((~token_int & 0xFFFFFFFFFFFF) >> 12)
   Upstream rejects sessions whose recovered timestamp deviates significantly from the current
   server epoch (e.g. older than 5 minutes or in the future), preventing replay attacks,
   token harvesting, and stale session reuse.

3. Why Upstream Rejects Non-Small Counters:
   The lowest 12 bits (`counter`, range 0..4095) provide intra-millisecond serialization.
   Authentic OpenCode CLI clients generate sessions with low sequential counters (0, 1, ...).
   High or pseudo-random counter values are flagged by upstream anomaly detection as
   automated fuzzing, script manipulation, or synthetic bot traffic.

4. Why Upstream Rejects Older User-Agents:
   Upstream enforces strict User-Agent verification (`opencode/latest/2.0.26/cli`). Older User-Agents
   or generic HTTP libraries (e.g., Python requests, curl) are immediately dropped with HTTP 403
   or HTTP 426 Upgrade Required because newer gateway routing infrastructure relies on the
   session format and telemetry schema introduced in CLI release 2.0.26.
"""

import secrets
import time
from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


# Standard Base62 alphabet for URL-safe token suffixes
BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class OpenCodePlugin(BasePlugin):
    """
    OpenCode CLI Provider Plugin implementing exact 9Router descending-time session generation.
    """

    id: str = "opencode"
    name: str = "OpenCode"
    description: str = "OpenCode CLI provider with 9Router 48-bit descending-time session tokens and client fingerprinting"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "terminal"
    color: str = "#10B981"
    default_base_url: str = "https://api.opencode.ai/v1"
    format: str = "openai"

    # Strict User-Agent required by OpenCode 2.0.26+ gateways
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

    @classmethod
    def generate_random_base62(cls, length: int = 14) -> str:
        """
        Generates a cryptographically secure random base62 string of the specified length.
        """
        return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))

    @classmethod
    def generate_descending_time_hex(cls, time_ms: Optional[int] = None, counter: int = 0) -> str:
        """
        Computes the 48-bit inverted descending-time hex string according to 9Router spec:
          descending_time_hex = (~(int(time_ms) * 0x1000 + counter) & 0xFFFFFFFFFFFF).to_bytes(6, 'big').hex()

        Step-by-step:
        1. time_ms: Millisecond UNIX epoch integer.
        2. Shifted left by 12 bits (multiplied by 0x1000) to embed the 12-bit sequence counter.
        3. Bitwise NOT (~) inverts the integer so newer timestamps produce numerically smaller values.
        4. Masked with 0xFFFFFFFFFFFF (48 bits / 6 bytes).
        5. Converted to 6 big-endian bytes and formatted as a 12-character hex string.
        """
        if time_ms is None:
            time_ms = int(time.time() * 1000)

        # Counter is clamped to 12 bits (0..4095)
        safe_counter = counter & 0x0FFF
        packed = (int(time_ms) * 0x1000 + safe_counter)
        inverted = (~packed) & 0xFFFFFFFFFFFF
        return inverted.to_bytes(6, "big").hex()

    @classmethod
    def generate_session_id(cls, time_ms: Optional[int] = None, counter: int = 0) -> str:
        """
        Generates a fully valid OpenCode session token:
          ses_<descending_time_hex><random14>

        Example:
          ses_f1a2b3c4d5e6A9b8C7d6E5f4G3
        """
        descending_hex = cls.generate_descending_time_hex(time_ms=time_ms, counter=counter)
        suffix = cls.generate_random_base62(14)
        return f"ses_{descending_hex}{suffix}"

    def build_headers(self, account: Account, stream: bool = True) -> Dict[str, str]:
        """
        Builds OpenCode headers injecting:
        - User-Agent: opencode/latest/2.0.26/cli
        - x-opencode-session: ses_<descending_time_hex><random14>
        """
        headers = super().build_headers(account, stream)
        headers["User-Agent"] = self.USER_AGENT
        session_id = account.extra_config.get("session_id") or self.generate_session_id()
        headers["x-opencode-session"] = session_id
        return headers

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Enforces OpenCode client fingerprinting headers on outgoing requests:
        1. Overrides or ensures User-Agent is opencode/latest/2.0.26/cli.
        2. Injects x-opencode-session if missing using the 48-bit descending-time format.
        """
        request.headers["User-Agent"] = self.USER_AGENT
        if "x-opencode-session" not in request.headers:
            session_id = account.extra_config.get("session_id") or self.generate_session_id()
            request.headers["x-opencode-session"] = session_id
        return request
