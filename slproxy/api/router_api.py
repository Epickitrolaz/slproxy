"""
Router API (/routerapi)
Implements:
- GET /routerapi/health
- GET /routerapi/v1/models
- POST /routerapi/v1/chat/completions (OpenAI compatible, streaming & non-streaming, fallback retries)
- POST /routerapi/v1/messages (Anthropic compatible, streaming & non-streaming)
- POST /routerapi/v1/embeddings
"""

import inspect
import asyncio
import json
import random
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from slproxy.config import DEFAULT_ROUTING_STRATEGY, REQUEST_TIMEOUT, REQUIRE_API_KEY
from slproxy.core.account_router import AccountRouter
from slproxy.core.key_authenticator import ApiKey, KeyAuthenticator
from slproxy.core.metrics import MetricsManager, RequestLog
from slproxy.core.plugin_base import Account, BasePlugin, ErrorCheckResult, ModelInfo, ProxyRequest, ProxyResponse
from slproxy.core.plugin_manager import PluginManager
from slproxy.core.proxy_engine import ProxyEngine
from slproxy.db.database import Database

router = APIRouter()


# -----------------------------------------------------------------------------
# Auth Dependency
# -----------------------------------------------------------------------------

async def get_current_api_key(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
) -> Optional[ApiKey]:
    db: Optional[Database] = getattr(request.app.state, "db", None)
    key_auth: Optional[KeyAuthenticator] = getattr(request.app.state, "key_authenticator", None)

    is_required = REQUIRE_API_KEY
    if not is_required and db:
        try:
            async with db.conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1") as cursor:
                row = await cursor.fetchone()
                if row and row[0] > 0:
                    is_required = True
        except Exception:
            pass

    raw_token = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            raw_token = authorization[7:].strip()
        else:
            raw_token = authorization.strip()
    elif x_api_key:
        raw_token = x_api_key.strip()

    if not is_required and not raw_token:
        return None

    if is_required and not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"message": "API key required", "type": "auth_error", "code": 401}},
        )

    api_key_obj: Optional[ApiKey] = None
    if key_auth:
        try:
            auth_header = authorization or (f"Bearer {raw_token}" if raw_token else "")
            api_key_obj = await key_auth.authenticate(auth_header)
        except NotImplementedError:
            api_key_obj = None
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"message": f"Authentication failed: {str(e)}", "type": "auth_error", "code": 401}},
            )

    if api_key_obj is None and db:
        async with db.conn.execute(
            "SELECT * FROM api_keys WHERE key = ? AND is_active = 1",
            (raw_token,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": {"message": "Invalid API key", "type": "auth_error", "code": 401}},
                )

            expires_at = row["expires_at"]
            if expires_at and expires_at < time.time():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": {"message": "API key has expired", "type": "auth_error", "code": 401}},
                )

            max_requests = row["max_requests"]
            used_requests = row["used_requests"] or 0
            if max_requests is not None and used_requests >= max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"error": {"message": "API key request limit reached", "type": "rate_limit_error", "code": 429}},
                )

            max_tokens = row["max_tokens"]
            used_tokens = row["used_tokens"] or 0
            if max_tokens is not None and used_tokens >= max_tokens:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"error": {"message": "API key token limit reached", "type": "rate_limit_error", "code": 429}},
                )

            allowed_plugins = json.loads(row["allowed_plugins"] or "[]")
            allowed_models = json.loads(row["allowed_models"] or "[]")
            extra_metadata = json.loads(row["extra_metadata"] or "{}")

            api_key_obj = ApiKey(
                id=row["id"],
                key=row["key"],
                name=row["name"],
                created_at=row["created_at"],
                expires_at=row["expires_at"],
                max_requests=row["max_requests"],
                max_tokens=row["max_tokens"],
                used_requests=row["used_requests"],
                used_tokens=row["used_tokens"],
                is_active=bool(row["is_active"]),
                allowed_plugins=allowed_plugins,
                allowed_models=allowed_models,
                extra_metadata=extra_metadata,
            )

    if api_key_obj is None and is_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"message": "Invalid API key", "type": "auth_error", "code": 401}},
        )

    return api_key_obj


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def resolve_plugin_and_model(
    plugin_manager: Optional[PluginManager],
    requested_model: str,
    accounts: Optional[List[Account]] = None,
) -> Tuple[Optional[BasePlugin], str]:
    if not plugin_manager:
        return None, requested_model

    enabled_plugins = [
        p for p in plugin_manager.list_plugins()
        if getattr(p, "enabled", True)
    ]
    if not enabled_plugins:
        return None, requested_model

    # 1. Prefix match: e.g. "antigravity/gemini-3.8-flash"
    if "/" in requested_model:
        prefix, _, stripped = requested_model.partition("/")
        for p in enabled_plugins:
            if p.id.lower() == prefix.lower():
                return p, stripped

    # 2. Exact match in plugin models
    for p in enabled_plugins:
        models = p.fetch_models() if hasattr(p, "fetch_models") else (p.models or [])
        for m in models:
            m_id = m.id if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else str(m))
            if m_id == requested_model:
                return p, requested_model

    # 3. Check account-level model overrides if accounts provided
    if accounts:
        for p in enabled_plugins:
            p_accounts = [a for a in accounts if a.provider_id == p.id]
            for acc in p_accounts:
                try:
                    acc_models = p.fetch_models(acc) if hasattr(p, "fetch_models") else []
                except Exception:
                    acc_models = []
                for m in acc_models:
                    m_id = m.id if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else str(m))
                    if m_id == requested_model:
                        return p, requested_model

    # 4. Model starts with plugin id prefix e.g. "anthropic-claude-..."
    for p in enabled_plugins:
        if requested_model.lower().startswith(p.id.lower() + "-"):
            return p, requested_model

    # 5. Fallback to default plugin if named "default"
    for p in enabled_plugins:
        if p.id.lower() == "default":
            return p, requested_model

    # 6. First enabled plugin
    return enabled_plugins[0], requested_model


