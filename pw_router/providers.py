# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Provider adapters: OpenAI, Anthropic, vLLM."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Protocol
from uuid import uuid4

import httpx


def _map_stop_reason(stop_reason: str | None) -> str:
    """Map Anthropic stop_reason to OpenAI finish_reason."""
    if stop_reason in ("end_turn", "stop_sequence"):
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    return "stop"


class ProviderAdapter(Protocol):
    async def chat_completion(
        self, body: dict, model_config: dict, *, stream: bool = False
    ) -> dict | AsyncIterator[str]: ...

    async def health_check(self, model_config: dict) -> bool: ...


class OpenAIAdapter:
    """Adapter for OpenAI-compatible APIs (pass-through)."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def chat_completion(
        self, body: dict, model_config: dict, *, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        base_url = model_config.get("base_url", "https://api.openai.com/v1")
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {model_config.get('api_key', '')}"}
        timeout = model_config.get("timeout_seconds", 120)

        payload = {**body, "model": model_config["model"]}
        if stream:
            payload["stream"] = True
            return self._stream_response(url, payload, headers, timeout)

        response = await self.client.post(
            url, json=payload, headers=headers, timeout=timeout
        )
        response.raise_for_status()
        return response.json()

    async def _stream_response(
        self, url: str, payload: dict, headers: dict, timeout: float
    ) -> AsyncIterator[str]:
        request = self.client.build_request(
            "POST", url, json=payload, headers=headers, timeout=timeout
        )
        response = await self.client.send(request, stream=True)
        try:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if line:
                    yield f"{line}\n\n"
        finally:
            await response.aclose()

    async def health_check(self, model_config: dict) -> bool:
        base_url = model_config.get("base_url", "https://api.openai.com/v1")
        headers = {"Authorization": f"Bearer {model_config.get('api_key', '')}"}
        timeout = model_config.get("check_timeout_seconds", 5)
        try:
            resp = await self.client.get(
                f"{base_url}/models", headers=headers, timeout=timeout
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False


class AnthropicAdapter:
    """Adapter that translates OpenAI format <-> Anthropic Messages API."""

    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    def _to_anthropic(self, body: dict, model_config: dict) -> dict:
        """Convert OpenAI-format request to Anthropic format."""
        messages = body.get("messages", [])
        system = None
        filtered: list[dict] = []

        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content", "")
            else:
                filtered.append({"role": msg["role"], "content": msg.get("content", "")})

        result: dict = {
            "model": model_config["model"],
            "messages": filtered,
            "max_tokens": body.get("max_tokens", 4096),
        }
        if system:
            result["system"] = system
        if "temperature" in body:
            result["temperature"] = body["temperature"]
        if "top_p" in body:
            result["top_p"] = body["top_p"]
        if "stop" in body:
            stop = body["stop"]
            result["stop_sequences"] = stop if isinstance(stop, list) else [stop]
        return result

    def _from_anthropic(self, data: dict, model_alias: str) -> dict:
        """Convert Anthropic response to OpenAI format."""
        content_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block.get("text", "")

        input_tokens = data.get("usage", {}).get("input_tokens", 0)
        output_tokens = data.get("usage", {}).get("output_tokens", 0)

        return {
            "id": f"chatcmpl-{data.get('id', uuid4().hex[:12])}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_alias,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content_text},
                    "finish_reason": _map_stop_reason(data.get("stop_reason")),
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }

    def _anthropic_headers(self, model_config: dict) -> dict:
        return {
            "x-api-key": model_config.get("api_key", ""),
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def chat_completion(
        self, body: dict, model_config: dict, *, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        base_url = model_config.get("base_url", "https://api.anthropic.com")
        url = f"{base_url}/v1/messages"
        headers = self._anthropic_headers(model_config)
        timeout = model_config.get("timeout_seconds", 120)

        payload = self._to_anthropic(body, model_config)
        model_alias = body.get("model", model_config.get("model", ""))

        if stream:
            payload["stream"] = True
            return self._stream_response(url, payload, headers, model_alias, timeout)

        response = await self.client.post(
            url, json=payload, headers=headers, timeout=timeout
        )
        response.raise_for_status()
        return self._from_anthropic(response.json(), model_alias)

    async def _stream_response(
        self,
        url: str,
        payload: dict,
        headers: dict,
        model_alias: str,
        timeout: float,
    ) -> AsyncIterator[str]:
        request = self.client.build_request(
            "POST", url, json=payload, headers=headers, timeout=timeout
        )
        response = await self.client.send(request, stream=True)
        try:
            response.raise_for_status()
            msg_id = f"chatcmpl-{uuid4().hex[:12]}"
            created = int(time.time())
            current_event: str | None = None

            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event: "):
                    current_event = line[7:]
                    continue
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", current_event)

                if event_type == "message_start":
                    chunk = {
                        "id": msg_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_alias,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant"},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

                elif event_type == "content_block_delta":
                    text = data.get("delta", {}).get("text", "")
                    if text:
                        chunk = {
                            "id": msg_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model_alias,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"

                elif event_type == "message_delta":
                    stop_reason = data.get("delta", {}).get("stop_reason")
                    chunk = {
                        "id": msg_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_alias,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": _map_stop_reason(stop_reason),
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

                elif event_type == "message_stop":
                    yield "data: [DONE]\n\n"
        finally:
            await response.aclose()

    async def health_check(self, model_config: dict) -> bool:
        base_url = model_config.get("base_url", "https://api.anthropic.com")
        headers = self._anthropic_headers(model_config)
        timeout = model_config.get("check_timeout_seconds", 5)
        try:
            resp = await self.client.get(
                f"{base_url}/v1/models", headers=headers, timeout=timeout
            )
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False


class VLLMAdapter(OpenAIAdapter):
    """Adapter for vLLM/RunPod endpoints (OpenAI-compatible)."""


def create_adapter(provider: str, client: httpx.AsyncClient) -> ProviderAdapter:
    """Factory: create the right adapter for a provider type."""
    adapters = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "vllm": VLLMAdapter,
    }
    cls = adapters.get(provider)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider}")
    return cls(client)
