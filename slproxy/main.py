"""
SLProxy Main Application
Mounts WebUI on / and local router APIs on /routerapi, admin APIs on /api
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from slproxy.config import BASE_DIR, DB_PATH, PLUGINS_DIR, REQUEST_TIMEOUT
from slproxy.db.database import Database
from slproxy.core.plugin_manager import PluginManager
from slproxy.core.account_router import AccountRouter
from slproxy.core.key_authenticator import KeyAuthenticator
from slproxy.core.proxy_engine import ProxyEngine
from slproxy.core.metrics import MetricsManager
from slproxy.api.router_api import router as router_api
from slproxy.api.admin_api import router as admin_api


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database connection
    db: Optional[Database] = getattr(app.state, "db", None)
    if db is None:
        db = Database(DB_PATH)
        app.state.db = db
    await db.connect()

    # Plugin Manager
    pm: Optional[PluginManager] = getattr(app.state, "plugin_manager", None)
    if pm is None:
        pm = PluginManager(PLUGINS_DIR)
        try:
            pm.discover_and_load_all()
        except (NotImplementedError, Exception):
            pass
        app.state.plugin_manager = pm

    # Account Router
    if getattr(app.state, "account_router", None) is None:
        app.state.account_router = AccountRouter()

    # Key Authenticator
    if getattr(app.state, "key_authenticator", None) is None:
        try:
            auth = KeyAuthenticator(db)
        except TypeError:
            auth = KeyAuthenticator()
            setattr(auth, "db", db)
        app.state.key_authenticator = auth

    # Proxy Engine
    if getattr(app.state, "proxy_engine", None) is None:
        app.state.proxy_engine = ProxyEngine(client_timeout=REQUEST_TIMEOUT)

    # Metrics Manager
    if getattr(app.state, "metrics_manager", None) is None:
        app.state.metrics_manager = MetricsManager()

    yield

    # Shutdown
    pe = getattr(app.state, "proxy_engine", None)
    if pe is not None and hasattr(pe, "close"):
        try:
            if callable(pe.close):
                res = pe.close()
                if hasattr(res, "__await__"):
                    await res
        except Exception:
            pass

    if getattr(app.state, "db", None) is not None:
        try:
            await app.state.db.close()
        except Exception:
            pass


app = FastAPI(
    title="SLProxy",
    description="Flexible AI Model Router with dynamic Python plugins",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount router_api at /routerapi and admin_api at /api
app.include_router(router_api, prefix="/routerapi")
app.include_router(admin_api, prefix="/api")

# Static WebUI mounting
web_dir = BASE_DIR / "web"
web_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.api_route("/", methods=["GET", "HEAD"])
async def serve_root():
    index_file = web_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "SLProxy is running.",
        "webui": "WebUI assets not yet built",
        "router_api": "/routerapi/health",
        "admin_api": "/api/plugins",
    }