def filter_accounts_for_model(
    plugin: BasePlugin,
    accounts: List[Account],
    requested_model: str,
) -> List[Account]:
    """
    Filters accounts respecting account-level model overrides via plugin.fetch_models(account).
    If an account specifies a custom models list, it only qualifies if the requested model
    is in plugin.fetch_models(account). Exact matching accounts are prioritized over general accounts.
    """
    exact_match = []
    default_accounts = []
    for acc in accounts:
        try:
            acc_models = plugin.fetch_models(acc) if hasattr(plugin, "fetch_models") else plugin.models
        except Exception:
            acc_models = plugin.models
        model_ids = {
            m.id if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else str(m))
            for m in (acc_models or [])
        }
        if requested_model in model_ids:
            exact_match.append(acc)
        elif not (acc.extra_config and "models" in acc.extra_config):
            default_accounts.append(acc)

    if exact_match:
        return exact_match
    if default_accounts:
        return default_accounts
    return accounts


async def sync_plugin_models_from_db(db: Optional[Database], pm: Optional[PluginManager]):
    """
    Synchronizes persisted plugin models from SQLite plugin_settings into the in-memory PluginManager.
    """
    if not db or not pm:
        return
    try:
        async with db.conn.execute("SELECT plugin_id, models, variables FROM plugin_settings") as cur:
            for row in await cur.fetchall():
                p_id = row["plugin_id"]
                if p_id in pm.plugins:
                    try:
                        if row["models"] is not None:
                            persisted = [ModelInfo(**item) for item in json.loads(row["models"])]
                            pm.plugins[p_id].models = persisted
                    except Exception:
                        pass
                    try:
                        pm.plugins[p_id].set_settings(json.loads(row["variables"] or "{}"))
                    except Exception:
                        pass
    except Exception:
        pass


async def get_all_active_accounts(db: Optional[Database]) -> List[Account]:
    if not db:
        return []
    accounts: List[Account] = []
    try:
        async with db.conn.execute("SELECT * FROM accounts WHERE is_active = 1 ORDER BY priority ASC, id ASC") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                extra_headers = json.loads(r["extra_headers"]) if r["extra_headers"] else {}
                extra_config = json.loads(r["extra_config"]) if r["extra_config"] else {}
                accounts.append(
                    Account(
                        id=r["id"],
                        provider_id=r["provider_id"],
                        name=r["name"],
                        api_key=r["api_key"] or "",
                        base_url=r["base_url"],
                        extra_headers=extra_headers,
                        extra_config=extra_config,
                        priority=r["priority"] or 1,
                        weight=r["weight"] or 1,
                        is_active=bool(r["is_active"]),
                        rate_limited_until=r["rate_limited_until"],
                        error_count=r["error_count"] or 0,
                        success_count=r["success_count"] or 0,
                        last_used_at=r["last_used_at"],
                    )
                )
    except Exception:
        pass
    return accounts


