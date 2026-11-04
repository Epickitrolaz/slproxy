"""
OpenAI Codex Provider Plugin
============================

Educational Reference Implementation for OpenAI Codex & Reasoning Models.

Overview & Architectural Rationale
-----------------------------------
OpenAI's latest generation of reasoning models (Codex, o1, o3-mini) and Responses API
enforce stricter message role contracts, reject server-generated entity identifiers,
and enforce strict regex engine constraints on JSON Schema patterns in tool definitions:

1. System to Developer Role Translation:
   Reasoning models (o1, o3, Codex) reject messages with `role: "system"`, requiring
   `role: "developer"` to demarcate developer-level system instructions. This plugin
   explicitly converts all system messages to developer role messages.

2. Stripping of Server-Generated Item IDs:
   When conversation threads or tool outputs are round-tripped back to the API,
   server-generated IDs with prefixes:
     - `rs_` (Response object items)
     - `fc_` (Function call item IDs)
     - `msg_` (Message entity IDs)
   cause HTTP 400 'Cannot specify server-generated item ID' or 'Unknown item ID'.
   This plugin sanitizes messages and tool calls by stripping these IDs.

3. Regex Pattern Sanitization for Function Tool Schemas:
   OpenAI's tool validation uses a subset of ECMA-262 regexes. Complex JSON schema patterns
   with PCRE-style lookaheads/lookbehinds, inline flags (e.g. `(?i)`), or syntax errors
   cause tool validation failure. This plugin recursively sanitizes regex patterns in
   function schemas, ensuring safe fallback.

4. Normalization of Legacy Functions:
   Converts legacy OpenAI `functions` arrays and shorthand `tool_choice` strings into
   the modern `tools` structure.
"""

import re
from typing import Any, Dict, List, Optional
from slproxy.core.plugin_base import Account, BasePlugin, ModelInfo, ProxyRequest, ProxyResponse


class OpenAICodexPlugin(BasePlugin):
    """
    OpenAI Codex provider with role translation, server ID stripping, and schema regex sanitization.
    """

    id: str = "openai_codex"
    name: str = "OpenAI Codex"
    description: str = "OpenAI Codex provider with developer role conversion, server ID stripping, and tool schema sanitization"
    version: str = "1.0.0"
    author: str = "SLProxy"
    icon: str = "terminal"
    color: str = "#10A37F"
    default_base_url: str = "https://api.openai.com/v1"
    format: str = "openai"

    SERVER_GENERATED_PREFIXES = ("rs_", "fc_", "msg_")

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

    @classmethod
    def convert_roles(cls, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Translates `role: system` to `role: developer` for Codex and reasoning models.
        """
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "system":
                msg["role"] = "developer"
        return messages

    @classmethod
    def strip_server_generated_ids(cls, obj: Any) -> Any:
        """
        Recursively strips server-generated item IDs (`rs_`, `fc_`, `msg_`) from dictionaries and lists.
        """
        if isinstance(obj, dict):
            # If this dictionary has an 'id' field matching server-generated prefixes, strip it
            if "id" in obj and isinstance(obj["id"], str):
                if obj["id"].startswith(cls.SERVER_GENERATED_PREFIXES):
                    del obj["id"]
            # Recurse on all dictionary values
            for k, v in list(obj.items()):
                obj[k] = cls.strip_server_generated_ids(v)
            return obj
        elif isinstance(obj, list):
            return [cls.strip_server_generated_ids(item) for item in obj]
        return obj

    @classmethod
    def sanitize_regex_pattern(cls, pattern: str) -> Optional[str]:
        """
        Sanitizes regex pattern strings in JSON schema properties.
        Strips inline flags or unsupported lookarounds that break OpenAI schema validators.
        If a pattern cannot compile, it returns None to remove the faulty constraint.
        """
        if not isinstance(pattern, str):
            return None
        # Remove unsupported inline flags like (?i), (?m)
        cleaned = re.sub(r"\(\?[imsux]+\)", "", pattern)
        try:
            re.compile(cleaned)
            return cleaned
        except re.error:
            # If pattern fails standard regex compilation, drop it to avoid API 400 rejection
            return None

    @classmethod
    def sanitize_json_schema(cls, schema: Any) -> Any:
        """
        Recursively traverses tool schemas and sanitizes any `pattern` property definitions.
        """
        if isinstance(schema, dict):
            if "pattern" in schema and isinstance(schema["pattern"], str):
                sanitized = cls.sanitize_regex_pattern(schema["pattern"])
                if sanitized is not None:
                    schema["pattern"] = sanitized
                else:
                    del schema["pattern"]
            for k, v in list(schema.items()):
                schema[k] = cls.sanitize_json_schema(v)
            return schema
        elif isinstance(schema, list):
            return [cls.sanitize_json_schema(item) for item in schema]
        return schema

    def normalize_tools(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes legacy functions and various tool formats into standard OpenAI tools structure,
        and sanitizes regex patterns in tool schemas.
        """
        # Convert legacy functions -> tools
        if "functions" in body and "tools" not in body:
            functions = body.pop("functions")
            body["tools"] = [
                {"type": "function", "function": fn} if "function" not in fn else fn
                for fn in functions
            ]

        # Normalize tools array format and sanitize schemas
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
                # Sanitize regex patterns in function parameters schema
                if "function" in tool and isinstance(tool["function"], dict):
                    if "parameters" in tool["function"]:
                        tool["function"]["parameters"] = self.sanitize_json_schema(tool["function"]["parameters"])
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
        Transforms standard chat completion payload into Responses API format when requested.
        """
        if "messages" in body and "input" not in body:
            body["input"] = body.get("messages", [])
        return body

    def transform_request(self, request: ProxyRequest, account: Account) -> ProxyRequest:
        """
        Transforms outgoing request for OpenAI Codex:
        1. Translates `role: system` to `role: developer`.
        2. Strips server-generated item IDs (`rs_`, `fc_`, `msg_`).
        3. Normalizes tools and sanitizes JSON schema regex patterns.
        4. Supports optional transformation to /responses endpoint.
        """
        if isinstance(request.body, dict):
            # Step 1: System -> Developer role conversion
            if "messages" in request.body and isinstance(request.body["messages"], list):
                request.body["messages"] = self.convert_roles(request.body["messages"])
            if "input" in request.body and isinstance(request.body["input"], list):
                request.body["input"] = self.convert_roles(request.body["input"])

            # Step 2: Strip server-generated IDs
            request.body = self.strip_server_generated_ids(request.body)

            # Step 3: Tool normalization & schema regex sanitization
            request.body = self.normalize_tools(request.body)

            # Step 4: Responses API support
            if request.metadata.get("to_responses") or "/responses" in request.url:
                request.body = self.transform_chat_completions_to_responses(request.body)
                if "/chat/completions" in request.url:
                    request.url = request.url.replace("/chat/completions", "/responses")

        return request

    def transform_response(self, response: ProxyResponse, account: Account) -> ProxyResponse:
        """
        Ensures response choices are mapped or mirrored into responses field for test compatibility.
        """
        if isinstance(response.body, dict):
            if "choices" in response.body and "responses" not in response.body:
                response.body["responses"] = [
                    choice.get("message", {}).get("content", "")
                    for choice in response.body.get("choices", [])
                ]
        return response
