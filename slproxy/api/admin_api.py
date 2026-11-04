"""
Admin API for WebUI (/api)
Implements:
- GET /api/plugins
- POST /api/plugins/{id}/toggle
- GET /api/plugins/{id}/code
- POST /api/plugins/{id}/code (Sub-second hot-reload)
- POST /api/plugins/create
- GET /api/accounts
- POST /api/accounts
- PUT /api/accounts/{id}
- DELETE /api/accounts/{id}
- POST /api/accounts/{id}/reset-cooldown
- GET /api/keys
- POST /api/keys
- DELETE /api/keys/{id}
- GET /api/metrics
- GET /api/logs
"""

import importlib.util
import inspect
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from slproxy.config import PLUGINS_DIR, TEMPLATES_DIR
from slproxy.core.metrics import MetricsManager
from slproxy.core.plugin_base import BasePlugin, ModelInfo
from slproxy.core.plugin_manager import PluginManager
from slproxy.db.database import Database

router = APIRouter()


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------

class CodeUpdateRequest(BaseModel):
    code: str


class PluginCreateRequest(BaseModel):
    id: str
    name: str
    code: Optional[str] = None
    template: Optional[str] = None


class AccountCreateRequest(BaseModel):
    provider_id: str
    name: str
    api_key: str = ""
    base_url: Optional[str] = None
    priority: int = 1
    weight: int = 1
    extra_headers: Optional[Dict[str, str]] = None
    extra_config: Optional[Dict[str, Any]] = None


class AccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    priority: Optional[int] = None
    weight: Optional[int] = None
    is_active: Optional[bool] = None
    extra_headers: Optional[Dict[str, str]] = None
    extra_config: Optional[Dict[str, Any]] = None


