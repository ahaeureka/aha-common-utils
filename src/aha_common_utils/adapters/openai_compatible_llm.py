"""OpenAI-compatible chat completions adapter for JSON responses."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

import httpx

from aha_common_utils.ports.llm_provider import LLMProviderPort
from aha_common_utils.ports.types import JsonObject, LLMContent, LLMMessage
from aha_common_utils.register import ProviderRegistry


@ProviderRegistry.register("openai-compatible", singleton=False)
class OpenAICompatibleLLMProvider(LLMProviderPort):
    """LLM provider for OpenAI-compatible ``/chat/completions`` APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.request_timeout_seconds = request_timeout_seconds
        self._client = http_client or httpx.AsyncClient(timeout=request_timeout_seconds)
        self._owns_client = http_client is None

    async def complete_json(
        self,
        *,
        messages: list[LLMMessage],
        schema: type[Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> JsonObject:
        """Request a chat completion and parse its content as a JSON object."""
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [self._message_to_payload(message) for message in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if schema is not None:
            payload["response_format"] = self._schema_to_response_format(schema)

        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        response.raise_for_status()
        content = self._extract_content(response.json())
        parsed = json.loads(self._strip_json_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("LLM response content must be a JSON object")
        return parsed

    async def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    def _message_to_payload(self, message: LLMMessage) -> dict[str, object]:
        return {"role": message.role, "content": self._content_to_payload(message.content)}

    def _content_to_payload(self, content: LLMContent) -> object:
        if isinstance(content, str):
            return content
        payload: list[object] = []
        for block in content:
            if is_dataclass(block):
                payload.append(asdict(block))
            else:
                payload.append(block)
        return payload

    def _schema_to_response_format(self, schema: type[Any]) -> dict[str, object]:
        if hasattr(schema, "model_json_schema"):
            json_schema = schema.model_json_schema()
        elif hasattr(schema, "schema"):
            json_schema = schema.schema()
        else:
            json_schema = schema
        return {
            "type": "json_schema",
            "json_schema": {
                "name": getattr(schema, "__name__", "response"),
                "schema": json_schema,
            },
        }

    def _extract_content(self, response_payload: object) -> str:
        if not isinstance(response_payload, dict):
            raise ValueError("LLM response payload must be a JSON object")
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM response payload is missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ValueError("LLM response choice must be a JSON object")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("LLM response choice is missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("LLM response message content must be a string")
        return content

    def _strip_json_fence(self, content: str) -> str:
        stripped = content.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
