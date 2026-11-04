"""
OpenAI Codex Provider Plugin
"""

from typing import Any, Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest, ProxyResponse


class OpenAICodexPlugin(BasePlugin):
    id: str = "openai_codex"
    name: str = "OpenAI Codex"
    description: str = "OpenAI Codex provider with chat completion transformation and tool normalization"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "terminal"
    color: str = "#10A37F"
    default_base_url: str = "https://api.openai.com/v1"
    format: str = "openai"

    models: List[ModelInfo] = [
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
            id="o3-mini",
            name="o3-mini",
            context_window=200000,
            max_output_tokens=100000,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
        ModelInfo(
            id="codex",
            name="OpenAI Codex",
            context_window=8192,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
        ),
        ModelInfo(
            id="code-davinci-002",
            name="Code Davinci 002",
            context_window=8192,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_tools=False,
            supports_vision=False,
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
    ]

    def normalize_tools(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes legacy functions and various tool formats into standard OpenAI tools structure.
        """
        # Convert legacy functions -> tools
        if "functions" in body and "tools" not in body:
            functions = body.pop("functions")
            body["tools"] = [
                {"type": "function", "function": fn} if "function" not in fn else fn
                for fn in functions
            ]

        # Normalize tools array format
        if "tools" in body and isinstance(body["tools"], list):
            normalized = []
            for tool in body["tools"]:
                if not isinstance(tool, dict):
                    continue
                if "type" not in tool:
                    tool["type"] = "function"
                if "function" not in tool and "name" in tool:
                    tool = {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {}),
                        },
                    }
                normalized.append(tool)
            body["tools"] = normalized

        # Normalize tool_choice if named function
        if "tool_choice" in body:
            choice = body["tool_choice"]
            if isinstance(choice, str) and choice not in ("none", "auto", "required"):
                body["tool_choice"] = {
                    "type": "function",
                    "function": {"name": choice},
                }

        return body

    def transform_chat_completions_to_responses(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms standard chat completion payload into Responses API format when needed.
        """
        if "messages" in body and "input" not in body:
            body["input"] = body.get("messages", [])
        return body

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        if isinstance(request.body, dict):
            request.body = self.normalize_tools(request.body)

            if request.metadata.get("to_responses") or "/responses" in request.url:
                request.body = self.transform_chat_completions_to_responses(request.body)
                if "/chat/completions" in request.url:
                    request.url = request.url.replace("/chat/completions", "/responses")

        return request

    def transform_response(self, response: ProxyResponse, account: Account) -> ProxyResponse:
        if isinstance(response.body, dict):
            # If response contains choices, also mirror or format into responses field if requested
            if "choices" in response.body and "responses" not in response.body:
                response.body["responses"] = [
                    choice.get("message", {}).get("content", "")
                    for choice in response.body.get("choices", [])
                ]
        return response
