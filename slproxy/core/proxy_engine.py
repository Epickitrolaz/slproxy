"""
Proxy Engine for SLProxy
"""

import inspect
from typing import Any, AsyncGenerator, Dict, Optional, Tuple
import httpx

from slproxy.core.plugin_base import Account, BasePlugin, ErrorCheckResult, ProxyRequest, ProxyResponse


class ProxyEngine:
    """
    Executes proxy requests against upstream provider with account routing,
    fallback retries, response/stream hooks, and error detection.
    """

    def __init__(
        self,
        client_timeout: float = 120.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.client_timeout = client_timeout
        self._custom_client = client
        if client is not None:
            self._client = client
        else:
            limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
            timeout = httpx.Timeout(self.client_timeout)
            self._client = httpx.AsyncClient(limits=limits, timeout=timeout)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=50, max_connections=200)
            timeout = httpx.Timeout(self.client_timeout)
            self._client = httpx.AsyncClient(limits=limits, timeout=timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def execute_request(
        self,
        plugin: BasePlugin,
        account: Account,
        request: ProxyRequest,
    ) -> ProxyResponse:
        """
        Executes a non-streaming request against upstream:
        - Calls plugin.transform_request(request, account)
        - Sends HTTP request upstream
        - Calls plugin.detect_error_or_limit(...)
        - Calls plugin.transform_response(...)
        - Returns ProxyResponse
        """
        # 1. Transform request hook
        req = plugin.transform_request(request, account)
        if inspect.iscoroutine(req):
            req = await req

        # 2. Build upstream request kwargs
        # Filter out hop-by-hop / recomputed headers like content-length and host
        upstream_headers = {
            k: v for k, v in req.headers.items()
            if k.lower() not in ("content-length", "host")
        }

        kwargs: Dict[str, Any] = {
            "method": req.method,
            "url": req.url,
            "headers": upstream_headers,
            "timeout": self.client_timeout,
        }
        if isinstance(req.body, (dict, list)):
            kwargs["json"] = req.body
        elif isinstance(req.body, str):
            kwargs["content"] = req.body.encode("utf-8")
        elif isinstance(req.body, bytes):
            kwargs["content"] = req.body
        elif req.body is not None:
            kwargs["json"] = req.body

        # 3. Send HTTP request upstream
        resp = await self.client.request(**kwargs)
        status_code = resp.status_code
        resp_headers = dict(resp.headers)
        raw_text = resp.text

        body = None
        try:
            body = resp.json()
        except Exception:
            body = raw_text

        # 4. Error / limit detection hook
        error_check = plugin.detect_error_or_limit(status_code, raw_text, resp_headers)
        if inspect.iscoroutine(error_check):
            error_check = await error_check

        metadata = dict(req.metadata)
        metadata["error_check"] = error_check

        proxy_resp = ProxyResponse(
            status_code=status_code,
            headers=resp_headers,
            body=body,
            raw_text=raw_text,
            metadata=metadata,
        )

        # 5. Transform response hook
        final_resp = plugin.transform_response(proxy_resp, account)
        if inspect.iscoroutine(final_resp):
            final_resp = await final_resp

        return final_resp

    async def execute_stream(
        self,
        plugin: BasePlugin,
        account: Account,
        request: ProxyRequest,
    ) -> Tuple[int, dict, AsyncGenerator[bytes, None]]:
        """
        Executes a streaming SSE request against upstream:
        - Calls plugin.transform_request(request, account)
        - Sends HTTP request upstream with stream=True
        - Forwards SSE chunks transformed via plugin.transform_stream_chunk(chunk, account)
        - Returns (status_code, headers, stream_generator)
        """
        # 1. Transform request hook
        req = plugin.transform_request(request, account)
        if inspect.iscoroutine(req):
            req = await req

        # 2. Build upstream request kwargs
        # Filter out hop-by-hop / recomputed headers like content-length and host
        upstream_headers = {
            k: v for k, v in req.headers.items()
            if k.lower() not in ("content-length", "host")
        }

        kwargs: Dict[str, Any] = {
            "method": req.method,
            "url": req.url,
            "headers": upstream_headers,
            "timeout": self.client_timeout,
        }
        if isinstance(req.body, (dict, list)):
            kwargs["json"] = req.body
        elif isinstance(req.body, str):
            kwargs["content"] = req.body.encode("utf-8")
        elif isinstance(req.body, bytes):
            kwargs["content"] = req.body
        elif req.body is not None:
            kwargs["json"] = req.body

        # 3. Send upstream with streaming enabled
        upstream_req = self.client.build_request(**kwargs)
        upstream_resp = await self.client.send(upstream_req, stream=True)
        status_code = upstream_resp.status_code
        resp_headers = dict(upstream_resp.headers)

        if status_code >= 400:
            err_check = plugin.detect_error_or_limit(status_code, "", resp_headers)
            if inspect.iscoroutine(err_check):
                await err_check

        # 4. Stream generator yielding transformed chunks
        async def stream_generator() -> AsyncGenerator[bytes, None]:
            try:
                async for raw_chunk in upstream_resp.aiter_bytes():
                    if not raw_chunk:
                        continue
                    chunk = plugin.transform_stream_chunk(raw_chunk, account)
                    if inspect.iscoroutine(chunk):
                        chunk = await chunk
                    if chunk is not None:
                        if isinstance(chunk, str):
                            chunk = chunk.encode("utf-8")
                        if len(chunk) > 0:
                            yield chunk

                final_chunk = plugin.finalize_stream(account, req.metadata)
                if inspect.iscoroutine(final_chunk):
                    final_chunk = await final_chunk
                if final_chunk:
                    if isinstance(final_chunk, str):
                        final_chunk = final_chunk.encode("utf-8")
                    yield final_chunk
            finally:
                await upstream_resp.aclose()

        return status_code, resp_headers, stream_generator()
