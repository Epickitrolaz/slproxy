"""
SLProxy Main Application
Mounts WebUI on / and local router APIs on /routerapi
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from slproxy.api.router_api import router as router_api
from slproxy.api.admin_api import router as admin_api
from slproxy.config import BASE_DIR

app = FastAPI(
    title="SLProxy",
    description="Flexible AI Model Router with dynamic Python plugins",
    version="1.0.0"
)

# Include routers
app.include_router(router_api)
app.include_router(admin_api)

# Static WebUI mounting
web_dir = BASE_DIR / "web"
web_dir.mkdir(parents=True, exist_ok=True)

if (web_dir / "index.html").exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/")
    async def serve_webui():
        return FileResponse(web_dir / "index.html")
else:
    @app.get("/")
    async def root_fallback():
        return {
            "message": "SLProxy is running.",
            "webui": "WebUI assets not yet built",
            "router_api": "/routerapi/health"
        }
