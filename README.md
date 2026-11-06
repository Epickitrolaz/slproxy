<p align="center">
  <img src="assets/icon.svg" width="80" height="80" alt="SLProxy Logo">
</p>

<h1 align="center">SLProxy</h1>

<p align="center">
  <strong>Intelligent AI Model Router & Dynamic Python Plugin Engine with &lt; 1s Hot Reload</strong>
</p>

<p align="center">
  <a href="#quickstart-with-docker"><img src="https://img.shields.io/badge/docker-ready-0284c7?logo=docker" alt="Docker Ready"></a>
  <a href="#dynamic-python-plugins--1s-hot-reload"><img src="https://img.shields.io/badge/hot--reload-%3C%201s-10b981" alt="Sub-second Hot Reload"></a>
  <a href="#modern-webui-dashboard"><img src="https://img.shields.io/badge/webui-dark--mode-38bdf8" alt="Modern WebUI"></a>
  <a href="#providers-supported-out-of-the-box"><img src="https://img.shields.io/badge/providers-7%20builtin-8b5cf6" alt="7 Builtin Providers"></a>
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="Python 3.12">
</p>

---

## Overview

**SLProxy** is a high-performance local AI model proxy and intelligent router designed for developers, autonomous agents (Cline, Cursor, OpenCode), and teams. It unifies OpenAI and Anthropic API protocols, provides multi-account failover with automated rate-limit cooldowns, and introduces a **browser-editable Python plugin engine with sub-second hot reload**.

### Highlights
- ⚡ **Sub-Second Hot Reload**: Edit Python provider plugins directly in your browser and deploy in `< 1s` without server restarts.
- 🎯 **Dual Protocol Gateway**: Seamlessly converts and routes requests between `/routerapi/v1/chat/completions` (OpenAI format) and `/routerapi/v1/messages` (Anthropic format).
- 🔄 **Intelligent Multi-Account Routing**: Priority failover, weighted round-robin, and automated cooldown backoff upon hitting HTTP 429 or quota exhaustion.
- 🔑 **Granular Router Keys**: Issue local client keys (`slp-live-...`) with token limits, request caps, expiration dates, and model whitelists.
- 🖥️ **Modern Responsive WebUI**: Real-time metrics dashboard, interactive API playground, live log streaming, multi-account manager, and CodeMirror Python editor.
- 🐳 **Containerized & Persistent**: Single-command deployment via Docker & Docker Compose with persistent SQLite volume at `/data`.

---

## Architecture

```
                   ┌────────────────────────────────────────┐
                   │    Clients, IDEs & Autonomous Agents   │
                   │  (Cursor, Cline, OpenCode, curl, apps) │
                   └───────────────────┬────────────────────┘
                                       │ Bearer slp-live-...
                                       ▼
                   ┌────────────────────────────────────────┐
                   │         SLProxy Gateway (:8080)        │
                   │                                        │
                   │   /              -> Modern WebUI       │
                   │   /routerapi/v1  -> AI Router Endpoints│
                   │   /api           -> Admin API          │
                   └───────────────────┬────────────────────┘
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        ▼                                                             ▼
┌────────────────────────────────┐                    ┌────────────────────────────────┐
│   Multi-Account Router Engine  │                    │ Dynamic Python Plugin Loader   │
│                                │                    │                                │
│ • Priority Failover            │◄──────────────────►│ • In-Browser CodeMirror Editor │
│ • Weighted Round-Robin         │                    │ • < 1s Hot Reload              │
│ • Cooldown Backoff (429/quota) │                    │ • Request & Stream Transforms  │
│ • Rate-Limit Auto-Recovery     │                    │ • Quota & Error Interceptors   │
└────────────────┬───────────────┘                    └────────────────┬───────────────┘
                 │                                                     │
                 └───────────────────────┬─────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            Supported Provider Plugins                                │
├───────────────┬───────────────┬───────────────┬──────────────────────┬───────────────┤
│ Google        │ OpenAI        │ Claude Code   │ OpenRouter           │ OpenCode      │
│ Antigravity   │ Codex         │ (Anthropic)   │ (Aggregator)         │ (Code Models) │
├───────────────┼───────────────┼───────────────┼──────────────────────┼───────────────┤
│ Generic OpenAI│ Generic Anthropic                                  │ User Custom   │
│ (Ollama/vLLM) │ (Custom Proxy)                                     │ Plugins (.py) │
└───────────────┴────────────────────────────────────────────────────┴───────────────┘
                                         │
                                         ▼
                   ┌────────────────────────────────────────┐
                   │        Persistent Storage (/data)      │
                   │   SQLite (slproxy.db) & Custom Plugins │
                   └────────────────────────────────────────┘
```

---

## Dynamic Python Plugins & &lt; 1s Hot Reload

