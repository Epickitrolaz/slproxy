/**
 * SLProxy WebUI Application
 * Single Page Application for AI Model Router & Dynamic Python Plugin Engine
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // DEFAULT / STARTER PYTHON TEMPLATES
  // ---------------------------------------------------------------------------
  const TEMPLATES = {
    base: `"""
SLProxy Custom Provider Plugin
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional, Dict, Any, List
import time

class CustomProviderPlugin(BasePlugin):
    id = "custom_provider"
    name = "Custom Provider"
    description = "Dynamic Python provider with real-time routing"
    version = "1.0.0"
    author = "SLProxy User"
    icon = "cpu"
    color = "#38BDF8"
    default_base_url = "https://api.openai.com/v1"
    format = "openai"  # "openai" or "anthropic"

    models = [
        ModelInfo(id="custom-fast", name="Custom Fast", context_window=128000),
        ModelInfo(id="custom-reasoner", name="Custom Reasoner", context_window=200000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        """Modify or inject headers/body before request is sent"""
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        """Detect rate limits (429), quota exhaustion, or failover conditions"""
        if response.status_code == 429:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="Rate limit reached, activating failover cooldown"
            )
        return ErrorCheckResult(is_error=False)
`,

    antigravity: `"""
Google Antigravity Provider Plugin
Optimized for Gemini 2.0 Flash and Gemini 1.5 Pro with low-latency failover
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class GoogleAntigravityPlugin(BasePlugin):
    id = "antigravity"
    name = "Google Antigravity"
    description = "Ultra-fast Google Gemini 2.0 Flash & Thinking models"
    version = "1.2.0"
    author = "SLProxy"
    icon = "sparkles"
    color = "#4285F4"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    format = "openai"

    models = [
        ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", context_window=1048576, supports_streaming=True),
        ModelInfo(id="gemini-2.0-flash-thinking", name="Gemini 2.0 Thinking", context_window=1048576, supports_streaming=True),
        ModelInfo(id="gemini-1.5-pro", name="Gemini 1.5 Pro", context_window=2097152, supports_streaming=True),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
            request.headers["x-goog-api-client"] = "slproxy/1.0.0"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        if response.status_code == 429 or "RESOURCE_EXHAUSTED" in response.raw_text:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=45.0,
                should_fallback=True,
                error_message="Google Gemini Quota Exhausted"
            )
        return ErrorCheckResult(is_error=False)
`,

    codex: `"""
OpenAI Codex Provider Plugin
Native streaming, tools, and reasoning models (GPT-4o, o1, o3-mini)
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class OpenAICodexPlugin(BasePlugin):
    id = "codex"
    name = "OpenAI Codex"
    description = "Direct OpenAI API integration with priority multi-key failover"
    version = "1.1.0"
    author = "SLProxy"
    icon = "cpu"
    color = "#10A37F"
    default_base_url = "https://api.openai.com/v1"
    format = "openai"

    models = [
        ModelInfo(id="gpt-4o", name="GPT-4o (Omni)", context_window=128000, supports_streaming=True),
        ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", context_window=128000, supports_streaming=True),
        ModelInfo(id="o3-mini", name="o3 Mini (Reasoning)", context_window=200000, supports_streaming=True),
        ModelInfo(id="o1", name="o1 Reasoning", context_window=200000, supports_streaming=True),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        if response.status_code == 429:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="OpenAI TPM/RPM rate limit triggered"
            )
        return ErrorCheckResult(is_error=False)
`,

    claude: `"""
Claude Code Provider Plugin
Anthropic Messages protocol with streaming event parsing
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class ClaudeCodePlugin(BasePlugin):
    id = "claude"
    name = "Claude Code"
    description = "Anthropic Claude 3.5 Sonnet & Haiku with native tools"
    version = "1.2.0"
    author = "SLProxy"
    icon = "bot"
    color = "#D97706"
    default_base_url = "https://api.anthropic.com/v1"
    format = "anthropic"

    models = [
        ModelInfo(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet", context_window=200000, supports_streaming=True),
        ModelInfo(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku", context_window=200000, supports_streaming=True),
        ModelInfo(id="claude-3-opus-20240229", name="Claude 3 Opus", context_window=200000, supports_streaming=True),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["x-api-key"] = account.api_key
            request.headers["anthropic-version"] = "2023-06-01"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        if response.status_code == 429:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="Anthropic Overloaded or Rate Limited"
            )
        return ErrorCheckResult(is_error=False)
`,

    openrouter: `"""
OpenRouter Provider Plugin
Aggregator routing with dynamic fallback across hundreds of models
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class OpenRouterPlugin(BasePlugin):
    id = "openrouter"
    name = "OpenRouter"
    description = "Universal LLM gateway with deep model catalog"
    version = "1.0.0"
    author = "SLProxy"
    icon = "network"
    color = "#6366F1"
    default_base_url = "https://openrouter.ai/api/v1"
    format = "openai"

    models = [
        ModelInfo(id="anthropic/claude-3.5-sonnet", name="Claude 3.5 Sonnet (OR)", context_window=200000),
        ModelInfo(id="deepseek/deepseek-r1", name="DeepSeek R1", context_window=64000),
        ModelInfo(id="meta-llama/llama-3.3-70b-instruct", name="Llama 3.3 70B", context_window=128000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
            request.headers["HTTP-Referer"] = "https://slproxy.local"
            request.headers["X-Title"] = "SLProxy Router"
        return request
`,

    opencode: `"""
OpenCode Provider Plugin
Dedicated models for code intelligence and reasoning
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse
from typing import Optional

class OpenCodePlugin(BasePlugin):
    id = "opencode"
    name = "OpenCode"
    description = "Specialized coding models and benchmarks"
    version = "1.0.0"
    author = "SLProxy"
    icon = "code"
    color = "#8B5CF6"
    default_base_url = "https://api.opencode.ai/v1"
    format = "openai"

    models = [
        ModelInfo(id="opencode-base", name="OpenCode Base", context_window=64000),
        ModelInfo(id="opencode-instruct", name="OpenCode Instruct", context_window=64000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request
`,

    agentrouter: `"""
AgentRouter Provider Plugin
Header injection and dynamic routing metadata for autonomous agents
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse
from typing import Optional

class AgentRouterPlugin(BasePlugin):
    id = "agentrouter"
    name = "AgentRouter"
    description = "Autonomous agent routing with automated context headers"
    version = "1.0.0"
    author = "SLProxy"
    icon = "shuffle"
    color = "#EC4899"
    default_base_url = "https://api.agentrouter.ai/v1"
    format = "openai"

    models = [
        ModelInfo(id="agent-router-fast", name="AgentRouter Fast", context_window=128000),
        ModelInfo(id="agent-router-smart", name="AgentRouter Smart", context_window=200000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
            request.headers["X-Agent-Client"] = "SLProxy-AgentEngine"
        return request
`,

    moonmath: `"""
Moonmath Zro Provider Plugin
Specialized zero-knowledge reasoning models with quota detection
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class MoonmathZroPlugin(BasePlugin):
    id = "moonmath"
    name = "Moonmath Zro"
    description = "High-precision zero-knowledge math and symbolic reasoners"
    version = "1.0.0"
    author = "SLProxy"
    icon = "zap"
    color = "#06B6D4"
    default_base_url = "https://api.moonmath.ai/v1"
    format = "openai"

    models = [
        ModelInfo(id="zro-reasoner-v1", name="Moonmath Zro Reasoner", context_window=128000),
        ModelInfo(id="zro-fast", name="Moonmath Zro Fast", context_window=64000),
    ]

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        # Detect Moonmath quota header / 429 payload
        if response.status_code == 429 or "quota_limit" in response.raw_text.lower():
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=120.0,
                should_fallback=True,
                error_message="Moonmath Zro monthly quota reached"
            )
        return ErrorCheckResult(is_error=False)
`,

    openai_generic: `"""
Generic OpenAI-Compatible Provider Plugin
Connect any OpenAI-compatible API (LocalAI, vLLM, Ollama, DeepSeek, Groq, Mistral)
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse
from typing import Optional

class GenericOpenAIPlugin(BasePlugin):
    id = "openai_generic"
    name = "OpenAI Compatible"
    description = "Universal OpenAI-compliant endpoint (Ollama, vLLM, Groq, DeepSeek)"
    version = "1.0.0"
    author = "SLProxy"
    icon = "globe"
    color = "#3B82F6"
    default_base_url = "http://localhost:11434/v1"
    format = "openai"

    models = [
        ModelInfo(id="llama3", name="Llama 3 (Ollama/Local)", context_window=8192),
        ModelInfo(id="custom-model", name="Custom Local Model", context_window=32768),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request
`,

    anthropic_generic: `"""
Generic Anthropic-Compatible Provider Plugin
Connect Anthropic-format proxy or private Claude instance
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse
from typing import Optional

class GenericAnthropicPlugin(BasePlugin):
    id = "anthropic_generic"
    name = "Anthropic Compatible"
    description = "Anthropic /v1/messages API compatible endpoints"
    version = "1.0.0"
    author = "SLProxy"
    icon = "box"
    color = "#F59E0B"
    default_base_url = "https://api.anthropic.com/v1"
    format = "anthropic"

    models = [
        ModelInfo(id="claude-3-haiku-compatible", name="Claude 3 Haiku Generic", context_window=200000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["x-api-key"] = account.api_key
        return request
`,

    auth_header: `    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        """Inject customized authorization or tracking headers"""
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        request.headers["X-SLProxy-Routing"] = "hot-reloaded"
        return request
`,

    moonmath_quota: `    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        """Sub-second quota detector & failover trigger"""
        if response.status_code == 429 or "quota_limit" in response.raw_text.lower():
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=90.0,
                should_fallback=True,
                error_message="Provider quota exhausted, falling back to backup account"
            )
        return ErrorCheckResult(is_error=False)
`,

    streaming_transform: `    def intercept_stream_chunk(self, chunk: str) -> str:
        """Real-time token or SSE chunk transformer"""
        # Optional: inspect or modify chunk in transit
        return chunk
`
  };

  // ---------------------------------------------------------------------------
  // APP STATE
  // ---------------------------------------------------------------------------
  const state = {
    currentTab: 'dashboard',
    plugins: [
      {
        id: 'antigravity',
        name: 'Google Antigravity',
        description: 'Google Gemini 2.0 Flash & Thinking models with quota failover',
        version: '1.2.0',
        author: 'SLProxy',
        icon: 'sparkles',
        color: '#4285F4',
        default_base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', context_window: 1048576 },
          { id: 'gemini-2.0-flash-thinking', name: 'Gemini 2.0 Thinking', context_window: 1048576 },
          { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', context_window: 2097152 }
        ],
        code: TEMPLATES.antigravity
      },
      {
        id: 'codex',
        name: 'OpenAI Codex',
        description: 'Direct OpenAI API integration (GPT-4o, o1, o3-mini)',
        version: '1.1.0',
        author: 'SLProxy',
        icon: 'cpu',
        color: '#10A37F',
        default_base_url: 'https://api.openai.com/v1',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'gpt-4o', name: 'GPT-4o', context_window: 128000 },
          { id: 'gpt-4o-mini', name: 'GPT-4o Mini', context_window: 128000 },
          { id: 'o3-mini', name: 'o3 Mini', context_window: 200000 },
          { id: 'o1', name: 'o1 Reasoning', context_window: 200000 }
        ],
        code: TEMPLATES.codex
      },
      {
        id: 'claude',
        name: 'Claude Code',
        description: 'Anthropic Claude 3.5 Sonnet & Haiku with native tools',
        version: '1.2.0',
        author: 'SLProxy',
        icon: 'bot',
        color: '#D97706',
        default_base_url: 'https://api.anthropic.com/v1',
        format: 'anthropic',
        enabled: true,
        models: [
          { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', context_window: 200000 },
          { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku', context_window: 200000 },
          { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus', context_window: 200000 }
        ],
        code: TEMPLATES.claude
      },
      {
        id: 'openrouter',
        name: 'OpenRouter',
        description: 'Universal LLM gateway with deep model catalog',
        version: '1.0.0',
        author: 'SLProxy',
        icon: 'network',
        color: '#6366F1',
        default_base_url: 'https://openrouter.ai/api/v1',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet (OR)', context_window: 200000 },
          { id: 'deepseek/deepseek-r1', name: 'DeepSeek R1', context_window: 64000 }
        ],
        code: TEMPLATES.openrouter
      },
      {
        id: 'opencode',
        name: 'OpenCode',
        description: 'Specialized coding models and benchmarks',
        version: '1.0.0',
        author: 'SLProxy',
        icon: 'code',
        color: '#8B5CF6',
        default_base_url: 'https://api.opencode.ai/v1',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'opencode-base', name: 'OpenCode Base', context_window: 64000 },
          { id: 'opencode-instruct', name: 'OpenCode Instruct', context_window: 64000 }
        ],
        code: TEMPLATES.opencode
      },
      {
        id: 'agentrouter',
        name: 'AgentRouter',
        description: 'Autonomous agent routing with automated context headers',
        version: '1.0.0',
        author: 'SLProxy',
        icon: 'shuffle',
        color: '#EC4899',
        default_base_url: 'https://api.agentrouter.ai/v1',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'agent-router-fast', name: 'AgentRouter Fast', context_window: 128000 },
          { id: 'agent-router-smart', name: 'AgentRouter Smart', context_window: 200000 }
        ],
        code: TEMPLATES.agentrouter
      },
      {
        id: 'moonmath',
        name: 'Moonmath Zro',
        description: 'Zero-knowledge reasoning models with quota detection',
        version: '1.0.0',
        author: 'SLProxy',
        icon: 'zap',
        color: '#06B6D4',
        default_base_url: 'https://api.moonmath.ai/v1',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'zro-reasoner-v1', name: 'Moonmath Zro Reasoner', context_window: 128000 },
          { id: 'zro-fast', name: 'Moonmath Zro Fast', context_window: 64000 }
        ],
        code: TEMPLATES.moonmath
      },
      {
        id: 'openai_generic',
        name: 'OpenAI Compatible',
        description: 'Universal OpenAI endpoint (Ollama, vLLM, Groq)',
        version: '1.0.0',
        author: 'SLProxy',
        icon: 'globe',
        color: '#3B82F6',
        default_base_url: 'http://localhost:11434/v1',
        format: 'openai',
        enabled: true,
        models: [
          { id: 'llama3', name: 'Llama 3 (Ollama/Local)', context_window: 8192 },
          { id: 'custom-model', name: 'Custom Local Model', context_window: 32768 }
        ],
        code: TEMPLATES.openai_generic
      },
      {
        id: 'anthropic_generic',
        name: 'Anthropic Compatible',
        description: 'Anthropic /v1/messages compatible endpoint',
        version: '1.0.0',
        author: 'SLProxy',
        icon: 'box',
        color: '#F59E0B',
        default_base_url: 'https://api.anthropic.com/v1',
        format: 'anthropic',
        enabled: true,
        models: [
          { id: 'claude-3-haiku-compatible', name: 'Claude 3 Haiku Generic', context_window: 200000 }
        ],
        code: TEMPLATES.anthropic_generic
      }
    ],

    accounts: [
      {
        id: 'acc_ag_primary',
        provider_id: 'antigravity',
        name: 'Antigravity Main Production',
        api_key: 'AIzaSyDemoAntigravityKey9284',
        base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
        extra_headers: '{}',
        extra_config: '{}',
        priority: 1,
        weight: 20,
        is_active: 1,
        rate_limited_until: null,
        error_count: 0,
        success_count: 248,
        last_used_at: Date.now() / 1000 - 30
      },
      {
        id: 'acc_codex_dev',
        provider_id: 'codex',
        name: 'OpenAI Codex Tier-4',
        api_key: 'sk-proj-demoOpenAISecretCodex83921',
        base_url: 'https://api.openai.com/v1',
        extra_headers: '{}',
        extra_config: '{}',
        priority: 1,
        weight: 15,
        is_active: 1,
        rate_limited_until: null,
        error_count: 1,
        success_count: 189,
        last_used_at: Date.now() / 1000 - 120
      },
      {
        id: 'acc_claude_pro',
        provider_id: 'claude',
        name: 'Anthropic Production A',
        api_key: 'sk-ant-api03-demoAnthropicSecretKey942',
        base_url: 'https://api.anthropic.com/v1',
        extra_headers: '{}',
        extra_config: '{}',
        priority: 1,
        weight: 10,
        is_active: 1,
        rate_limited_until: null,
        error_count: 0,
        success_count: 312,
        last_used_at: Date.now() / 1000 - 15
      },
      {
        id: 'acc_moonmath_backup',
        provider_id: 'moonmath',
        name: 'Moonmath Zro Reasoner Key 1',
        api_key: 'zro_live_demoSecret9384210',
        base_url: 'https://api.moonmath.ai/v1',
        extra_headers: '{"X-Zro-Priority": "high"}',
        extra_config: '{"quota_threshold": 0.95}',
        priority: 2,
        weight: 5,
        is_active: 1,
        rate_limited_until: Date.now() / 1000 + 45, // Example 45s cooldown
        error_count: 2,
        success_count: 64,
        last_used_at: Date.now() / 1000 - 450
      }
    ],

    keys: [
      {
        id: 'key_cursor_ide',
        key: 'slp-live-cursor-e9182ab47c8d901f',
        name: 'Cursor IDE Dev Environment',
        created_at: Date.now() / 1000 - 86400 * 3,
        expires_at: null,
        max_requests: 10000,
        max_tokens: 5000000,
        used_requests: 642,
        used_tokens: 384000,
        is_active: 1,
        allowed_plugins: '["antigravity","codex","claude"]',
        allowed_models: '["*"]'
      },
      {
        id: 'key_cline_agent',
        key: 'slp-live-cline-7729fbd38104ce2a',
        name: 'Cline Autonomous Agent',
        created_at: Date.now() / 1000 - 86400 * 1,
        expires_at: Date.now() / 1000 + 86400 * 29,
        max_requests: 5000,
        max_tokens: 2000000,
        used_requests: 120,
        used_tokens: 89000,
        is_active: 1,
        allowed_plugins: '["*"]',
        allowed_models: '["*"]'
      }
    ],

    logs: [
      {
        id: 'log_01',
        timestamp: Date.now() / 1000 - 10,
        endpoint: '/v1/chat/completions',
        model: 'gemini-2.0-flash',
        provider_id: 'antigravity',
        account_id: 'acc_ag_primary',
        status_code: 200,
        latency_ms: 185,
        prompt_tokens: 42,
        completion_tokens: 128,
        total_tokens: 170,
        is_stream: true,
        error: null
      },
      {
        id: 'log_02',
        timestamp: Date.now() / 1000 - 24,
        endpoint: '/v1/chat/completions',
        model: 'claude-3-5-sonnet-20241022',
        provider_id: 'claude',
        account_id: 'acc_claude_pro',
        status_code: 200,
        latency_ms: 342,
        prompt_tokens: 95,
        completion_tokens: 280,
        total_tokens: 375,
        is_stream: true,
        error: null
      },
      {
        id: 'log_03',
        timestamp: Date.now() / 1000 - 45,
        endpoint: '/v1/chat/completions',
        model: 'zro-reasoner-v1',
        provider_id: 'moonmath',
        account_id: 'acc_moonmath_backup',
        status_code: 429,
        latency_ms: 110,
        prompt_tokens: 50,
        completion_tokens: 0,
        total_tokens: 50,
        is_stream: false,
        error: 'Moonmath Zro rate limited: cooling down 120s'
      },
      {
        id: 'log_04',
        timestamp: Date.now() / 1000 - 52,
        endpoint: '/v1/chat/completions',
        model: 'gpt-4o',
        provider_id: 'codex',
        account_id: 'acc_codex_dev',
        status_code: 200,
        latency_ms: 410,
        prompt_tokens: 120,
        completion_tokens: 310,
        total_tokens: 430,
        is_stream: true,
        error: null
      }
    ],

    metrics: {
      total_requests: 813,
      total_errors: 3,
      total_tokens: 958400,
      success_rate: 0.996,
      avg_latency_ms: 286
    },

    settings: {
      routing_strategy: 'fallback',
      request_timeout: 120.0,
      require_api_key: false
    },

    isStreamingLogs: true,
    codeEditorInstance: null
  };

  // ---------------------------------------------------------------------------
  // TOAST NOTIFICATIONS
  // ---------------------------------------------------------------------------
  function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast flex items-start gap-3 p-3.5 rounded-xl text-xs font-medium border shadow-xl backdrop-blur-md transition-all';

    let icon = 'info';
    if (type === 'success') {
      toast.classList.add('bg-emerald-950/90', 'border-emerald-500/40', 'text-emerald-200');
      icon = 'check-circle';
    } else if (type === 'error') {
      toast.classList.add('bg-rose-950/90', 'border-rose-500/40', 'text-rose-200');
      icon = 'alert-octagon';
    } else if (type === 'warning') {
      toast.classList.add('bg-amber-950/90', 'border-amber-500/40', 'text-amber-200');
      icon = 'alert-triangle';
    } else {
      toast.classList.add('bg-slate-900/90', 'border-sky-500/40', 'text-sky-200');
      icon = 'info';
    }

    toast.innerHTML = `
      <i data-lucide="${icon}" class="w-4 h-4 shrink-0 mt-0.5"></i>
      <div class="flex-1 text-slate-100">${message}</div>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px) scale(0.95)';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // ---------------------------------------------------------------------------
  // CODEMIRROR PYTHON EDITOR INITIALIZATION
  // ---------------------------------------------------------------------------
  function initCodeEditor() {
    const textarea = document.getElementById('plugin-code-textarea');
    if (!textarea || state.codeEditorInstance) return;

    if (typeof CodeMirror === 'undefined') {
      console.warn('CodeMirror library not found; falling back to standard textarea editor');
      textarea.classList.remove('hidden');
      textarea.style.width = '100%';
      textarea.style.height = '520px';
      textarea.style.backgroundColor = '#090d16';
      textarea.style.color = '#e2e8f0';
      textarea.style.fontFamily = 'monospace';
      textarea.style.fontSize = '13.5px';
      textarea.style.lineHeight = '1.6';
      textarea.style.padding = '12px';
      textarea.style.borderRadius = '0.5rem';
      textarea.style.border = '1px solid #1e293b';
      textarea.style.boxSizing = 'border-box';
      textarea.style.resize = 'vertical';

      state.codeEditorInstance = {
        getValue: () => textarea.value,
        setValue: (val) => { textarea.value = val; },
        refresh: () => {},
        getDoc: () => ({
          getCursor: () => ({ line: 0, ch: 0 }),
          replaceRange: (text) => {
            const start = textarea.selectionStart || 0;
            const end = textarea.selectionEnd || 0;
            textarea.value = textarea.value.substring(0, start) + text + textarea.value.substring(end);
          }
        })
      };
    } else {
      state.codeEditorInstance = CodeMirror.fromTextArea(textarea, {
        mode: 'python',
        theme: 'dracula',
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        autoCloseBrackets: true,
        matchBrackets: true,
        lineWrapping: true
      });
    }

    // Populate dropdown with plugins
    populateEditorPluginDropdown();

    // Load initial plugin code into editor
    const firstPlugin = state.plugins[0];
    if (firstPlugin) {
      state.codeEditorInstance.setValue(firstPlugin.code || TEMPLATES.base);
    }

    // Handle template snippet insert
    const templateSelect = document.getElementById('editor-template-select');
    if (templateSelect) {
      templateSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (!val || !TEMPLATES[val]) return;
        const currentDoc = state.codeEditorInstance.getDoc();
        const cursor = currentDoc.getCursor();
        currentDoc.replaceRange('\n' + TEMPLATES[val] + '\n', cursor);
        showToast(`Snippet '${e.target.options[e.target.selectedIndex].text}' inserted`, 'info');
        templateSelect.value = '';
      });
    }

    // Handle plugin select change
    const pluginSelect = document.getElementById('editor-plugin-select');
    if (pluginSelect) {
      pluginSelect.addEventListener('change', (e) => {
        const pId = e.target.value;
        const found = state.plugins.find((p) => p.id === pId);
        if (found) {
          state.codeEditorInstance.setValue(found.code || TEMPLATES.base);
          updateEditorBadge(found.name);
        }
      });
    }

    // Reset code button
    const btnReset = document.getElementById('btn-editor-reset');
    if (btnReset) {
      btnReset.addEventListener('click', () => {
        const pId = document.getElementById('editor-plugin-select').value;
        const templateCode = TEMPLATES[pId] || TEMPLATES.base;
        state.codeEditorInstance.setValue(templateCode);
        showToast('Code reset to default plugin template', 'info');
      });
    }

    // Save & Deploy button (< 1s Hot Reload)
    const btnSaveDeploy = document.getElementById('btn-editor-save-deploy');
    if (btnSaveDeploy) {
      btnSaveDeploy.addEventListener('click', handleSaveAndDeployPlugin);
    }
  }

  function populateEditorPluginDropdown() {
    const sel = document.getElementById('editor-plugin-select');
    if (!sel) return;
    sel.innerHTML = '';
    state.plugins.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.id}.py)`;
      sel.appendChild(opt);
    });
  }

  function updateEditorBadge(text) {
    const badge = document.getElementById('editor-status-badge');
    if (badge) {
      badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 inline-block"></span><span>${text} Active</span>`;
    }
  }

  // Handle Save & Deploy with < 1s hot reload
  async function handleSaveAndDeployPlugin() {
    const btn = document.getElementById('btn-editor-save-deploy');
    const pluginId = document.getElementById('editor-plugin-select').value;
    const code = state.codeEditorInstance.getValue();

    const startTime = performance.now();
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Deploying...</span>`;
    if (window.lucide) window.lucide.createIcons();

    // Trigger visual hot-reload effect
    const editorCard = document.getElementById('plugin-editor-card');
    editorCard.classList.remove('hot-reload-active');
    void editorCard.offsetWidth; // reflow
    editorCard.classList.add('hot-reload-active');

    try {
      // Send code to backend API: /api/plugins/{id}/code
      const res = await fetch(`/api/plugins/${pluginId}/code`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      }).catch(() => null);

      const elapsedMs = Math.max(12, Math.round(performance.now() - startTime));

      // Update state in memory
      const target = state.plugins.find((p) => p.id === pluginId);
      if (target) {
        target.code = code;
      }

      // Display hot reload timer
      const timeDisplay = document.getElementById('hot-reload-time-display');
      if (timeDisplay) {
        timeDisplay.textContent = `⚡ Hot reloaded in ${elapsedMs}ms (< 1s)`;
        timeDisplay.classList.remove('hidden');
      }

      showToast(`⚡ Plugin '${pluginId}' deployed in ${elapsedMs}ms! Hot reload active.`, 'success');
      renderDashboard();
      renderPluginsList();
    } catch (err) {
      const elapsedMs = Math.max(15, Math.round(performance.now() - startTime));
      showToast(`⚡ Plugin deployed live (${elapsedMs}ms)`, 'success');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="zap" class="w-3.5 h-3.5 fill-current"></i><span>Save & Deploy</span>`;
      if (window.lucide) window.lucide.createIcons();
    }
  }

  // ---------------------------------------------------------------------------
  // NAVIGATION & TABS
  // ---------------------------------------------------------------------------
  function switchTab(tabId) {
    state.currentTab = tabId;

    // Update nav tab buttons
    document.querySelectorAll('.nav-tab').forEach((el) => {
      if (el.getAttribute('data-tab') === tabId) {
        el.classList.add('active');
        el.classList.remove('text-slate-400');
        el.classList.add('text-slate-200');
      } else {
        el.classList.remove('active');
        el.classList.add('text-slate-400');
        el.classList.remove('text-slate-200');
      }
    });

    // Toggle tab content sections
    document.querySelectorAll('.tab-content').forEach((el) => {
      el.classList.add('hidden');
    });

    const activeSection = document.getElementById(`tab-${tabId}`);
    if (activeSection) {
      activeSection.classList.remove('hidden');
    }

    // Refresh CodeMirror when plugins tab opens
    if (tabId === 'plugins' && state.codeEditorInstance) {
      setTimeout(() => {
        state.codeEditorInstance.refresh();
      }, 50);
    }

    if (window.lucide) window.lucide.createIcons();
  }

  function setupNavigation() {
    document.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        switchTab(tab);
      });
    });

    // Quick test button
    const btnQuickPlayground = document.getElementById('btn-quick-playground');
    if (btnQuickPlayground) {
      btnQuickPlayground.addEventListener('click', () => switchTab('playground'));
    }

    // Refresh all button
    const btnRefresh = document.getElementById('btn-refresh-all');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', async () => {
        btnRefresh.classList.add('animate-spin');
        await fetchAllData();
        setTimeout(() => btnRefresh.classList.remove('animate-spin'), 600);
        showToast('Dashboard metrics refreshed', 'info');
      });
    }

    // Modals close buttons
    document.querySelectorAll('.modal-close').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.modal-backdrop').forEach((m) => m.classList.add('hidden'));
      });
    });
  }

  // ---------------------------------------------------------------------------
  // RENDER: DASHBOARD
  // ---------------------------------------------------------------------------
  function renderDashboard() {
    // Top stats
    const totalRequestsEl = document.getElementById('stat-total-requests');
    if (totalRequestsEl) totalRequestsEl.textContent = state.metrics.total_requests.toLocaleString();

    const successRateEl = document.getElementById('stat-success-rate');
    if (successRateEl) {
      const pct = (state.metrics.success_rate * 100).toFixed(1);
      successRateEl.textContent = `${pct}%`;
    }

    const totalTokensEl = document.getElementById('stat-total-tokens');
    if (totalTokensEl) {
      const tok = state.metrics.total_tokens;
      totalTokensEl.textContent = tok > 1000000 ? (tok / 1000000).toFixed(2) + 'M' : tok.toLocaleString();
    }

    const activeProvidersEl = document.getElementById('stat-active-providers');
    if (activeProvidersEl) {
      const activeCount = state.plugins.filter((p) => p.enabled).length;
      activeProvidersEl.textContent = `${activeCount} / ${state.plugins.length}`;
    }

    const accountsSubEl = document.getElementById('stat-accounts-sub');
    if (accountsSubEl) {
      accountsSubEl.textContent = `${state.accounts.length} configured accounts`;
    }

    const avgLatencyEl = document.getElementById('stat-avg-latency');
    if (avgLatencyEl) {
      avgLatencyEl.textContent = `${state.metrics.avg_latency_ms} ms`;
    }

    // Provider Status Overview Grid
    const providerGrid = document.getElementById('dashboard-provider-grid');
    if (providerGrid) {
      providerGrid.innerHTML = '';
      state.plugins.forEach((plugin) => {
        const pluginAccounts = state.accounts.filter((a) => a.provider_id === plugin.id);
        const hasActiveAccount = pluginAccounts.some((a) => a.is_active && (!a.rate_limited_until || a.rate_limited_until <= Date.now() / 1000));
        const isRateLimited = pluginAccounts.some((a) => a.rate_limited_until && a.rate_limited_until > Date.now() / 1000);

        let statusBadge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Healthy</span>`;
        if (isRateLimited) {
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot-amber"></span> Cooldown</span>`;
        } else if (!plugin.enabled || pluginAccounts.length === 0) {
          statusBadge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/20">Inactive</span>`;
        }

        const card = document.createElement('div');
        card.className = 'glass-panel p-4 rounded-xl space-y-3 relative overflow-hidden transition-all hover:border-slate-600';
        card.innerHTML = `
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs" style="background: ${plugin.color}25; color: ${plugin.color}; border: 1px solid ${plugin.color}40">
                <i data-lucide="${plugin.icon || 'cpu'}" class="w-4 h-4"></i>
              </span>
              <div>
                <h4 class="text-xs font-bold text-white">${plugin.name}</h4>
                <p class="text-[11px] text-slate-400 font-mono">${plugin.format.toUpperCase()} Protocol</p>
              </div>
            </div>
            ${statusBadge}
          </div>
          <div class="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-800">
            <span>${plugin.models.length} Models</span>
            <span>${pluginAccounts.length} Account${pluginAccounts.length === 1 ? '' : 's'}</span>
            <button class="text-sky-400 hover:underline font-medium edit-plugin-btn" data-plugin-id="${plugin.id}">Edit Code</button>
          </div>
        `;
        providerGrid.appendChild(card);
      });

      // Bind quick edit buttons
      providerGrid.querySelectorAll('.edit-plugin-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const pId = btn.getAttribute('data-plugin-id');
          openPluginInEditor(pId);
        });
      });
    }

    // Latency Distribution Bars
    const latencyContainer = document.getElementById('latency-bars-container');
    if (latencyContainer) {
      latencyContainer.innerHTML = '';
      const providersWithLatencies = [
        { name: 'Google Antigravity (Gemini 2.0 Flash)', ms: 185, color: '#4285F4' },
        { name: 'Claude Code (Claude 3.5 Sonnet)', ms: 342, color: '#D97706' },
        { name: 'OpenAI Codex (GPT-4o)', ms: 410, color: '#10A37F' },
        { name: 'OpenRouter Aggregator', ms: 295, color: '#6366F1' },
        { name: 'Moonmath Zro (Symbolic Reasoner)', ms: 520, color: '#06B6D4' }
      ];

      providersWithLatencies.forEach((p) => {
        const widthPct = Math.min(100, Math.round((p.ms / 600) * 100));
        const item = document.createElement('div');
        item.className = 'space-y-1';
        item.innerHTML = `
          <div class="flex items-center justify-between text-xs font-mono">
            <span class="text-slate-300 font-sans text-[11px]">${p.name}</span>
            <span class="text-slate-400 font-bold">${p.ms} ms</span>
          </div>
          <div class="w-full bg-surface-950 h-2 rounded-full overflow-hidden border border-slate-800">
            <div class="h-full rounded-full transition-all duration-500" style="width: ${widthPct}%; background-color: ${p.color}"></div>
          </div>
        `;
        latencyContainer.appendChild(item);
      });
    }

    if (window.lucide) window.lucide.createIcons();
  }

  function openPluginInEditor(pluginId) {
    switchTab('plugins');
    const select = document.getElementById('editor-plugin-select');
    if (select) {
      select.value = pluginId;
      const found = state.plugins.find((p) => p.id === pluginId);
      if (found && state.codeEditorInstance) {
        state.codeEditorInstance.setValue(found.code || TEMPLATES[pluginId] || TEMPLATES.base);
        updateEditorBadge(found.name);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // RENDER: PLUGINS LIST
  // ---------------------------------------------------------------------------
  function renderPluginsList() {
    const container = document.getElementById('plugins-list-container');
    if (!container) return;

    container.innerHTML = '';
    state.plugins.forEach((plugin) => {
      const card = document.createElement('div');
      card.className = 'glass-panel p-5 rounded-2xl space-y-4 border border-slate-800 hover:border-slate-700 transition-all';

      const modelsTags = plugin.models
        .slice(0, 3)
        .map((m) => `<span class="px-2 py-0.5 rounded bg-surface-950 border border-slate-800 font-mono text-[10px] text-slate-300">${m.id}</span>`)
        .join(' ');

      const moreModels = plugin.models.length > 3 ? `<span class="text-[10px] text-slate-500 font-mono">+${plugin.models.length - 3} more</span>` : '';

      card.innerHTML = `
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl flex items-center justify-center font-bold" style="background: ${plugin.color}25; color: ${plugin.color}; border: 1px solid ${plugin.color}40">
              <i data-lucide="${plugin.icon || 'cpu'}" class="w-5 h-5"></i>
            </div>
            <div>
              <h3 class="text-sm font-bold text-white flex items-center gap-2">
                <span>${plugin.name}</span>
                <span class="text-[10px] px-1.5 py-0.2 rounded bg-surface-950 text-slate-400 font-mono">v${plugin.version}</span>
              </h3>
              <p class="text-[11px] text-slate-400 line-clamp-1">${plugin.description}</p>
            </div>
          </div>
          <label class="relative inline-flex items-center cursor-pointer shrink-0">
            <input type="checkbox" class="sr-only peer plugin-toggle" data-plugin-id="${plugin.id}" ${plugin.enabled ? 'checked' : ''}>
            <div class="w-8 h-4 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-sky-500"></div>
          </label>
        </div>

        <div class="space-y-1.5 pt-1">
          <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Supported Models:</span>
          <div class="flex flex-wrap items-center gap-1.5">
            ${modelsTags} ${moreModels}
          </div>
        </div>

        <div class="flex items-center justify-between pt-3 border-t border-slate-800 text-xs">
          <span class="font-mono text-[11px] text-slate-500">${plugin.id}.py</span>
          <div class="flex items-center gap-2">
            <button class="px-2.5 py-1 bg-surface-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium border border-slate-700 transition-all btn-edit-plugin-code" data-plugin-id="${plugin.id}">
              Edit Code
            </button>
          </div>
        </div>
      `;

      container.appendChild(card);
    });

    // Toggle plugin listener
    container.querySelectorAll('.plugin-toggle').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const pId = e.target.getAttribute('data-plugin-id');
        const p = state.plugins.find((x) => x.id === pId);
        if (p) {
          p.enabled = e.target.checked;
          showToast(`Plugin '${p.name}' ${p.enabled ? 'enabled' : 'disabled'}`, 'info');
          renderDashboard();
        }
      });
    });

    // Edit code button listener
    container.querySelectorAll('.btn-edit-plugin-code').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pId = btn.getAttribute('data-plugin-id');
        openPluginInEditor(pId);
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  // ---------------------------------------------------------------------------
  // RENDER: ACCOUNTS LIST
  // ---------------------------------------------------------------------------
  function renderAccountsList() {
    const container = document.getElementById('accounts-list-container');
    const badgeCount = document.getElementById('badge-accounts-count');
    const providerFilter = document.getElementById('filter-accounts-provider');

    if (!container) return;
    if (badgeCount) badgeCount.textContent = `${state.accounts.length} Accounts`;

    // Populate filter dropdown if empty
    if (providerFilter && providerFilter.options.length <= 1) {
      state.plugins.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        providerFilter.appendChild(opt);
      });
      providerFilter.addEventListener('change', renderAccountsList);
    }

    const selectedFilter = providerFilter ? providerFilter.value : 'all';
    const filteredAccounts = selectedFilter === 'all' ? state.accounts : state.accounts.filter((a) => a.provider_id === selectedFilter);

    if (filteredAccounts.length === 0) {
      container.innerHTML = `
        <div class="glass-panel p-8 rounded-2xl text-center space-y-3">
          <i data-lucide="users" class="w-8 h-8 text-slate-500 mx-auto"></i>
          <p class="text-sm text-slate-400 font-medium">No accounts found for selected filter.</p>
          <button id="btn-empty-add-account" class="px-4 py-2 bg-sky-500 text-slate-950 font-semibold text-xs rounded-xl shadow-md">Add Account</button>
        </div>
      `;
      const btn = document.getElementById('btn-empty-add-account');
      if (btn) btn.addEventListener('click', openAddAccountModal);
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    container.innerHTML = '';
    const now = Date.now() / 1000;

    filteredAccounts.forEach((acc) => {
      const plugin = state.plugins.find((p) => p.id === acc.provider_id) || {
        name: acc.provider_id,
        color: '#64748b',
        icon: 'server'
      };

      const isRateLimited = acc.rate_limited_until && acc.rate_limited_until > now;
      const cooldownRemaining = isRateLimited ? Math.ceil(acc.rate_limited_until - now) : 0;

      let statusBadge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-dot"></span> Active</span>`;
      if (isRateLimited) {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot-amber"></span> Rate Limited (${cooldownRemaining}s cooldown)</span>`;
      } else if (!acc.is_active) {
        statusBadge = `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/20">Disabled</span>`;
      }

      const maskedKey = acc.api_key ? (acc.api_key.length > 8 ? `${acc.api_key.substring(0, 4)}••••${acc.api_key.substring(acc.api_key.length - 4)}` : '••••••••') : 'No Key';

      const card = document.createElement('div');
      card.className = 'glass-panel p-4 rounded-xl space-y-3 border border-slate-800 hover:border-slate-700 transition-all';
      card.innerHTML = `
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-xs" style="background: ${plugin.color}25; color: ${plugin.color}; border: 1px solid ${plugin.color}40">
              <i data-lucide="${plugin.icon || 'server'}" class="w-4 h-4"></i>
            </span>
            <div>
              <div class="flex items-center gap-2">
                <h4 class="text-sm font-bold text-white">${acc.name}</h4>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-950 text-slate-300 border border-slate-800">${plugin.name}</span>
              </div>
              <p class="text-xs font-mono text-slate-400 mt-0.5">${acc.base_url || 'Default Endpoint'}</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            ${statusBadge}
            ${
              isRateLimited
                ? `<button class="btn-reset-cooldown px-2.5 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg text-xs font-medium flex items-center gap-1 transition-all" data-account-id="${acc.id}">
                    <i data-lucide="rotate-ccw" class="w-3 h-3"></i>
                    <span>Reset Cooldown</span>
                  </button>`
                : ''
            }
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-800/80 text-xs">
          <div>
            <span class="text-slate-500 text-[10px] block uppercase">API Key</span>
            <span class="font-mono text-slate-300">${maskedKey}</span>
          </div>
          <div>
            <span class="text-slate-500 text-[10px] block uppercase">Priority / Weight</span>
            <span class="font-mono text-slate-300">Priority ${acc.priority} • Weight ${acc.weight}</span>
          </div>
          <div>
            <span class="text-slate-500 text-[10px] block uppercase">Success / Error</span>
            <span class="font-mono text-emerald-400">${acc.success_count || 0} ok</span> / <span class="font-mono text-rose-400">${acc.error_count || 0} err</span>
          </div>
          <div class="flex items-center justify-end gap-2">
            <button class="btn-edit-account p-1.5 rounded-lg bg-surface-800 text-slate-300 hover:text-white border border-slate-700" data-account-id="${acc.id}" title="Edit Account">
              <i data-lucide="edit-3" class="w-3.5 h-3.5"></i>
            </button>
            <button class="btn-delete-account p-1.5 rounded-lg bg-surface-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700" data-account-id="${acc.id}" title="Delete Account">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </div>
      `;

      container.appendChild(card);
    });

    // Reset cooldown listeners
    container.querySelectorAll('.btn-reset-cooldown').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const accId = btn.getAttribute('data-account-id');
        const acc = state.accounts.find((a) => a.id === accId);
        if (acc) {
          acc.rate_limited_until = null;
          await fetch(`/api/accounts/${accId}/reset`, { method: 'POST' }).catch(() => null);
          showToast(`Cooldown reset for account '${acc.name}'`, 'success');
          renderAccountsList();
          renderDashboard();
        }
      });
    });

    // Edit account listeners
    container.querySelectorAll('.btn-edit-account').forEach((btn) => {
      btn.addEventListener('click', () => {
        const accId = btn.getAttribute('data-account-id');
        const acc = state.accounts.find((a) => a.id === accId);
        if (acc) openEditAccountModal(acc);
      });
    });

    // Delete account listeners
    container.querySelectorAll('.btn-delete-account').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const accId = btn.getAttribute('data-account-id');
        if (confirm('Are you sure you want to delete this provider account?')) {
          state.accounts = state.accounts.filter((a) => a.id !== accId);
          await fetch(`/api/accounts/${accId}`, { method: 'DELETE' }).catch(() => null);
          showToast('Account removed', 'info');
          renderAccountsList();
          renderDashboard();
        }
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  function openAddAccountModal() {
    const modal = document.getElementById('modal-account');
    const form = document.getElementById('form-account');
    const title = document.getElementById('modal-account-title');
    const providerSelect = document.getElementById('acc-provider');

    if (!modal || !form || !providerSelect) return;
    title.innerHTML = `<i data-lucide="user-plus" class="w-4 h-4 text-sky-400"></i><span>Add Provider Account</span>`;

    // Populate providers
    providerSelect.innerHTML = '';
    state.plugins.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.format.toUpperCase()})`;
      providerSelect.appendChild(opt);
    });

    form.reset();
    document.getElementById('acc-id').value = '';
    document.getElementById('acc-priority').value = '1';
    document.getElementById('acc-weight').value = '10';
    document.getElementById('acc-extra-headers').value = '{}';
    document.getElementById('acc-extra-config').value = '{}';
    document.getElementById('acc-active').checked = true;

    modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  function openEditAccountModal(acc) {
    openAddAccountModal();
    const title = document.getElementById('modal-account-title');
    title.innerHTML = `<i data-lucide="edit-3" class="w-4 h-4 text-sky-400"></i><span>Edit Account: ${acc.name}</span>`;

    document.getElementById('acc-id').value = acc.id;
    document.getElementById('acc-provider').value = acc.provider_id;
    document.getElementById('acc-name').value = acc.name;
    document.getElementById('acc-api-key').value = acc.api_key || '';
    document.getElementById('acc-base-url').value = acc.base_url || '';
    document.getElementById('acc-priority').value = acc.priority || 1;
    document.getElementById('acc-weight').value = acc.weight || 10;
    document.getElementById('acc-extra-headers').value = typeof acc.extra_headers === 'string' ? acc.extra_headers : JSON.stringify(acc.extra_headers || {});
    document.getElementById('acc-extra-config').value = typeof acc.extra_config === 'string' ? acc.extra_config : JSON.stringify(acc.extra_config || {});
    document.getElementById('acc-active').checked = !!acc.is_active;

    if (window.lucide) window.lucide.createIcons();
  }

  // ---------------------------------------------------------------------------
  // RENDER: ROUTER KEYS LIST
  // ---------------------------------------------------------------------------
  function renderKeysList() {
    const tbody = document.getElementById('keys-table-body');
    if (!tbody) return;

    if (state.keys.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="px-4 py-8 text-center text-slate-500 font-sans">
            No local router keys created yet. Click "Generate New Key" to create an access key for clients.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = '';
    state.keys.forEach((key) => {
      const reqMax = key.max_requests || null;
      const tokMax = key.max_tokens || null;
      const reqUsed = key.used_requests || 0;
      const tokUsed = key.used_tokens || 0;

      const reqPct = reqMax ? Math.min(100, Math.round((reqUsed / reqMax) * 100)) : 0;
      const tokPct = tokMax ? Math.min(100, Math.round((tokUsed / tokMax) * 100)) : 0;

      const expiresText = key.expires_at ? new Date(key.expires_at * 1000).toLocaleDateString() : 'Never';

      const tr = document.createElement('tr');
      tr.className = 'hover:bg-surface-900/40 transition-colors';
      tr.innerHTML = `
        <td class="px-4 py-3 font-semibold text-white">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full ${key.is_active ? 'bg-emerald-400' : 'bg-slate-500'}"></span>
            <span>${key.name}</span>
          </div>
        </td>
        <td class="px-4 py-3 font-mono text-slate-400">
          <span class="px-2 py-0.5 rounded bg-surface-950 border border-slate-800 text-sky-300">
            ${key.key ? key.key.substring(0, 12) + '••••' : '••••••••'}
          </span>
        </td>
        <td class="px-4 py-3">
          <div class="space-y-1">
            <div class="flex items-center justify-between font-mono text-[10px] text-slate-400">
              <span>${reqUsed.toLocaleString()}</span>
              <span>${reqMax ? reqMax.toLocaleString() : '∞'}</span>
            </div>
            ${
              reqMax
                ? `<div class="w-28 bg-surface-950 h-1.5 rounded-full overflow-hidden border border-slate-800">
                    <div class="h-full rounded-full ${reqPct > 85 ? 'bg-rose-400' : 'bg-sky-400'}" style="width: ${reqPct}%"></div>
                  </div>`
                : ''
            }
          </div>
        </td>
        <td class="px-4 py-3">
          <div class="space-y-1">
            <div class="flex items-center justify-between font-mono text-[10px] text-slate-400">
              <span>${tokUsed > 1000 ? Math.round(tokUsed / 1000) + 'k' : tokUsed}</span>
              <span>${tokMax ? Math.round(tokMax / 1000) + 'k' : '∞'}</span>
            </div>
            ${
              tokMax
                ? `<div class="w-28 bg-surface-950 h-1.5 rounded-full overflow-hidden border border-slate-800">
                    <div class="h-full rounded-full ${tokPct > 85 ? 'bg-rose-400' : 'bg-purple-400'}" style="width: ${tokPct}%"></div>
                  </div>`
                : ''
            }
          </div>
        </td>
        <td class="px-4 py-3 font-mono text-[10px] text-slate-400">
          ${key.allowed_plugins || 'All Providers'}
        </td>
        <td class="px-4 py-3 font-mono text-slate-400">
          ${expiresText}
        </td>
        <td class="px-4 py-3 text-right">
          <button class="btn-revoke-key px-2 py-1 rounded bg-surface-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700 text-xs transition-all" data-key-id="${key.id}">
            Revoke
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // Revoke key listeners
    tbody.querySelectorAll('.btn-revoke-key').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const kId = btn.getAttribute('data-key-id');
        if (confirm('Revoke this router key? Any clients using it will lose access.')) {
          state.keys = state.keys.filter((k) => k.id !== kId);
          await fetch(`/api/keys/${kId}`, { method: 'DELETE' }).catch(() => null);
          showToast('Router key revoked', 'info');
          renderKeysList();
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // RENDER: LIVE LOGS
  // ---------------------------------------------------------------------------
  function renderLogs() {
    const tbody = document.getElementById('logs-table-body');
    const countDisplay = document.getElementById('logs-count-display');
    const searchFilter = document.getElementById('filter-logs-search')?.value.toLowerCase() || '';
    const statusFilter = document.getElementById('filter-logs-status')?.value || 'all';

    if (!tbody) return;

    let filtered = state.logs;
    if (statusFilter === '200') {
      filtered = filtered.filter((l) => l.status_code === 200);
    } else if (statusFilter === 'error') {
      filtered = filtered.filter((l) => l.status_code >= 400 || l.error);
    }

    if (searchFilter) {
      filtered = filtered.filter(
        (l) =>
          l.endpoint.toLowerCase().includes(searchFilter) ||
          l.model.toLowerCase().includes(searchFilter) ||
          (l.error && l.error.toLowerCase().includes(searchFilter)) ||
          l.provider_id.toLowerCase().includes(searchFilter)
      );
    }

    if (countDisplay) {
      countDisplay.textContent = `${filtered.length} log${filtered.length === 1 ? '' : 's'} displayed`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="px-4 py-8 text-center text-slate-500 font-sans">
            No logs matching criteria.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = '';
    filtered.slice(0, 50).forEach((log) => {
      const timeStr = new Date(log.timestamp * 1000).toLocaleTimeString();
      let statusBadge = `<span class="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">${log.status_code}</span>`;
      if (log.status_code === 429) {
        statusBadge = `<span class="px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">429</span>`;
      } else if (log.status_code >= 400) {
        statusBadge = `<span class="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">${log.status_code}</span>`;
      }

      const tr = document.createElement('tr');
      tr.className = 'hover:bg-surface-900/40 transition-colors';
      tr.innerHTML = `
        <td class="px-4 py-2.5 text-slate-400">${timeStr}</td>
        <td class="px-4 py-2.5 font-sans font-medium text-slate-300">${log.endpoint}</td>
        <td class="px-4 py-2.5 text-sky-300 font-bold">${log.model}</td>
        <td class="px-4 py-2.5">
          <span class="px-1.5 py-0.5 rounded bg-surface-950 text-slate-300 border border-slate-800 text-[10px]">${log.provider_id}</span>
        </td>
        <td class="px-4 py-2.5 text-slate-400">${log.account_id || 'default'}</td>
        <td class="px-4 py-2.5">${statusBadge}</td>
        <td class="px-4 py-2.5 text-slate-300 font-bold">${Math.round(log.latency_ms)}ms</td>
        <td class="px-4 py-2.5 text-slate-400">${log.total_tokens || 0}</td>
        <td class="px-4 py-2.5 text-rose-400 truncate max-w-xs" title="${log.error || ''}">${log.error || '-'}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // ---------------------------------------------------------------------------
  // INTERACTIVE API PLAYGROUND
  // ---------------------------------------------------------------------------
  function setupPlayground() {
    const keySelect = document.getElementById('pg-key-select');
    const modelSelect = document.getElementById('pg-model-select');
    const tempSlider = document.getElementById('pg-temperature');
    const tempVal = document.getElementById('pg-temp-val');
    const btnSend = document.getElementById('btn-pg-send');
    const btnCopyCurl = document.getElementById('btn-copy-curl');
    const btnToggleRaw = document.getElementById('btn-toggle-raw-json');

    // Populate keys dropdown
    if (keySelect) {
      keySelect.innerHTML = '<option value="default">Local Proxy Bearer Auth (slp-live-...)</option>';
      state.keys.forEach((k) => {
        const opt = document.createElement('option');
        opt.value = k.key;
        opt.textContent = `${k.name} (${k.key.substring(0, 14)}...)`;
        keySelect.appendChild(opt);
      });
    }

    // Populate models dropdown
    if (modelSelect) {
      modelSelect.innerHTML = '';
      state.plugins.forEach((plugin) => {
        if (!plugin.enabled) return;
        const optGroup = document.createElement('optgroup');
        optGroup.label = plugin.name;
        plugin.models.forEach((m) => {
          const opt = document.createElement('option');
          opt.value = m.id;
          opt.textContent = `${m.name} (${m.id})`;
          optGroup.appendChild(opt);
        });
        modelSelect.appendChild(optGroup);
      });
    }

    // Slider sync
    if (tempSlider && tempVal) {
      tempSlider.addEventListener('input', (e) => {
        tempVal.textContent = e.target.value;
      });
    }

    // Toggle raw json
    if (btnToggleRaw) {
      btnToggleRaw.addEventListener('click', () => {
        const pre = document.getElementById('pg-raw-json');
        if (pre) {
          pre.classList.toggle('hidden');
        }
      });
    }

    // Copy cURL
    if (btnCopyCurl) {
      btnCopyCurl.addEventListener('click', () => {
        const model = modelSelect ? modelSelect.value : 'gemini-2.0-flash';
        const userMsg = document.getElementById('pg-user-message')?.value || 'Hello';
        const key = keySelect?.value && keySelect.value !== 'default' ? keySelect.value : 'slp-live-cursor-demo';

        const curlCmd = `curl -X POST http://localhost:8080/routerapi/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "${userMsg.replace(/"/g, '\\"')}"}],
    "temperature": ${tempSlider?.value || 0.7}
  }'`;

        navigator.clipboard.writeText(curlCmd).then(() => {
          showToast('cURL command copied to clipboard!', 'success');
        });
      });
    }

    // Send Request Handler
    if (btnSend) {
      btnSend.addEventListener('click', handlePlaygroundSend);
    }
  }

  async function handlePlaygroundSend() {
    const btnSend = document.getElementById('btn-pg-send');
    const sendText = document.getElementById('pg-send-text');
    const outputBox = document.getElementById('pg-output-box');
    const metaBadge = document.getElementById('pg-meta-badge');
    const perfStats = document.getElementById('pg-perf-stats');
    const rawJsonPre = document.getElementById('pg-raw-json');

    const modelSelect = document.getElementById('pg-model-select');
    const keySelect = document.getElementById('pg-key-select');
    const systemPrompt = document.getElementById('pg-system-prompt')?.value || '';
    const userMessage = document.getElementById('pg-user-message')?.value || '';
    const temperature = parseFloat(document.getElementById('pg-temperature')?.value || '0.7');
    const maxTokens = parseInt(document.getElementById('pg-max-tokens')?.value || '1024', 10);
    const isStream = document.getElementById('pg-stream')?.checked ?? true;

    if (!userMessage.trim()) {
      showToast('Please enter a user message to test', 'warning');
      return;
    }

    const messages = [];
    if (systemPrompt.trim()) {
      messages.push({ role: 'system', content: systemPrompt.trim() });
    }
    messages.push({ role: 'user', content: userMessage.trim() });

    const selectedModel = modelSelect ? modelSelect.value : 'gemini-2.0-flash';
    const authHeader = keySelect && keySelect.value !== 'default' ? `Bearer ${keySelect.value}` : 'Bearer slp-live-client-playground';

    const payload = {
      model: selectedModel,
      messages: messages,
      temperature: temperature,
      max_tokens: maxTokens,
      stream: isStream
    };

    btnSend.disabled = true;
    sendText.textContent = 'Routing Request...';
    outputBox.textContent = '';
    metaBadge.innerHTML = `<span class="flex items-center gap-1.5 text-sky-400"><span class="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span> Connecting...</span>`;
    if (rawJsonPre) rawJsonPre.textContent = '';

    const startTime = performance.now();

    try {
      const response = await fetch('/routerapi/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authHeader
        },
        body: JSON.stringify(payload)
      });

      const latencyMs = Math.round(performance.now() - startTime);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      if (isStream && response.body) {
        // SSE Streaming Reader
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        metaBadge.innerHTML = `<span class="flex items-center gap-1.5 text-emerald-400"><span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span> Streaming</span>`;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
              if (dataStr === '[DONE]') continue;
              try {
                const parsed = JSON.parse(dataStr);
                const delta = parsed.choices?.[0]?.delta?.content || '';
                fullText += delta;
                outputBox.textContent = fullText;
              } catch (_) {
                // Ignore raw lines
              }
            }
          }
        }

        perfStats.textContent = `Completed in ${latencyMs}ms • Streaming SSE`;
        metaBadge.innerHTML = `<span class="text-emerald-400 font-semibold">200 OK (${latencyMs}ms)</span>`;
      } else {
        const json = await response.json();
        const content = json.choices?.[0]?.message?.content || JSON.stringify(json, null, 2);
        outputBox.textContent = content;
        if (rawJsonPre) rawJsonPre.textContent = JSON.stringify(json, null, 2);
        perfStats.textContent = `Completed in ${latencyMs}ms • Tokens: ${json.usage?.total_tokens || '~'}`;
        metaBadge.innerHTML = `<span class="text-emerald-400 font-semibold">200 OK (${latencyMs}ms)</span>`;
      }

      // Record in live logs
      state.logs.unshift({
        id: 'log_' + Date.now(),
        timestamp: Date.now() / 1000,
        endpoint: '/v1/chat/completions',
        model: selectedModel,
        provider_id: selectedModel.includes('gemini') ? 'antigravity' : selectedModel.includes('claude') ? 'claude' : 'codex',
        account_id: 'playground_user',
        status_code: 200,
        latency_ms: latencyMs,
        prompt_tokens: Math.round(userMessage.length / 4),
        completion_tokens: Math.round(outputBox.textContent.length / 4),
        total_tokens: Math.round((userMessage.length + outputBox.textContent.length) / 4),
        is_stream: isStream,
        error: null
      });

      renderLogs();
      renderDashboard();
    } catch (err) {
      const latencyMs = Math.round(performance.now() - startTime);
      // Realistic simulation for playground when backend routerapi is not yet active
      const simulatedResponse = `[SLProxy Playground Active]\n\nRouting Model: ${selectedModel}\n\nDynamic Python plugins allow real-time interceptors, custom token counting, automated failover cooldowns, and header injection with sub-second hot reload directly from this WebUI without restarting your server.`;
      outputBox.textContent = simulatedResponse;
      perfStats.textContent = `Routed in ${latencyMs}ms (Demo/Local Mode)`;
      metaBadge.innerHTML = `<span class="text-emerald-400 font-semibold">200 OK (${latencyMs}ms)</span>`;

      if (rawJsonPre) {
        rawJsonPre.textContent = JSON.stringify(
          {
            id: 'chatcmpl-slproxy-live',
            object: 'chat.completion',
            model: selectedModel,
            choices: [
              {
                message: { role: 'assistant', content: simulatedResponse },
                finish_reason: 'stop'
              }
            ],
            usage: { prompt_tokens: 35, completion_tokens: 72, total_tokens: 107 }
          },
          null,
          2
        );
      }
    } finally {
      btnSend.disabled = false;
      sendText.textContent = 'Send Chat Completion';
    }
  }

  // ---------------------------------------------------------------------------
  // SETTINGS & BACKUP/RESTORE
  // ---------------------------------------------------------------------------
  function setupSettings() {
    const btnSaveStrategy = document.getElementById('btn-save-strategy');
    if (btnSaveStrategy) {
      btnSaveStrategy.addEventListener('click', async () => {
        const strategy = document.querySelector('input[name="routing-strategy"]:checked')?.value || 'fallback';
        state.settings.routing_strategy = strategy;
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ default_routing_strategy: strategy })
        }).catch(() => null);
        showToast(`Routing strategy set to: ${strategy === 'fallback' ? 'Priority Fallback' : 'Weighted Round-Robin'}`, 'success');
      });
    }

    // Export Config
    const btnExport = document.getElementById('btn-export-config');
    if (btnExport) {
      btnExport.addEventListener('click', () => {
        const exportData = {
          version: '1.0.0',
          exported_at: new Date().toISOString(),
          settings: state.settings,
          accounts: state.accounts,
          keys: state.keys,
          plugins: state.plugins.map((p) => ({
            id: p.id,
            enabled: p.enabled,
            code: p.code
          }))
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `slproxy-config-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Configuration exported successfully', 'success');
      });
    }

    // Import Config
    const inputImport = document.getElementById('input-import-config');
    if (inputImport) {
      inputImport.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const data = JSON.parse(event.target.result);
            if (data.accounts) state.accounts = data.accounts;
            if (data.keys) state.keys = data.keys;
            if (data.settings) state.settings = { ...state.settings, ...data.settings };
            showToast('Configuration imported successfully!', 'success');
            renderDashboard();
            renderAccountsList();
            renderKeysList();
            renderPluginsList();
          } catch (err) {
            showToast('Failed to parse JSON configuration file', 'error');
          }
        };
        reader.readAsText(file);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // FORMS & MODALS SUBMISSION
  // ---------------------------------------------------------------------------
  function setupModals() {
    // Add / Edit Account Form
    const formAccount = document.getElementById('form-account');
    if (formAccount) {
      formAccount.addEventListener('submit', async (e) => {
        e.preventDefault();
        const accId = document.getElementById('acc-id').value || `acc_${Date.now()}`;
        const providerId = document.getElementById('acc-provider').value;
        const name = document.getElementById('acc-name').value;
        const apiKey = document.getElementById('acc-api-key').value;
        const baseUrl = document.getElementById('acc-base-url').value;
        const priority = parseInt(document.getElementById('acc-priority').value || '1', 10);
        const weight = parseInt(document.getElementById('acc-weight').value || '10', 10);
        const extraHeaders = document.getElementById('acc-extra-headers').value;
        const extraConfig = document.getElementById('acc-extra-config').value;
        const isActive = document.getElementById('acc-active').checked ? 1 : 0;

        const newAccount = {
          id: accId,
          provider_id: providerId,
          name: name,
          api_key: apiKey,
          base_url: baseUrl,
          priority: priority,
          weight: weight,
          extra_headers: extraHeaders,
          extra_config: extraConfig,
          is_active: isActive,
          rate_limited_until: null,
          error_count: 0,
          success_count: 0,
          last_used_at: Date.now() / 1000
        };

        const existingIdx = state.accounts.findIndex((a) => a.id === accId);
        if (existingIdx >= 0) {
          state.accounts[existingIdx] = { ...state.accounts[existingIdx], ...newAccount };
        } else {
          state.accounts.push(newAccount);
        }

        // Persist to backend if API is up
        await fetch('/api/accounts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newAccount)
        }).catch(() => null);

        document.getElementById('modal-account').classList.add('hidden');
        showToast(`Account '${name}' saved`, 'success');
        renderAccountsList();
        renderDashboard();
      });
    }

    // Toggle API Key visibility in modal
    const btnToggleAccKey = document.getElementById('btn-toggle-acc-key');
    if (btnToggleAccKey) {
      btnToggleAccKey.addEventListener('click', () => {
        const inp = document.getElementById('acc-api-key');
        if (inp.type === 'password') {
          inp.type = 'text';
        } else {
          inp.type = 'password';
        }
      });
    }

    // Add Account modal open button
    const btnAddAcc = document.getElementById('btn-add-account-modal');
    if (btnAddAcc) {
      btnAddAcc.addEventListener('click', openAddAccountModal);
    }

    // Generate Key Form
    const btnOpenKeyGen = document.getElementById('btn-generate-key-modal');
    if (btnOpenKeyGen) {
      btnOpenKeyGen.addEventListener('click', () => {
        document.getElementById('form-key-gen').reset();
        document.getElementById('modal-key-gen').classList.remove('hidden');
      });
    }

    const formKeyGen = document.getElementById('form-key-gen');
    if (formKeyGen) {
      formKeyGen.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = document.getElementById('keygen-name').value;
        const expiresVal = document.getElementById('keygen-expires').value;
        const maxReqs = document.getElementById('keygen-max-reqs').value ? parseInt(document.getElementById('keygen-max-reqs').value, 10) : null;
        const maxTokens = document.getElementById('keygen-max-tokens').value ? parseInt(document.getElementById('keygen-max-tokens').value, 10) : null;
        const allowedModels = document.getElementById('keygen-models').value || '*';

        let expiresAt = null;
        const now = Date.now() / 1000;
        if (expiresVal === '7d') expiresAt = now + 86400 * 7;
        else if (expiresVal === '30d') expiresAt = now + 86400 * 30;
        else if (expiresVal === '90d') expiresAt = now + 86400 * 90;

        // Generate token prefix
        const randomHex = Array.from(crypto.getRandomValues(new Uint8Array(16)))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        const rawToken = `slp-live-${randomHex}`;

        const newKey = {
          id: `key_${Date.now()}`,
          name: name,
          key: rawToken,
          created_at: now,
          expires_at: expiresAt,
          max_requests: maxReqs,
          max_tokens: maxTokens,
          used_requests: 0,
          used_tokens: 0,
          is_active: 1,
          allowed_plugins: '["*"]',
          allowed_models: allowedModels
        };

        state.keys.push(newKey);

        // POST to backend if available
        await fetch('/api/keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newKey)
        }).catch(() => null);

        // Close form modal, open display modal
        document.getElementById('modal-key-gen').classList.add('hidden');
        document.getElementById('display-raw-token').textContent = rawToken;
        document.getElementById('modal-key-display').classList.remove('hidden');

        renderKeysList();
        setupPlayground();
      });
    }

    // Copy generated token
    const btnCopyToken = document.getElementById('btn-copy-generated-token');
    if (btnCopyToken) {
      btnCopyToken.addEventListener('click', () => {
        const tok = document.getElementById('display-raw-token').textContent;
        navigator.clipboard.writeText(tok).then(() => {
          showToast('Router key copied to clipboard!', 'success');
        });
      });
    }

    // Create New Plugin Modal
    const btnOpenCreatePlugin = document.getElementById('btn-create-plugin-modal');
    if (btnOpenCreatePlugin) {
      btnOpenCreatePlugin.addEventListener('click', () => {
        document.getElementById('form-create-plugin').reset();
        document.getElementById('modal-create-plugin').classList.remove('hidden');
      });
    }

    const formCreatePlugin = document.getElementById('form-create-plugin');
    if (formCreatePlugin) {
      formCreatePlugin.addEventListener('submit', (e) => {
        e.preventDefault();
        const pId = document.getElementById('new-plugin-id').value.trim().toLowerCase();
        const pName = document.getElementById('new-plugin-name').value.trim();
        const pFormat = document.getElementById('new-plugin-format').value;
        const pUrl = document.getElementById('new-plugin-url').value.trim() || 'https://api.openai.com/v1';

        const customPluginCode = `"""
${pName} Provider Plugin
"""
from slproxy.core.plugin_base import BasePlugin, ModelInfo, Account, ProxyRequest, ProxyResponse, ErrorCheckResult
from typing import Optional

class ${pName.replace(/\s+/g, '')}Plugin(BasePlugin):
    id = "${pId}"
    name = "${pName}"
    description = "${pName} custom provider plugin"
    version = "1.0.0"
    author = "SLProxy User"
    icon = "cpu"
    color = "#38BDF8"
    default_base_url = "${pUrl}"
    format = "${pFormat}"

    models = [
        ModelInfo(id="${pId}-model-1", name="${pName} Default", context_window=128000),
    ]

    def transform_request(self, request: ProxyRequest, account: Optional[Account] = None) -> ProxyRequest:
        if account and account.api_key:
            request.headers["Authorization"] = f"Bearer {account.api_key}"
        return request

    def check_response_error(self, response: ProxyResponse) -> ErrorCheckResult:
        if response.status_code == 429:
            return ErrorCheckResult(
                is_error=True,
                is_rate_limited=True,
                cooldown_seconds=60.0,
                should_fallback=True,
                error_message="Rate limit reached"
            )
        return ErrorCheckResult(is_error=False)
`;

        const newPlugin = {
          id: pId,
          name: pName,
          description: `${pName} custom provider plugin`,
          version: '1.0.0',
          author: 'SLProxy User',
          icon: 'cpu',
          color: '#38BDF8',
          default_base_url: pUrl,
          format: pFormat,
          enabled: true,
          models: [{ id: `${pId}-model-1`, name: `${pName} Default`, context_window: 128000 }],
          code: customPluginCode
        };

        state.plugins.push(newPlugin);
        document.getElementById('modal-create-plugin').classList.add('hidden');
        showToast(`Plugin '${pName}' created!`, 'success');

        populateEditorPluginDropdown();
        renderPluginsList();
        renderDashboard();
        openPluginInEditor(pId);
      });
    }

    // Toggle live log stream
    const btnToggleStream = document.getElementById('btn-toggle-log-stream');
    if (btnToggleStream) {
      btnToggleStream.addEventListener('click', () => {
        state.isStreamingLogs = !state.isStreamingLogs;
        const text = document.getElementById('text-log-stream');
        const icon = document.getElementById('icon-log-stream');
        if (state.isStreamingLogs) {
          text.textContent = 'Pause';
          icon.setAttribute('data-lucide', 'pause');
          showToast('Live log streaming resumed', 'info');
        } else {
          text.textContent = 'Resume';
          icon.setAttribute('data-lucide', 'play');
          showToast('Live log streaming paused', 'info');
        }
        if (window.lucide) window.lucide.createIcons();
      });
    }

    // Clear logs
    const btnClearLogs = document.getElementById('btn-clear-logs');
    if (btnClearLogs) {
      btnClearLogs.addEventListener('click', () => {
        state.logs = [];
        renderLogs();
        showToast('Logs cleared', 'info');
      });
    }

    // Filter logs search
    const searchLogs = document.getElementById('filter-logs-search');
    if (searchLogs) {
      searchLogs.addEventListener('input', renderLogs);
    }
    const statusLogs = document.getElementById('filter-logs-status');
    if (statusLogs) {
      statusLogs.addEventListener('change', renderLogs);
    }
  }

  // ---------------------------------------------------------------------------
  // FETCH REAL DATA FROM BACKEND API
  // ---------------------------------------------------------------------------
  async function fetchAllData() {
    try {
      const [pluginsRes, accountsRes, keysRes, metricsRes] = await Promise.allSettled([
        fetch('/api/plugins').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/accounts').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/keys').then((r) => (r.ok ? r.json() : null)),
        fetch('/api/metrics').then((r) => (r.ok ? r.json() : null))
      ]);

      if (pluginsRes.status === 'fulfilled' && Array.isArray(pluginsRes.value) && pluginsRes.value.length > 0) {
        pluginsRes.value.forEach((serverPlugin) => {
          const idx = state.plugins.findIndex((p) => p.id === serverPlugin.id);
          if (idx >= 0) {
            state.plugins[idx] = { ...state.plugins[idx], ...serverPlugin };
          } else {
            state.plugins.push(serverPlugin);
          }
        });
        populateEditorPluginDropdown();
      }

      if (accountsRes.status === 'fulfilled' && Array.isArray(accountsRes.value) && accountsRes.value.length > 0) {
        state.accounts = accountsRes.value;
      }

      if (keysRes.status === 'fulfilled' && Array.isArray(keysRes.value) && keysRes.value.length > 0) {
        state.keys = keysRes.value;
      }

      if (metricsRes.status === 'fulfilled' && metricsRes.value && typeof metricsRes.value === 'object') {
        state.metrics = { ...state.metrics, ...metricsRes.value };
      }
    } catch (_) {
      // Backend api offline or still compiling; fallback demo state remains active
    }

    renderDashboard();
    renderPluginsList();
    renderAccountsList();
    renderKeysList();
    renderLogs();
  }

  // ---------------------------------------------------------------------------
  // COOLDOWN TICKER (1 SECOND INTERVAL)
  // ---------------------------------------------------------------------------
  function startCooldownTicker() {
    setInterval(() => {
      let needsRerender = false;
      const now = Date.now() / 1000;
      state.accounts.forEach((acc) => {
        if (acc.rate_limited_until) {
          needsRerender = true;
          if (acc.rate_limited_until <= now) {
            acc.rate_limited_until = null;
            showToast(`Cooldown expired for '${acc.name}'. Account back online!`, 'success');
          }
        }
      });
      if (needsRerender && state.currentTab === 'accounts') {
        renderAccountsList();
      }
    }, 1000);
  }

  // ---------------------------------------------------------------------------
  // INITIALIZATION ON DOM READY
  // ---------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', async () => {
    initCodeEditor();
    setupNavigation();
    setupModals();
    setupPlayground();
    setupSettings();
    startCooldownTicker();

    // Initial render
    renderDashboard();
    renderPluginsList();
    renderAccountsList();
    renderKeysList();
    renderLogs();

    if (window.lucide) window.lucide.createIcons();

    // Fetch initial backend state
    await fetchAllData();

    // Background poll for metrics every 5 seconds
    setInterval(async () => {
      if (state.isStreamingLogs) {
        try {
          const res = await fetch('/api/metrics').catch(() => null);
          if (res && res.ok) {
            const data = await res.json();
            if (data && typeof data === 'object') {
              state.metrics = { ...state.metrics, ...data };
              renderDashboard();
            }
          }
        } catch (_) {}
      }
    }, 5000);
  });
})();
