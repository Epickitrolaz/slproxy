"""
OpenAI Compatible Provider Plugin
=================================

Educational Reference Implementation for Generic OpenAI-Compatible Endpoints.

Overview & Architectural Rationale
-----------------------------------
This plugin provides standard OpenAI API proxying for third-party endpoints,
self-hosted inference engines (vLLM, Ollama, LocalAI, TGI), and OpenAI-compatible
gateways (Groq, Together AI, Fireworks, Mistral, Perplexity).

It passes through standard Authorization Bearer tokens and JSON payloads
without proprietary transforms.
"""

from typing import Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest


class OpenAICompatiblePlugin(BasePlugin):
    """
    Generic OpenAI Compatible provider plugin.
    """

    id: str = "openai_compatible"
    name: str = "OpenAI Compatible"
    description: str = "Generic OpenAI-compatible API endpoint proxy supporting custom self-hosted or cloud inference"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "cpu"
    color: str = "#000000"
    default_base_url: str = "https://api.openai.com/v1"
    format: str = "openai"

    models: List[ModelInfo] = [
        ModelInfo(
            id="default",
            name="Default Model",
            context_window=128000,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="gpt-4o",
            name="GPT-4o",
            context_window=128000,
            max_output_tokens=16384,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            context_window=128000,
            max_output_tokens=16384,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        ),
        ModelInfo(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            context_window=16385,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
    ]