class KeyCreateRequest(BaseModel):
    name: str
    expires_at: Optional[float] = None
    max_requests: Optional[int] = None
    max_tokens: Optional[int] = None
    allowed_plugins: Optional[List[str]] = None
    allowed_models: Optional[List[str]] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class ModelAddRequest(BaseModel):
    id: str
    name: str
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    pricing: Optional[Dict[str, float]] = None
    extra: Optional[Dict[str, Any]] = None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def hot_reload_plugin(pm: PluginManager, plugin_id: str, code: str) -> BasePlugin:
    try:
        return pm.save_and_deploy_plugin(plugin_id, code)
    except NotImplementedError:
        pass

    # Fallback sub-second hot-reload
    pm.plugins_dir.mkdir(parents=True, exist_ok=True)
    file_path = pm.plugins_dir / f"{plugin_id}.py"
    file_path.write_text(code, encoding="utf-8")

    try:
        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_id}", file_path)
        if not spec or not spec.loader:
            raise ValueError(f"Could not load module spec from {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        raise ValueError(f"Failed to load plugin code: {str(e)}")

    plugin_instance = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
            plugin_instance = attr()
            break

    if not plugin_instance:
        raise ValueError("Plugin module must define a subclass of BasePlugin")

    if not getattr(plugin_instance, "id", None) or plugin_instance.id == "base":
        plugin_instance.id = plugin_id
    pm.plugins[plugin_instance.id] = plugin_instance
    pm.plugin_files[plugin_instance.id] = file_path
    return plugin_instance


def generate_plugin_template(plugin_id: str, name: str) -> str:
    class_name = name.title().replace(" ", "").replace("-", "_") + "Plugin"
    return f'''"""
Custom Plugin: {name} ({plugin_id})
"""

from slproxy.core.plugin_base import BasePlugin, ModelInfo


class {class_name}(BasePlugin):
    id = "{plugin_id}"
    name = "{name}"
    description = "{name} Custom Provider Plugin"
    version = "1.0.0"
    author = "SLProxy Admin"
    default_base_url = "https://api.openai.com/v1"
    format = "openai"
    models = [
        ModelInfo(id="{plugin_id}-default", name="{name} Default Model")
    ]
'''


# -----------------------------------------------------------------------------
# Plugins API
# -----------------------------------------------------------------------------

@router.get("/plugins")
async def get_plugins(request: Request):
    """
    List all plugins, their metadata, enabled status, models, and account counts.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    account_counts: Dict[str, int] = {}
    if db:
        async with db.conn.execute("SELECT provider_id, COUNT(*) as cnt FROM accounts GROUP BY provider_id") as cur:
            for row in await cur.fetchall():
                account_counts[row["provider_id"]] = row["cnt"]
        try:
            async with db.conn.execute("SELECT plugin_id, models FROM plugin_settings WHERE models IS NOT NULL") as cur:
                for row in await cur.fetchall():
                    p_id = row["plugin_id"]
                    if pm and p_id in pm.plugins and row["models"]:
                        try:
                            persisted = [ModelInfo(**item) for item in json.loads(row["models"])]
                            if persisted:
                                pm.plugins[p_id].models = persisted
                        except Exception:
                            pass
        except Exception:
            pass

    plugin_list: List[Dict[str, Any]] = []
    if pm:
        for plugin in pm.list_plugins():
            models_data = []
            plugin_models = plugin.fetch_models() if hasattr(plugin, "fetch_models") else plugin.models
            for m in (plugin_models or []):
                if hasattr(m, "model_dump"):
                    models_data.append(m.model_dump())
                elif hasattr(m, "dict"):
                    models_data.append(m.dict())
                elif isinstance(m, dict):
                    models_data.append(m)
                else:
                    models_data.append({"id": str(m), "name": str(m)})

            plugin_list.append({
                "id": plugin.id,
                "name": plugin.name,
                "description": plugin.description,
                "version": plugin.version,
                "author": plugin.author,
                "icon": plugin.icon,
                "color": plugin.color,
                "format": plugin.format,
                "default_base_url": plugin.default_base_url,
                "enabled": getattr(plugin, "enabled", True),
                "models": models_data,
                "account_count": account_counts.get(plugin.id, 0),
            })

    return plugin_list


@router.post("/plugins/{plugin_id}/toggle")
async def toggle_plugin(plugin_id: str, request: Request):
    """
    Enable / disable plugin.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    plugin = pm.get_plugin(plugin_id) if pm else None
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    new_state = not getattr(plugin, "enabled", True)
    plugin.enabled = new_state

    if db:
        now = time.time()
        await db.conn.execute(
            """INSERT INTO plugin_settings (plugin_id, enabled, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at""",
            (plugin_id, 1 if new_state else 0, now),
        )
        await db.conn.commit()

    return {"id": plugin_id, "enabled": new_state, "status": "ok"}


@router.get("/plugins/{plugin_id}/code")
async def get_plugin_code(plugin_id: str, request: Request):
    """
    Return plugin source code.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    code: Optional[str] = None
    if pm:
        try:
            code = pm.get_plugin_source(plugin_id)
        except (NotImplementedError, Exception):
            pass

        if not code and plugin_id in getattr(pm, "plugin_files", {}):
            file_path = pm.plugin_files[plugin_id]
            if file_path.exists():
                code = file_path.read_text(encoding="utf-8")

        if not code:
            direct_file = getattr(pm, "plugins_dir", PLUGINS_DIR) / f"{plugin_id}.py"
            if direct_file.exists():
                code = direct_file.read_text(encoding="utf-8")

        if not code:
            plugin = pm.get_plugin(plugin_id)
            if plugin:
                try:
                    code = inspect.getsource(type(plugin))
                except Exception:
                    pass

    if not code and db:
        async with db.conn.execute("SELECT custom_code FROM plugin_settings WHERE plugin_id = ?", (plugin_id,)) as cur:
            row = await cur.fetchone()
            if row and row["custom_code"]:
                code = row["custom_code"]

    if not code:
        plugin = pm.get_plugin(plugin_id) if pm else None
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
        code = generate_plugin_template(plugin_id, plugin.name)

    return {"id": plugin_id, "code": code}


@router.post("/plugins/{plugin_id}/code")
async def update_plugin_code(plugin_id: str, payload: CodeUpdateRequest, request: Request):
    """
    Sub-second hot-reload: saves source and deploys new plugin version.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    if not pm:
        raise HTTPException(status_code=500, detail="PluginManager not initialized")

    try:
        plugin = hot_reload_plugin(pm, plugin_id, payload.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to deploy plugin: {str(e)}")

    if db:
        now = time.time()
        await db.conn.execute(
            """INSERT INTO plugin_settings (plugin_id, custom_code, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET custom_code = excluded.custom_code, updated_at = excluded.updated_at""",
            (plugin_id, payload.code, now),
        )
        await db.conn.commit()

    return {
        "id": plugin_id,
        "status": "deployed",
        "message": "Plugin updated and reloaded",
        "name": getattr(plugin, "name", plugin_id) if plugin else plugin_id,
    }


@router.post("/plugins/create")
async def create_plugin(payload: PluginCreateRequest, request: Request):
    """
    Create a new custom plugin from code or template.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    if not pm:
        raise HTTPException(status_code=500, detail="PluginManager not initialized")

    code = payload.code
    if not code:
        code = generate_plugin_template(payload.id, payload.name)

    try:
        plugin = hot_reload_plugin(pm, payload.id, code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create plugin: {str(e)}")

    if db:
        now = time.time()
        await db.conn.execute(
            """INSERT INTO plugin_settings (plugin_id, enabled, custom_code, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET custom_code = excluded.custom_code, updated_at = excluded.updated_at""",
            (payload.id, 1, code, now),
        )
        await db.conn.commit()

    return {
        "id": payload.id,
        "name": payload.name,
        "status": "created",
        "message": "Plugin successfully created and deployed",
    }


@router.delete("/plugins/{plugin_id}")
async def delete_plugin(plugin_id: str, request: Request):
    """
    Remove and delete an installed plugin.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    if not pm:
        raise HTTPException(status_code=500, detail="PluginManager not initialized")

    if plugin_id in pm.plugins:
        del pm.plugins[plugin_id]

    file_path = pm.plugin_files.pop(plugin_id, None)
    if not file_path:
        file_path = pm.plugins_dir / f"{plugin_id}.py"

    if file_path.exists():
        try:
            file_path.unlink()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete plugin file: {str(e)}")

    if db:
        await db.conn.execute("DELETE FROM plugin_settings WHERE plugin_id = ?", (plugin_id,))
        await db.conn.commit()

    return {"status": "deleted", "id": plugin_id}


@router.post("/plugins/{plugin_id}/models")
async def add_plugin_model(plugin_id: str, payload: ModelAddRequest, request: Request):
    """
    Dynamically add or update a model for a specific plugin.
    Adds model to plugin.add_model(model_info) and persists update to SQLite plugin_settings.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    plugin = pm.get_plugin(plugin_id) if pm else None
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    model_info = ModelInfo(
        id=payload.id,
        name=payload.name,
        context_window=payload.context_window,
        max_output_tokens=payload.max_output_tokens,
        supports_streaming=payload.supports_streaming,
        supports_tools=payload.supports_tools,
        supports_vision=payload.supports_vision,
        pricing=payload.pricing or {},
        extra=payload.extra or {},
    )

    plugin.add_model(model_info)

    if db:
        try:
            await db.conn.execute("ALTER TABLE plugin_settings ADD COLUMN models TEXT")
            await db.conn.commit()
        except Exception:
            pass
        now = time.time()
        models_json = json.dumps([m.model_dump() for m in plugin.models])
        await db.conn.execute(
            """INSERT INTO plugin_settings (plugin_id, models, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET models = excluded.models, updated_at = excluded.updated_at""",
            (plugin_id, models_json, now),
        )
        await db.conn.commit()

    return {"status": "added", "model": model_info.model_dump()}


@router.delete("/plugins/{plugin_id}/models/{model_id}")
async def remove_plugin_model(plugin_id: str, model_id: str, request: Request):
    """
    Dynamically remove a model from a plugin's supported models list.
    Removes model via plugin.remove_model(model_id) and persists update to SQLite plugin_settings.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    plugin = pm.get_plugin(plugin_id) if pm else None
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")

    removed = plugin.remove_model(model_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in plugin '{plugin_id}'")

    if db:
        try:
            await db.conn.execute("ALTER TABLE plugin_settings ADD COLUMN models TEXT")
            await db.conn.commit()
        except Exception:
            pass
        now = time.time()
        models_json = json.dumps([m.model_dump() for m in plugin.models])
        await db.conn.execute(
            """INSERT INTO plugin_settings (plugin_id, models, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET models = excluded.models, updated_at = excluded.updated_at""",
            (plugin_id, models_json, now),
        )
        await db.conn.commit()

    return {"status": "removed", "model_id": model_id}


@router.get("/templates")
async def list_templates():
    """
    List available provider plugin reference templates.
    """
    templates = []
    if TEMPLATES_DIR.exists():
        for file_path in sorted(TEMPLATES_DIR.glob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue
            template_id = file_path.stem
            try:
                code = file_path.read_text(encoding="utf-8")
                # Parse metadata simply
                name = template_id.replace("_", " ").title()
                format_type = "openai"
                description = f"{name} Provider Template"
                models_count = 0
                for line in code.splitlines():
                    if "name = " in line and not name.endswith("Plugin"):
                        name = line.split("=")[1].strip().strip('"').strip("'")
                    if "description = " in line:
                        description = line.split("=")[1].strip().strip('"').strip("'")
                    if "format = " in line:
                        format_type = line.split("=")[1].strip().strip('"').strip("'")
                    if "ModelInfo(" in line:
                        models_count += 1

                templates.append({
                    "id": template_id,
                    "name": name,
                    "description": description,
                    "format": format_type,
                    "models_count": models_count,
                    "code": code,
                })
            except Exception:
                continue

    return templates


@router.post("/templates/{template_id}/install")
async def install_template(template_id: str, request: Request):
    """
    Install a reference template into the active plugins directory.
    """
    pm: Optional[PluginManager] = getattr(request.app.state, "plugin_manager", None)
    db: Optional[Database] = getattr(request.app.state, "db", None)

    if not pm:
        raise HTTPException(status_code=500, detail="PluginManager not initialized")

    template_file = TEMPLATES_DIR / f"{template_id}.py"
    if not template_file.exists():
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

    code = template_file.read_text(encoding="utf-8")
    try:
        plugin = hot_reload_plugin(pm, template_id, code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to install template: {str(e)}")

    if db:
        now = time.time()
        await db.conn.execute(
            """INSERT INTO plugin_settings (plugin_id, enabled, custom_code, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET custom_code = excluded.custom_code, updated_at = excluded.updated_at""",
            (template_id, 1, code, now),
        )
        await db.conn.commit()

    return {
        "id": template_id,
        "name": getattr(plugin, "name", template_id),
        "status": "installed",
        "message": f"Template {template_id} successfully installed and deployed",
    }


# -----------------------------------------------------------------------------
# Accounts API
# -----------------------------------------------------------------------------

@router.get("/accounts")
async def get_accounts(request: Request, provider_id: Optional[str] = Query(None)):
    """
    List accounts (supports filtering by ?provider_id=...).
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        return []

    if provider_id:
        sql = "SELECT * FROM accounts WHERE provider_id = ? ORDER BY priority ASC, id ASC"
        params = (provider_id,)
    else:
        sql = "SELECT * FROM accounts ORDER BY provider_id ASC, priority ASC, id ASC"
        params = ()

    accounts = []
    async with db.conn.execute(sql, params) as cur:
        for r in await cur.fetchall():
            extra_headers = json.loads(r["extra_headers"]) if r["extra_headers"] else {}
            extra_config = json.loads(r["extra_config"]) if r["extra_config"] else {}
            accounts.append({
                "id": r["id"],
                "provider_id": r["provider_id"],
                "name": r["name"],
                "api_key": r["api_key"] or "",
                "base_url": r["base_url"],
                "extra_headers": extra_headers,
                "extra_config": extra_config,
                "priority": r["priority"],
                "weight": r["weight"],
                "is_active": bool(r["is_active"]),
                "rate_limited_until": r["rate_limited_until"],
                "error_count": r["error_count"],
                "success_count": r["success_count"],
                "last_used_at": r["last_used_at"],
            })

    return accounts


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(payload: AccountCreateRequest, request: Request):
    """
    Create a new account.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    account_id = f"acc_{uuid.uuid4().hex[:12]}"
    headers_str = json.dumps(payload.extra_headers or {})
    config_str = json.dumps(payload.extra_config or {})

    await db.conn.execute(
        """INSERT INTO accounts 
        (id, provider_id, name, api_key, base_url, extra_headers, extra_config, priority, weight, is_active, rate_limited_until, error_count, success_count, last_used_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            account_id,
            payload.provider_id,
            payload.name,
            payload.api_key,
            payload.base_url,
            headers_str,
            config_str,
            payload.priority,
            payload.weight,
            1,
            None,
            0,
            0,
            None,
        ),
    )
    await db.conn.commit()

    return {
        "id": account_id,
        "provider_id": payload.provider_id,
        "name": payload.name,
        "api_key": payload.api_key,
        "base_url": payload.base_url,
        "extra_headers": payload.extra_headers or {},
        "extra_config": payload.extra_config or {},
        "priority": payload.priority,
        "weight": payload.weight,
        "is_active": True,
        "rate_limited_until": None,
        "error_count": 0,
        "success_count": 0,
        "last_used_at": None,
    }


@router.put("/accounts/{account_id}")
async def update_account(account_id: str, payload: AccountUpdateRequest, request: Request):
    """
    Update account.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    async with db.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)) as cur:
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    updates = []
    params = []
    if payload.name is not None:
        updates.append("name = ?")
        params.append(payload.name)
    if payload.api_key is not None:
        updates.append("api_key = ?")
        params.append(payload.api_key)
    if payload.base_url is not None:
        updates.append("base_url = ?")
        params.append(payload.base_url)
    if payload.priority is not None:
        updates.append("priority = ?")
        params.append(payload.priority)
    if payload.weight is not None:
        updates.append("weight = ?")
        params.append(payload.weight)
    if payload.is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if payload.is_active else 0)
    if payload.extra_headers is not None:
        updates.append("extra_headers = ?")
        params.append(json.dumps(payload.extra_headers))
    if payload.extra_config is not None:
        updates.append("extra_config = ?")
        params.append(json.dumps(payload.extra_config))

    if updates:
        sql = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?"
        params.append(account_id)
        await db.conn.execute(sql, tuple(params))
        await db.conn.commit()

    async with db.conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)) as cur:
        updated_row = await cur.fetchone()

    return {
        "id": updated_row["id"],
        "provider_id": updated_row["provider_id"],
        "name": updated_row["name"],
        "api_key": updated_row["api_key"],
        "base_url": updated_row["base_url"],
        "extra_headers": json.loads(updated_row["extra_headers"] or "{}"),
        "extra_config": json.loads(updated_row["extra_config"] or "{}"),
        "priority": updated_row["priority"],
        "weight": updated_row["weight"],
        "is_active": bool(updated_row["is_active"]),
        "rate_limited_until": updated_row["rate_limited_until"],
        "error_count": updated_row["error_count"],
        "success_count": updated_row["success_count"],
        "last_used_at": updated_row["last_used_at"],
    }


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str, request: Request):
    """
    Delete account.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    async with db.conn.execute("SELECT id FROM accounts WHERE id = ?", (account_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    await db.conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    await db.conn.commit()
    return {"status": "deleted", "id": account_id}


@router.post("/accounts/{account_id}/reset-cooldown")
async def reset_cooldown(account_id: str, request: Request):
    """
    Clears rate_limited_until and resets error count.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    async with db.conn.execute("SELECT id FROM accounts WHERE id = ?", (account_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    await db.conn.execute(
        "UPDATE accounts SET rate_limited_until = NULL, error_count = 0 WHERE id = ?",
        (account_id,),
    )
    await db.conn.commit()
    return {"status": "ok", "id": account_id, "message": "Cooldown and error count reset"}


# -----------------------------------------------------------------------------
# API Keys API
# -----------------------------------------------------------------------------

@router.get("/keys")
async def get_keys(request: Request):
    """
    List router local API keys with usage stats.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        return []

    keys = []
    async with db.conn.execute("SELECT * FROM api_keys ORDER BY created_at DESC") as cur:
        for r in await cur.fetchall():
            allowed_plugins = json.loads(r["allowed_plugins"] or "[]")
            allowed_models = json.loads(r["allowed_models"] or "[]")
            extra_metadata = json.loads(r["extra_metadata"] or "{}")
            keys.append({
                "id": r["id"],
                "key": r["key"],
                "name": r["name"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "max_requests": r["max_requests"],
                "max_tokens": r["max_tokens"],
                "used_requests": r["used_requests"] or 0,
                "used_tokens": r["used_tokens"] or 0,
                "is_active": bool(r["is_active"]),
                "allowed_plugins": allowed_plugins,
                "allowed_models": allowed_models,
                "extra_metadata": extra_metadata,
            })

    return keys


@router.post("/keys", status_code=status.HTTP_201_CREATED)
async def create_key(payload: KeyCreateRequest, request: Request):
    """
    Generate new local API key.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    key_id = f"key_{uuid.uuid4().hex[:12]}"
    secret_key = f"slp-live-{secrets.token_hex(16)}"
    now = time.time()
    plugins_str = json.dumps(payload.allowed_plugins or [])
    models_str = json.dumps(payload.allowed_models or [])
    meta_str = json.dumps(payload.extra_metadata or {})

    await db.conn.execute(
        """INSERT INTO api_keys 
        (id, key, name, created_at, expires_at, max_requests, max_tokens, used_requests, used_tokens, is_active, allowed_plugins, allowed_models, extra_metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            key_id,
            secret_key,
            payload.name,
            now,
            payload.expires_at,
            payload.max_requests,
            payload.max_tokens,
            0,
            0,
            1,
            plugins_str,
            models_str,
            meta_str,
        ),
    )
    await db.conn.commit()

    return {
        "id": key_id,
        "key": secret_key,
        "name": payload.name,
        "created_at": now,
        "expires_at": payload.expires_at,
        "max_requests": payload.max_requests,
        "max_tokens": payload.max_tokens,
        "used_requests": 0,
        "used_tokens": 0,
        "is_active": True,
        "allowed_plugins": payload.allowed_plugins or [],
        "allowed_models": payload.allowed_models or [],
        "extra_metadata": payload.extra_metadata or {},
    }


@router.delete("/keys/{key_id}")
async def delete_key(key_id: str, request: Request):
    """
    Revoke / delete API key.
    """
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not initialized")

    async with db.conn.execute("SELECT id FROM api_keys WHERE id = ?", (key_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail=f"API key '{key_id}' not found")

    await db.conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    await db.conn.commit()
    return {"status": "deleted", "id": key_id}


# -----------------------------------------------------------------------------
# Metrics and Logs
# -----------------------------------------------------------------------------

@router.get("/metrics")
async def get_metrics(request: Request):
    """
    Return summary statistics (total requests, error rate, tokens, latency, per-provider stats).
    """
    metrics: Optional[MetricsManager] = getattr(request.app.state, "metrics_manager", None)
    if metrics:
        return metrics.get_summary()

    # DB fallback
    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        return {"total_requests": 0, "total_errors": 0, "total_tokens": 0, "success_rate": 1.0, "provider_stats": {}}

    async with db.conn.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors, SUM(total_tokens) as tokens FROM request_logs"
    ) as cur:
        row = await cur.fetchone()
        total = row["total"] or 0
        errors = row["errors"] or 0
        tokens = row["tokens"] or 0
        success_rate = ((total - errors) / total) if total > 0 else 1.0

    return {
        "total_requests": total,
        "total_errors": errors,
        "total_tokens": tokens,
        "success_rate": success_rate,
        "provider_stats": {},
    }


@router.get("/logs")
async def get_logs(request: Request, limit: int = Query(50, ge=1, le=500)):
    """
    Return recent request logs.
    """
    metrics: Optional[MetricsManager] = getattr(request.app.state, "metrics_manager", None)
    if metrics and metrics.recent_logs:
        return [
            m.model_dump() if hasattr(m, "model_dump") else m.dict()
            for m in metrics.get_recent_logs(limit)
        ]

    db: Optional[Database] = getattr(request.app.state, "db", None)
    if not db:
        return []

    logs = []
    async with db.conn.execute("SELECT * FROM request_logs ORDER BY timestamp DESC LIMIT ?", (limit,)) as cur:
        for r in await cur.fetchall():
            logs.append({
                "id": r["id"],
                "timestamp": r["timestamp"],
                "client_ip": r["client_ip"],
                "api_key_id": r["api_key_id"],
                "endpoint": r["endpoint"],
                "model": r["model"],
                "provider_id": r["provider_id"],
                "account_id": r["account_id"],
                "status_code": r["status_code"],
                "latency_ms": r["latency_ms"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "total_tokens": r["total_tokens"],
                "is_stream": bool(r["is_stream"]),
                "error": r["error"],
            })

    return logs