async def get_active_accounts_for_provider(db: Optional[Database], provider_id: str) -> List[Account]:
    if not db:
        return []
    accounts: List[Account] = []
    async with db.conn.execute(
        "SELECT * FROM accounts WHERE provider_id = ? AND is_active = 1 ORDER BY priority ASC, id ASC",
        (provider_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        for r in rows:
            extra_headers = json.loads(r["extra_headers"]) if r["extra_headers"] else {}
            extra_config = json.loads(r["extra_config"]) if r["extra_config"] else {}
            accounts.append(
                Account(
                    id=r["id"],
                    provider_id=r["provider_id"],
                    name=r["name"],
                    api_key=r["api_key"] or "",
                    base_url=r["base_url"],
                    extra_headers=extra_headers,
                    extra_config=extra_config,
                    priority=r["priority"] or 1,
                    weight=r["weight"] or 1,
                    is_active=bool(r["is_active"]),
                    rate_limited_until=r["rate_limited_until"],
                    error_count=r["error_count"] or 0,
                    success_count=r["success_count"] or 0,
                    last_used_at=r["last_used_at"],
                )
            )
    return accounts


def select_account(
    account_router: Optional[AccountRouter],
    candidates: List[Account],
    strategy: str = DEFAULT_ROUTING_STRATEGY,
) -> Optional[Account]:
    if account_router:
        try:
            return account_router.select_account(candidates, strategy=strategy)
        except NotImplementedError:
            pass
    now = time.time()
    available = [a for a in candidates if a.is_available(now)]
    return available[0] if available else None


async def mark_account_success(
    account_router: Optional[AccountRouter],
    db: Optional[Database],
    account: Account,
):
    router_handled = False
    if account_router:
        try:
            account_router.mark_success(account)
            router_handled = True
        except (NotImplementedError, Exception):
            router_handled = False
    if not router_handled:
        account.success_count += 1
        account.last_used_at = time.time()
    if db:
        try:
            now = account.last_used_at or time.time()
            await db.conn.execute(
                "UPDATE accounts SET success_count = success_count + 1, last_used_at = ? WHERE id = ?",
                (now, account.id),
            )
            await db.conn.commit()
        except Exception:
            pass


async def mark_account_error_or_limit(
    account_router: Optional[AccountRouter],
    db: Optional[Database],
    account: Account,
    err_check: ErrorCheckResult,
):
    now = time.time()
    router_handled = False
    if err_check.is_rate_limited:
        cooldown = err_check.cooldown_seconds or 60.0
        account.rate_limited_until = now + cooldown
        if account_router:
            try:
                account_router.mark_rate_limited(account, cooldown_seconds=cooldown)
                router_handled = True
            except (NotImplementedError, Exception):
                router_handled = False
        if not router_handled:
            account.error_count += 1
        if db:
            try:
                await db.conn.execute(
                    "UPDATE accounts SET rate_limited_until = ?, error_count = error_count + 1 WHERE id = ?",
                    (account.rate_limited_until, account.id),
                )
                await db.conn.commit()
            except Exception:
                pass
    else:
        if account_router:
            try:
                account_router.mark_error(account, err_check.error_message)
                router_handled = True
            except (NotImplementedError, Exception):
                router_handled = False
        if not router_handled:
            account.error_count += 1
        if db:
            try:
                await db.conn.execute(
                    "UPDATE accounts SET error_count = error_count + 1 WHERE id = ?",
                    (account.id,),
                )
                await db.conn.commit()
            except Exception:
                pass


async def record_usage_and_telemetry(
    request: Request,
    api_key: Optional[ApiKey],
    endpoint: str,
    model: str,
    provider_id: str,
    account_id: str,
    status_code: int,
    start_time: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    is_stream: bool = False,
    error: Optional[str] = None,
):
    db: Optional[Database] = getattr(request.app.state, "db", None)
    metrics: Optional[MetricsManager] = getattr(request.app.state, "metrics_manager", None)
    key_auth: Optional[KeyAuthenticator] = getattr(request.app.state, "key_authenticator", None)

    latency_ms = (time.time() - start_time) * 1000.0
    total_tokens = prompt_tokens + completion_tokens
    client_ip = request.client.host if request.client else ""

    log = RequestLog(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        client_ip=client_ip,
        api_key_id=api_key.id if api_key else None,
        endpoint=endpoint,
        model=model,
        provider_id=provider_id,
        account_id=account_id,
        status_code=status_code,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        is_stream=is_stream,
        error=error,
    )

    if metrics:
        try:
            metrics.record_request(log)
        except Exception:
            pass

    if db:
        try:
            await db.conn.execute(
                """INSERT INTO request_logs 
                (id, timestamp, client_ip, api_key_id, endpoint, model, provider_id, account_id, status_code, latency_ms, prompt_tokens, completion_tokens, total_tokens, is_stream, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    log.id,
                    log.timestamp,
                    log.client_ip,
                    log.api_key_id,
                    log.endpoint,
                    log.model,
                    log.provider_id,
                    log.account_id,
                    log.status_code,
                    log.latency_ms,
                    log.prompt_tokens,
                    log.completion_tokens,
                    log.total_tokens,
                    1 if is_stream else 0,
                    log.error,
                ),
            )
            await db.conn.commit()
        except Exception:
            pass

    if api_key:
        recorded = False
        if key_auth:
            try:
                await key_auth.record_usage(api_key.id, requests_inc=1, tokens_inc=total_tokens)
                recorded = True
            except (NotImplementedError, Exception):
                recorded = False
        if not recorded and db:
            try:
                await db.conn.execute(
                    "UPDATE api_keys SET used_requests = used_requests + 1, used_tokens = used_tokens + ? WHERE id = ?",
                    (total_tokens, api_key.id),
                )
                await db.conn.commit()
            except Exception:
                pass


async def execute_proxy_request(
    proxy_engine: Optional[ProxyEngine],
    plugin: BasePlugin,
    account: Account,
    proxy_req: ProxyRequest,
) -> ProxyResponse:
    if proxy_engine:
        try:
            return await proxy_engine.execute_request(plugin, account, proxy_req)
        except NotImplementedError:
            pass

    # Fallback HTTP execution
    headers = proxy_req.headers or plugin.build_headers(account, stream=False)
    body = proxy_req.body
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if isinstance(body, dict):
            r = await client.request(
                method=proxy_req.method,
                url=proxy_req.url,
                headers=headers,
                json=body,
            )
        else:
            r = await client.request(
                method=proxy_req.method,
                url=proxy_req.url,
                headers=headers,
                content=body if isinstance(body, bytes) else str(body).encode("utf-8"),
            )
        try:
            body_json = r.json()
        except Exception:
            body_json = None
        resp = ProxyResponse(
            status_code=r.status_code,
            headers=dict(r.headers),
            body=body_json,
            raw_text=r.text,
        )
        return plugin.transform_response(resp, account)


async def execute_proxy_stream(
    proxy_engine: Optional[ProxyEngine],
    plugin: BasePlugin,
    account: Account,
    proxy_req: ProxyRequest,
) -> Tuple[int, Dict[str, str], AsyncGenerator[bytes, None]]:
    if proxy_engine:
        try:
            return await proxy_engine.execute_stream(plugin, account, proxy_req)
        except NotImplementedError:
            pass

    # Fallback streaming execution
    headers = proxy_req.headers or plugin.build_headers(account, stream=True)
    body = proxy_req.body
    client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    req = client.build_request(
        method=proxy_req.method,
        url=proxy_req.url,
        headers=headers,
        json=body if isinstance(body, dict) else None,
        content=body if isinstance(body, (bytes, str)) else None,
    )
    upstream_resp = await client.send(req, stream=True)
    status_code = upstream_resp.status_code
    resp_headers = dict(upstream_resp.headers)

    async def stream_generator():
        try:
            async for chunk in upstream_resp.aiter_bytes():
                yield plugin.transform_stream_chunk(chunk, account)
            final_chunk = plugin.finalize_stream(account, proxy_req.metadata)
            if inspect.iscoroutine(final_chunk):
                final_chunk = await final_chunk
            if final_chunk:
                if isinstance(final_chunk, str):
                    final_chunk = final_chunk.encode("utf-8")
                yield final_chunk
        finally:
            await upstream_resp.aclose()
            await client.aclose()

    return status_code, resp_headers, stream_generator()


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("/health")
async def health_check():
    """
    Returns 200 {"status": "ok", "service": "SLProxy", "version": "1.0.0"}
    """
    return {"status": "ok", "service": "SLProxy", "version": "1.0.0"}


@router.get("/v1/models")
async def list_models(
    request: Request,
    api_key: Optional[ApiKey] = Depends(get_current_api_key),
):
    """
    Aggregates all models from all enabled plugins in OpenAI format.
    Supports account-level model overrides via plugin.fetch_models(account).
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)
    models_data: List[Dict[str, Any]] = []
    seen_ids = set()

    if pm:
        await sync_plugin_models_from_db(db, pm)
        for plugin in pm.list_plugins():
            if not getattr(plugin, "enabled", True):
                continue
            if api_key and api_key.allowed_plugins and plugin.id not in api_key.allowed_plugins:
                continue

            plugin_models = list(plugin.fetch_models() if hasattr(plugin, "fetch_models") else plugin.models)

            # Support account-level model overrides
            accounts = await get_active_accounts_for_provider(db, plugin.id)
            for acc in accounts:
                if hasattr(plugin, "fetch_models"):
                    acc_models = plugin.fetch_models(acc)
                    for am in acc_models:
                        am_id = am.id if hasattr(am, "id") else (am.get("id") if isinstance(am, dict) else str(am))
                        if not any((m.id if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else str(m))) == am_id for m in plugin_models):
                            plugin_models.append(am)

            for m in plugin_models:
                m_id = m.id if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else str(m))
                if api_key and api_key.allowed_models and m_id not in api_key.allowed_models:
                    continue

                if m_id not in seen_ids:
                    seen_ids.add(m_id)
                    models_data.append({
                        "id": m_id,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": plugin.id,
                        "permission": [],
                        "root": m_id,
                        "parent": None,
                    })
                # Also include prefixed form if not already prefixed
                if "/" not in m_id:
                    prefixed = f"{plugin.id}/{m_id}"
                    if prefixed not in seen_ids:
                        seen_ids.add(prefixed)
                        models_data.append({
                            "id": prefixed,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": plugin.id,
                            "permission": [],
                            "root": m_id,
                            "parent": None,
                        })

    return {"object": "list", "data": models_data}


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key: Optional[ApiKey] = Depends(get_current_api_key),
):
    """
    OpenAI-compatible chat completions endpoint with transparent account fallback.
    """
    start_time = time.time()
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    requested_model = body.get("model", "")
    if not requested_model:
        raise HTTPException(status_code=400, detail="Model parameter is required")

    is_stream = bool(body.get("stream", False))

    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)
    account_router: Optional[AccountRouter] = getattr(request.app.state, "account_router", None)
    proxy_engine: Optional[ProxyEngine] = getattr(request.app.state, "proxy_engine", None)

    # 1. Resolve plugin and upstream model name (checking account overrides)
    await sync_plugin_models_from_db(db, pm)
    all_accounts = await get_all_active_accounts(db)
    plugin, upstream_model = resolve_plugin_and_model(pm, requested_model, accounts=all_accounts)
    if not plugin:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={"error": {"message": "No enabled provider plugin available", "type": "service_unavailable", "code": 503}},
        )

    # Validate key permissions if key exists
    if api_key:
        if api_key.allowed_plugins and plugin.id not in api_key.allowed_plugins:
            raise HTTPException(status_code=403, detail="Plugin not allowed for this API key")
        if api_key.allowed_models and requested_model not in api_key.allowed_models:
            raise HTTPException(status_code=403, detail="Model not allowed for this API key")

    # 2. Fetch active accounts for the provider
    accounts = await get_active_accounts_for_provider(db, plugin.id)
    if not accounts:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={"error": {"message": f"No active accounts configured for provider '{plugin.id}'", "type": "service_unavailable", "code": 503}},
        )

    # Filter candidate accounts respecting account-level model overrides
    candidate_accounts = filter_accounts_for_model(plugin, accounts, upstream_model)

    # Prepare payload with upstream model
    upstream_body = dict(body)
    upstream_body["model"] = upstream_model

    # 3. Transparent account retry loop
    last_error_resp: Optional[Response] = None
    account_switch_count = 0

    while candidate_accounts:
        # Antigravity: avoid instantaneous account switches/retries by waiting a
        # randomized amount of time before moving to another Google account.
        if account_switch_count > 0 and plugin.id == "google_antigravity":
            delay_method = getattr(plugin, "get_account_switch_delay", None)
            delay = float(delay_method()) if callable(delay_method) else 0.0
            if delay > 0:
                await asyncio.sleep(delay)

        selected_account = select_account(account_router, candidate_accounts)
        if not selected_account:
            # All available accounts exhausted or rate limited
            break

        base_url = plugin.get_base_url(selected_account)
        req_url = f"{base_url}/chat/completions"
        if base_url.endswith("/chat/completions"):
            req_url = base_url

        headers = plugin.build_headers(selected_account, stream=is_stream)
        proxy_req = ProxyRequest(
            method="POST",
            url=req_url,
            headers=headers,
            body=upstream_body,
            is_stream=is_stream,
            model=upstream_model,
            client_format="openai",
        )
        proxy_req = plugin.configure_request(proxy_req)
        proxy_req = plugin.transform_request(proxy_req, selected_account)

        if is_stream:
            try:
                status_code, resp_headers, stream_gen = await execute_proxy_stream(
                    proxy_engine, plugin, selected_account, proxy_req
                )
            except Exception as ex:
                err_check = ErrorCheckResult(is_error=True, error_message=str(ex), should_fallback=True)
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)
                account_switch_count += 1
                candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                continue

            if status_code >= 400:
                # Upstream error on stream open - consume body to check limit
                err_chunks = []
                try:
                    async for c in stream_gen:
                        err_chunks.append(c)
                except Exception:
                    pass
                err_text = b"".join(err_chunks).decode("utf-8", errors="replace")
                err_check = plugin.detect_error_or_limit(status_code, err_text, resp_headers)
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)

                antigravity_account_restriction = (
                    plugin.id == "google_antigravity"
                    and (err_check.is_rate_limited or status_code in (401, 403))
                )
                if (
                    not antigravity_account_restriction
                    and (err_check.should_fallback or status_code == 429)
                    and len(candidate_accounts) > 1
                ):
                    account_switch_count += 1
                    candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                    continue
                else:
                    await record_usage_and_telemetry(
                        request=request,
                        api_key=api_key,
                        endpoint="/routerapi/v1/chat/completions",
                        model=requested_model,
                        provider_id=plugin.id,
                        account_id=selected_account.id,
                        status_code=status_code,
                        start_time=start_time,
                        is_stream=True,
                        error=err_check.error_message or err_text,
                    )
                    return Response(content=err_text, status_code=status_code, media_type="application/json")

            # Streaming success: Wrap generator to track telemetry
            await mark_account_success(account_router, db, selected_account)

            async def wrapped_stream():
                total_completion_tokens = 0
                prompt_tokens = 0
                try:
                    async for chunk in stream_gen:
                        # Attempt to inspect usage in chunk
                        try:
                            lines = chunk.decode("utf-8", errors="ignore").split("\n")
                            for line in lines:
                                if line.startswith("data:") and not line.endswith("[DONE]"):
                                    data = json.loads(line[5:].strip())
                                    usage = data.get("usage")
                                    if usage:
                                        prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                                        total_completion_tokens = usage.get("completion_tokens", total_completion_tokens)
                        except Exception:
                            pass
                        yield chunk
                finally:
                    await record_usage_and_telemetry(
                        request=request,
                        api_key=api_key,
                        endpoint="/routerapi/v1/chat/completions",
                        model=requested_model,
                        provider_id=plugin.id,
                        account_id=selected_account.id,
                        status_code=200,
                        start_time=start_time,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=total_completion_tokens,
                        is_stream=True,
                    )

            return StreamingResponse(
                wrapped_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        else:
            # Non-streaming
            try:
                resp = await execute_proxy_request(proxy_engine, plugin, selected_account, proxy_req)
            except Exception as ex:
                err_check = ErrorCheckResult(is_error=True, error_message=str(ex), should_fallback=True)
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)
                account_switch_count += 1
                candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                continue

            raw_text = resp.raw_text or (json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body))
            err_check = plugin.detect_error_or_limit(resp.status_code, raw_text, resp.headers)

            if err_check.is_error or err_check.is_rate_limited or resp.status_code >= 400:
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)
                antigravity_account_restriction = (
                    plugin.id == "google_antigravity"
                    and (err_check.is_rate_limited or resp.status_code in (401, 403))
                )
                if (
                    not antigravity_account_restriction
                    and (err_check.should_fallback or resp.status_code == 429)
                    and len(candidate_accounts) > 1
                ):
                    account_switch_count += 1
                    candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                    last_error_resp = JSONResponse(
                        status_code=resp.status_code,
                        content=resp.body if isinstance(resp.body, dict) else {"error": {"message": raw_text}},
                    )
                    continue
                else:
                    await record_usage_and_telemetry(
                        request=request,
                        api_key=api_key,
                        endpoint="/routerapi/v1/chat/completions",
                        model=requested_model,
                        provider_id=plugin.id,
                        account_id=selected_account.id,
                        status_code=resp.status_code,
                        start_time=start_time,
                        is_stream=False,
                        error=err_check.error_message or raw_text,
                    )
                    return JSONResponse(
                        status_code=resp.status_code,
                        content=resp.body if isinstance(resp.body, dict) else {"error": {"message": raw_text}},
                    )

            # Success
            await mark_account_success(account_router, db, selected_account)

            prompt_tokens = 0
            completion_tokens = 0
            if isinstance(resp.body, dict) and "usage" in resp.body:
                u = resp.body["usage"]
                prompt_tokens = u.get("prompt_tokens", 0)
                completion_tokens = u.get("completion_tokens", 0)

            await record_usage_and_telemetry(
                request=request,
                api_key=api_key,
                endpoint="/routerapi/v1/chat/completions",
                model=requested_model,
                provider_id=plugin.id,
                account_id=selected_account.id,
                status_code=resp.status_code,
                start_time=start_time,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                is_stream=False,
            )

            return JSONResponse(status_code=resp.status_code, content=resp.body)

    # If all accounts are exhausted or rate-limited
    now = time.time()
    waits = [
        (a.rate_limited_until - now)
        for a in accounts
        if a.rate_limited_until and a.rate_limited_until > now
    ]
    retry_seconds = max(1, int(min(waits))) if waits else 60
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": str(retry_seconds)},
        content={"error": {"message": "All accounts exhausted or rate-limited", "type": "service_unavailable", "code": 503}},
    )


