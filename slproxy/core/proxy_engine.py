"""
Proxy Engine Contract & Stub
"""

from typing import AsyncGenerator, Tuple, Optional
from slproxy.core.plugin_base import BasePlugin, Account, ProxyRequest, ProxyResponse, ErrorCheckResult


class ProxyEngine:
    """
    Executes proxy requests against upstream provider with account routing,
    fallback retries, response/stream hooks, and error detection.
    """
    def __init__(self, client_timeout: float = 120.0):
        self.client_timeout = client_timeout

    async def execute_request(
        self,
        plugin: BasePlugin,
        account: Account,
        request: ProxyRequest
    ) -> ProxyResponse:
        raise NotImplementedError

    async def execute_stream(
        self,
        plugin: BasePlugin,
        account: Account,
        request: ProxyRequest
    ) -> Tuple[int, dict, AsyncGenerator[bytes, None]]:
        raise NotImplementedError
