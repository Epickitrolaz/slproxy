"""
SLProxy Configuration
"""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("SLPROXY_DATA_DIR", BASE_DIR.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "slproxy.db"
PLUGINS_DIR = Path(os.getenv("SLPROXY_PLUGINS_DIR", BASE_DIR / "plugins"))
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR = BASE_DIR / "templates" / "plugins"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Server
HOST = os.getenv("SLPROXY_HOST", "0.0.0.0")
PORT = int(os.getenv("SLPROXY_PORT", "8080"))

# Security & Routing
REQUIRE_API_KEY = os.getenv("SLPROXY_REQUIRE_API_KEY", "false").lower() in ("true", "1", "yes")
ADMIN_PASSWORD = os.getenv("SLPROXY_ADMIN_PASSWORD", "")
DEFAULT_ROUTING_STRATEGY = os.getenv("SLPROXY_DEFAULT_ROUTING_STRATEGY", "fallback")
REQUEST_TIMEOUT = float(os.getenv("SLPROXY_REQUEST_TIMEOUT", "120.0"))