# -----------------------------------------------------------------------------
# Anthropic /v1/messages
# -----------------------------------------------------------------------------

def translate_anthropic_to_openai(payload: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    openai_messages = []
    system_val = payload.get("system")
    if system_val:
        if isinstance(system_val, list):
            sys_text = "\n".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in system_val])
        else:
            sys_text = str(system_val)
        openai_messages.append({"role": "system", "content": sys_text})

    for msg in payload.get("messages", []):
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content_text = "".join(text_parts) if text_parts else str(content)
        else:
            content_text = content
        openai_messages.append({"role": role, "content": content_text})

    openai_payload = {
        "model": model_name,
        "messages": openai_messages,
        "stream": bool(payload.get("stream", False)),
    }
    if "max_tokens" in payload:
        openai_payload["max_tokens"] = payload["max_tokens"]
    if "temperature" in payload:
        openai_payload["temperature"] = payload["temperature"]
    if "top_p" in payload:
        openai_payload["top_p"] = payload["top_p"]
    return openai_payload


def translate_openai_to_anthropic_json(openai_body: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    choices = openai_body.get("choices", [])
    content_text = ""
    stop_reason = "end_turn"
    if choices:
        choice = choices[0]
        msg = choice.get("message", {})
        content_text = msg.get("content") or ""
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            stop_reason = "max_tokens"
        elif finish_reason == "tool_calls":
            stop_reason = "tool_use"

    usage = openai_body.get("usage", {})
    return {
        "id": f"msg_{uuid.uuid4().hex[:16]}",
        "type": "message",
        "role": "assistant",
        "model": model_name,
        "content": [
            {
                "type": "text",
                "text": content_text,
            }
        ],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


async def translate_openai_stream_to_anthropic(
    openai_stream: AsyncGenerator[bytes, None],
    model_name: str,
) -> AsyncGenerator[bytes, None]:
    msg_id = f"msg_{uuid.uuid4().hex[:16]}"
    
    # message_start
    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': model_name, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}})}\n\n".encode("utf-8")

    # content_block_start
    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n".encode("utf-8")

    total_tokens = 0
    buffer = ""

    async for chunk in openai_stream:
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                continue
            try:
                data = json.loads(data_str)
            except Exception:
                continue

            choices = data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content_delta = delta.get("content")
                if content_delta:
                    total_tokens += 1
                    event_data = {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": content_delta},
                    }
                    yield f"event: content_block_delta\ndata: {json.dumps(event_data)}\n\n".encode("utf-8")

    # content_block_stop
    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n".encode("utf-8")

    # message_delta
    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': total_tokens}})}\n\n".encode("utf-8")

    # message_stop
    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n".encode("utf-8")


@router.post("/v1/messages")
async def anthropic_messages(
    request: Request,
    api_key: Optional[ApiKey] = Depends(get_current_api_key),
):
    """
    Anthropic-compatible messages endpoint.
    Routes to Anthropic provider or translates if routing to OpenAI-compatible provider.
    """
    start_time = time.time()
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    requested_model = body.get("model", "")
    if not requested_model:
        raise HTTPException(status_code=400, detail="Model parameter is required")

    is_stream = bool(body.get("stream", False))

    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)
    account_router: Optional[AccountRouter] = getattr(request.app.state, "account_router", None)
    proxy_engine: Optional[ProxyEngine] = getattr(request.app.state, "proxy_engine", None)

    await sync_plugin_models_from_db(db, pm)
    all_accounts = await get_all_active_accounts(db)
    plugin, upstream_model = resolve_plugin_and_model(pm, requested_model, accounts=all_accounts)
    if not plugin:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={"error": {"message": "No enabled provider plugin available", "type": "service_unavailable", "code": 503}},
        )

    if api_key:
        if api_key.allowed_plugins and plugin.id not in api_key.allowed_plugins:
            raise HTTPException(status_code=403, detail="Plugin not allowed for this API key")
        if api_key.allowed_models and requested_model not in api_key.allowed_models:
            raise HTTPException(status_code=403, detail="Model not allowed for this API key")

    accounts = await get_active_accounts_for_provider(db, plugin.id)
    if not accounts:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={"error": {"message": f"No active accounts configured for provider '{plugin.id}'", "type": "service_unavailable", "code": 503}},
        )

    is_anthropic_plugin = (getattr(plugin, "format", "openai") == "anthropic")
    candidate_accounts = filter_accounts_for_model(plugin, accounts, upstream_model)

    while candidate_accounts:
        selected_account = select_account(account_router, candidate_accounts)
        if not selected_account:
            break

        base_url = plugin.get_base_url(selected_account)
        if is_anthropic_plugin:
            req_url = base_url.rstrip("/") + ("/messages" if base_url.endswith("/v1") else "/v1/messages")
            if base_url.endswith("/messages"):
                req_url = base_url
            headers = plugin.build_headers(selected_account, stream=is_stream)
            upstream_body = dict(body)
            upstream_body["model"] = upstream_model
            proxy_req = ProxyRequest(
                method="POST",
                url=req_url,
                headers=headers,
                body=upstream_body,
                is_stream=is_stream,
                model=upstream_model,
                client_format="anthropic",
            )
        else:
            # Route to OpenAI format plugin
            req_url = f"{base_url}/chat/completions"
            if base_url.endswith("/chat/completions"):
                req_url = base_url
            headers = plugin.build_headers(selected_account, stream=is_stream)
            upstream_body = translate_anthropic_to_openai(body, upstream_model)
            proxy_req = ProxyRequest(
                method="POST",
                url=req_url,
                headers=headers,
                body=upstream_body,
                is_stream=is_stream,
                model=upstream_model,
                client_format="openai",
            )

        proxy_req = plugin.configure_request(proxy_req)
        proxy_req = plugin.transform_request(proxy_req, selected_account)

        if is_stream:
            try:
                status_code, resp_headers, stream_gen = await execute_proxy_stream(
                    proxy_engine, plugin, selected_account, proxy_req
                )
            except Exception as ex:
                err_check = ErrorCheckResult(is_error=True, error_message=str(ex), should_fallback=True)
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)
                candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                continue

            if status_code >= 400:
                err_chunks = []
                try:
                    async for c in stream_gen:
                        err_chunks.append(c)
                except Exception:
                    pass
                err_text = b"".join(err_chunks).decode("utf-8", errors="replace")
                err_check = plugin.detect_error_or_limit(status_code, err_text, resp_headers)
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)

                if (err_check.should_fallback or status_code == 429) and len(candidate_accounts) > 1:
                    candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                    continue
                else:
                    await record_usage_and_telemetry(
                        request=request,
                        api_key=api_key,
                        endpoint="/routerapi/v1/messages",
                        model=requested_model,
                        provider_id=plugin.id,
                        account_id=selected_account.id,
                        status_code=status_code,
                        start_time=start_time,
                        is_stream=True,
                        error=err_check.error_message or err_text,
                    )
                    return Response(content=err_text, status_code=status_code, media_type="application/json")

            await mark_account_success(account_router, db, selected_account)

            final_stream = stream_gen if is_anthropic_plugin else translate_openai_stream_to_anthropic(stream_gen, requested_model)

            async def wrapped_anthropic_stream():
                try:
                    async for chunk in final_stream:
                        yield chunk
                finally:
                    await record_usage_and_telemetry(
                        request=request,
                        api_key=api_key,
                        endpoint="/routerapi/v1/messages",
                        model=requested_model,
                        provider_id=plugin.id,
                        account_id=selected_account.id,
                        status_code=200,
                        start_time=start_time,
                        is_stream=True,
                    )

            return StreamingResponse(
                wrapped_anthropic_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        else:
            try:
                resp = await execute_proxy_request(proxy_engine, plugin, selected_account, proxy_req)
            except Exception as ex:
                err_check = ErrorCheckResult(is_error=True, error_message=str(ex), should_fallback=True)
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)
                candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                continue

            raw_text = resp.raw_text or (json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body))
            err_check = plugin.detect_error_or_limit(resp.status_code, raw_text, resp.headers)

            if err_check.is_error or err_check.is_rate_limited or resp.status_code >= 400:
                await mark_account_error_or_limit(account_router, db, selected_account, err_check)
                if (err_check.should_fallback or resp.status_code == 429) and len(candidate_accounts) > 1:
                    candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                    continue
                else:
                    await record_usage_and_telemetry(
                        request=request,
                        api_key=api_key,
                        endpoint="/routerapi/v1/messages",
                        model=requested_model,
                        provider_id=plugin.id,
                        account_id=selected_account.id,
                        status_code=resp.status_code,
                        start_time=start_time,
                        is_stream=False,
                        error=err_check.error_message or raw_text,
                    )
                    return JSONResponse(
                        status_code=resp.status_code,
                        content=resp.body if isinstance(resp.body, dict) else {"error": {"message": raw_text}},
                    )

            await mark_account_success(account_router, db, selected_account)

            if is_anthropic_plugin:
                final_content = resp.body
                tokens = final_content.get("usage", {}) if isinstance(final_content, dict) else {}
                prompt_tokens = tokens.get("input_tokens", 0)
                completion_tokens = tokens.get("output_tokens", 0)
            else:
                final_content = translate_openai_to_anthropic_json(resp.body if isinstance(resp.body, dict) else {}, requested_model)
                tokens = final_content.get("usage", {})
                prompt_tokens = tokens.get("input_tokens", 0)
                completion_tokens = tokens.get("output_tokens", 0)

            await record_usage_and_telemetry(
                request=request,
                api_key=api_key,
                endpoint="/routerapi/v1/messages",
                model=requested_model,
                provider_id=plugin.id,
                account_id=selected_account.id,
                status_code=resp.status_code,
                start_time=start_time,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                is_stream=False,
            )

            return JSONResponse(status_code=resp.status_code, content=final_content)

    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "60"},
        content={"error": {"message": "All accounts exhausted or rate-limited", "type": "service_unavailable", "code": 503}},
    )