The centerpiece of SLProxy is its dynamic plugin architecture. Every provider is a self-contained Python class subclassing `BasePlugin`. You can inspect, modify, and deploy new plugin logic directly from the WebUI.

### How It Works
1. Navigate to the **Plugins & Editor** tab in the WebUI.
2. Select any provider (or click **Create New Plugin**).
3. Edit request transformation logic, custom authentication headers, token counters, or quota detection routines.
4. Click **Save & Deploy**: the Python code is re-compiled and hot-swapped into the running server in memory in **under 1 second** (`< 1s`).
5. All subsequent requests instantly execute the updated Python code—no server downtime or restarts.

### Provider variables and model options

A plugin can declare provider-wide controls with `settings_schema`. The WebUI renders supported types (`string`, `password`, `number`, `integer`, `boolean`, `select`, `textarea`, and `json`), and the saved values are available as `self.settings` or `self.get_setting(...)`. Per-model `options` are editable in the provider model list and arrive on each `ProxyRequest` as `request.metadata["model_options"]`; provider variables are also attached as `request.metadata["provider_settings"]`.

```python
settings_schema = [
    {"key": "api_mode", "label": "API mode", "type": "select", "default": "standard",
     "options": [{"value": "standard", "label": "Standard"}, "compat"]},
    {"key": "send_beta_header", "label": "Enable beta header", "type": "boolean", "default": False},
]

def transform_request(self, request, account):
    mode = request.metadata["provider_settings"].get("api_mode", "standard")
    model_options = request.metadata["model_options"]
    if model_options.get("upstream_model_id"):
        request.body["model"] = model_options["upstream_model_id"]
    if mode == "compat":
        request.headers["X-API-Mode"] = "compat"
    return request
```

Provider variables and model definitions/options are stored in SQLite and applied after plugin reload. Model removal is persisted, including when a provider has zero remaining models.

### Example Plugin: Quota Interceptor & Header Injection
```python
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class CustomAIPlugin(BasePlugin):
    id = "custom_ai"
    name = "Custom AI Engine"
    default_base_url = "https://api.openai.com/v1"
    format = "openai"

    models = [
        ModelInfo(id="custom-fast", name="Custom Fast", context_window=128000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        """Inject customized auth and routing headers"""
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        request.headers["X-Client-Agent"] = "SLProxy/1.0"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        """Detect rate limits and trigger instant multi-account failover"""
        if response.status_code == 429 or "quota_exceeded" in response.raw_text:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="Quota exceeded, activating failover cooldown"
            )
        return ErrorCheckResult(is_error=False)
```

---

## Providers Supported Out of the Box

| Provider | Plugin ID | Protocol | Key Models | Special Capabilities |
|:---|:---|:---|:---|:---|
| **Google Antigravity** | `google_antigravity` | Antigravity (Cloud Code) | `gemini-3.8-flash-high`, `gemini-3.8-flash-medium`, `gemini-3.8-flash-low`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium` | Wire-compatible with the official `agy` CLI (`v1internal:streamGenerateContent`), `RESOURCE_EXHAUSTED` quota failover |
| **OpenAI Codex** | `codex` | OpenAI | `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini` | Reasoning model parameters, tool calls, multi-tier key balancing |
| **Claude Code** | `claude` | Anthropic | `claude-3-5-sonnet`, `claude-3-5-haiku`, `claude-3-opus` | Anthropic Messages format, SSE streaming event transformers |
| **OpenRouter** | `openrouter` | OpenAI | `deepseek/deepseek-r1`, `meta-llama/llama-3.3-70b` | Universal gateway aggregator routing |
| **OpenCode** | `opencode` | OpenAI | `opencode-base`, `opencode-instruct` | Optimized for IDE code completion and code intelligence |
| **OpenAI Compatible** | `openai_generic`| OpenAI | `llama3`, `deepseek-chat`, custom models | Connects to Ollama, vLLM, LocalAI, Groq, Mistral |
| **Anthropic Compatible**| `anthropic_generic`| Anthropic | `claude-3-haiku-compatible` | Connects to third-party Anthropic-compatible proxies |

---

## Multi-Account Routing Strategies

SLProxy eliminates rate limits and service interruptions by managing multiple accounts per provider.

- **Priority Fallback (Default)**:
  Accounts are evaluated by their configured priority rank (`1` = highest priority). If an account receives an HTTP 429 or quota error, SLProxy marks it as **Rate-Limited** with a cooldown timer (e.g. 60 seconds) and immediately fails over to the next priority account. Once the cooldown expires, the account is automatically returned to the active pool.
- **Weighted Round-Robin**:
  Requests are distributed across all active, non-rate-limited accounts proportional to their assigned weight (e.g. Account A with weight 20 gets 2x the requests of Account B with weight 10).
- **Manual Cooldown Reset**:
  Reset rate-limit cooldowns instantly via the WebUI or API with a single click.

---

## Local API Key Security & Limits

Secure client access to `/routerapi` using local API keys:
- **Prefix format**: `slp-live-...` (shown once upon creation).
- **Limits**: Configurable maximum request caps and maximum token caps.
- **Expiration**: Optional TTL presets (7 days, 30 days, 90 days, or permanent).
- **Model Whitelists**: Restrict keys to specific providers or models.

---

## Modern WebUI Dashboard

The WebUI is served at `http://localhost:8080/` with a dark-mode first design:

1. **Dashboard**: Live request counter, success rate %, total tokens, active providers, latency distribution bars, and provider health overview.
2. **Plugins & Editor**: List of installed provider plugins with models, and the in-browser CodeMirror Python editor with instant "Save & Deploy".
3. **Accounts**: Multi-account management per provider with priority, weight, masked keys, and live cooldown countdowns with reset buttons.
4. **Router Keys**: Client key generator with usage progress bars (requests/tokens used vs max) and revoke buttons.
5. **Live Logs**: Real-time telemetry stream showing timestamps, endpoints, status codes, latency, token consumption, and error logs.
6. **Playground**: Test `/routerapi/v1/chat/completions` directly from your browser with streaming SSE display, temperature controls, and a "Copy cURL" button.
7. **Settings**: Switch routing strategies, export/import JSON configurations, and view system specifications.

---

## Quickstart with Docker

### Using Docker Compose (Recommended)

`docker-compose.yml` pulls the prebuilt image from GHCR, so no local build is needed:

1. Clone the repository and start the container:
```bash
git clone https://github.com/Epickitrolaz/slproxy.git
cd slproxy
docker compose up -d
```

To build the image locally instead of using the published image:

```bash
docker compose up -d --build
```

2. Open the WebUI in your browser:
```
http://localhost:8080
```

### Using Docker CLI

```bash
# Pull and run the prebuilt image with persistent data volume
docker run -d \
  --name slproxy \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  ghcr.io/epickitrolaz/slproxy:latest
```

Alternative tags: `:latest` (current main), `:1.2.3` / `:1.2` (release versions), `:sha-<commit>` (per-commit builds). Multi-arch images are built for `linux/amd64` and `linux/arm64`.

> **Image availability note:** the GHCR package is private on first publish — after the first CI run, flip `ghcr.io/epickitrolaz/slproxy` to public under *GitHub → Packages → slproxy → Package settings → Change visibility*. Until then, `docker pull` from ghcr requires `docker login ghcr.io` with a GitHub token that has `read:packages`.

---

## Quickstart with Local Python

1. Ensure Python 3.12+ is installed:
```bash
python3 --version
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Launch SLProxy server:
```bash
uvicorn slproxy.main:app --host 0.0.0.0 --port 8080
```

4. Access the WebUI at `http://localhost:8080`.

---

## Example cURL Requests

### 1. OpenAI Chat Completions Format (`/routerapi/v1/chat/completions`)

```bash
curl -X POST http://localhost:8080/routerapi/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer slp-live-cursor-e9182ab47c8d901f" \
  -d '{
    "model": "gemini-3.8-flash-high",
    "messages": [
      {"role": "system", "content": "You are a helpful coding assistant."},
      {"role": "user", "content": "Write a Python function to calculate fibonacci numbers."}
    ],
    "temperature": 0.7,
    "stream": false
  }'
```

### 2. Anthropic Messages Format (`/routerapi/v1/messages`)

```bash
curl -X POST http://localhost:8080/routerapi/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: slp-live-cline-7729fbd38104ce2a" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Explain quantum entanglement in simple terms."}
    ]
  }'
```

### 3. List Available Models (`/routerapi/v1/models`)

```bash
curl -X GET http://localhost:8080/routerapi/v1/models \
  -H "Authorization: Bearer slp-live-cursor-e9182ab47c8d901f"
```

### 4. Health Check

```bash
curl -X GET http://localhost:8080/routerapi/health
```

---

## Environment Variables

| Variable | Default | Description |
|:---|:---|:---|
| `SLPROXY_HOST` | `0.0.0.0` | Host interface for server binding |
| `SLPROXY_PORT` | `8080` | Port for WebUI and Router APIs |
| `SLPROXY_DATA_DIR` | `/data` (or `./data`) | Directory for persistent SQLite database and user plugins |
| `SLPROXY_DEFAULT_ROUTING_STRATEGY` | `fallback` | Default routing strategy (`fallback` or `round_robin`) |
| `SLPROXY_REQUIRE_API_KEY` | `false` | Whether client requests to `/routerapi` require router API key |
| `SLPROXY_ADMIN_PASSWORD` | `""` | Optional admin password for WebUI access |
| `SLPROXY_REQUEST_TIMEOUT` | `120.0` | Upstream provider request timeout in seconds |

---

## License

MIT License. Built for seamless AI model routing and dynamic plugin development.