# -----------------------------------------------------------------------------
# Embeddings /v1/embeddings
# -----------------------------------------------------------------------------

@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    api_key: Optional[ApiKey] = Depends(get_current_api_key),
):
    """
    Forwards embedding request to plugin supporting embeddings.
    """
    start_time = time.time()
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    requested_model = body.get("model", "")
    if not requested_model:
        raise HTTPException(status_code=400, detail="Model parameter is required")

    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)
    account_router: Optional[AccountRouter] = getattr(request.app.state, "account_router", None)
    proxy_engine: Optional[ProxyEngine] = getattr(request.app.state, "proxy_engine", None)

    await sync_plugin_models_from_db(db, pm)
    all_accounts = await get_all_active_accounts(db)
    plugin, upstream_model = resolve_plugin_and_model(pm, requested_model, accounts=all_accounts)
    if not plugin:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={"error": {"message": "No enabled provider plugin available", "type": "service_unavailable", "code": 503}},
        )

    if api_key:
        if api_key.allowed_plugins and plugin.id not in api_key.allowed_plugins:
            raise HTTPException(status_code=403, detail="Plugin not allowed for this API key")
        if api_key.allowed_models and requested_model not in api_key.allowed_models:
            raise HTTPException(status_code=403, detail="Model not allowed for this API key")

    accounts = await get_active_accounts_for_provider(db, plugin.id)
    if not accounts:
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={"error": {"message": f"No active accounts configured for provider '{plugin.id}'", "type": "service_unavailable", "code": 503}},
        )

    candidate_accounts = filter_accounts_for_model(plugin, accounts, upstream_model)
    upstream_body = dict(body)
    upstream_body["model"] = upstream_model

    while candidate_accounts:
        selected_account = select_account(account_router, candidate_accounts)
        if not selected_account:
            break

        base_url = plugin.get_base_url(selected_account)
        req_url = f"{base_url}/embeddings"
        if base_url.endswith("/embeddings"):
            req_url = base_url
        headers = plugin.build_headers(selected_account, stream=False)
        proxy_req = ProxyRequest(
            method="POST",
            url=req_url,
            headers=headers,
            body=upstream_body,
            is_stream=False,
            model=upstream_model,
            client_format="openai",
        )
        proxy_req = plugin.configure_request(proxy_req)
        proxy_req = plugin.transform_request(proxy_req, selected_account)

        try:
            resp = await execute_proxy_request(proxy_engine, plugin, selected_account, proxy_req)
        except Exception as ex:
            err_check = ErrorCheckResult(is_error=True, error_message=str(ex), should_fallback=True)
            await mark_account_error_or_limit(account_router, db, selected_account, err_check)
            candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
            continue

        raw_text = resp.raw_text or (json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body))
        err_check = plugin.detect_error_or_limit(resp.status_code, raw_text, resp.headers)

        if err_check.is_error or resp.status_code >= 400:
            await mark_account_error_or_limit(account_router, db, selected_account, err_check)
            if (err_check.should_fallback or resp.status_code == 429) and len(candidate_accounts) > 1:
                candidate_accounts = [a for a in candidate_accounts if a.id != selected_account.id]
                continue
            else:
                await record_usage_and_telemetry(
                    request=request,
                    api_key=api_key,
                    endpoint="/routerapi/v1/embeddings",
                    model=requested_model,
                    provider_id=plugin.id,
                    account_id=selected_account.id,
                    status_code=resp.status_code,
                    start_time=start_time,
                    is_stream=False,
                    error=err_check.error_message or raw_text,
                )
                return JSONResponse(
                    status_code=resp.status_code,
                    content=resp.body if isinstance(resp.body, dict) else {"error": {"message": raw_text}},
                )

        await mark_account_success(account_router, db, selected_account)

        prompt_tokens = 0
        if isinstance(resp.body, dict) and "usage" in resp.body:
            prompt_tokens = resp.body["usage"].get("prompt_tokens", 0)

        await record_usage_and_telemetry(
            request=request,
            api_key=api_key,
            endpoint="/routerapi/v1/embeddings",
            model=requested_model,
            provider_id=plugin.id,
            account_id=selected_account.id,
            status_code=resp.status_code,
            start_time=start_time,
            prompt_tokens=prompt_tokens,
            is_stream=False,
        )

        return JSONResponse(status_code=resp.status_code, content=resp.body)

    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "60"},
        content={"error": {"message": "All accounts exhausted or rate-limited", "type": "service_unavailable", "code": 503}},
    )
