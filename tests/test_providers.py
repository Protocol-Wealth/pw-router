# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for provider adapters with mocked HTTP via respx."""

import json

import httpx
import pytest
import respx

from pw_router.providers import (
    AnthropicAdapter,
    OpenAIAdapter,
    VLLMAdapter,
    _map_stop_reason,
    create_adapter,
)
from tests.conftest import ANTHROPIC_CHAT_RESPONSE, OPENAI_CHAT_RESPONSE


class TestMapStopReason:
    def test_end_turn(self):
        assert _map_stop_reason("end_turn") == "stop"

    def test_stop_sequence(self):
        assert _map_stop_reason("stop_sequence") == "stop"

    def test_max_tokens(self):
        assert _map_stop_reason("max_tokens") == "length"

    def test_none(self):
        assert _map_stop_reason(None) == "stop"


class TestOpenAIAdapter:
    @pytest.mark.asyncio
    @respx.mock
    async def test_non_streaming(self):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            result = await adapter.chat_completion(
                {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                {
                    "model": "gpt-4o",
                    "api_key": "fake",
                    "base_url": "https://api.openai.com/v1",
                    "timeout_seconds": 30,
                },
            )

        assert result["choices"][0]["message"]["content"] == "Hello from the test!"
        assert result["usage"]["total_tokens"] == 15

    @pytest.mark.asyncio
    @respx.mock
    async def test_streaming(self):
        sse_lines = (
            'data: {"id":"chatcmpl-s1","object":"chat.completion.chunk",'
            '"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
            'data: {"id":"chatcmpl-s1","object":"chat.completion.chunk",'
            '"choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}\n\n'
            "data: [DONE]\n\n"
        )
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=sse_lines.encode(),
                headers={"content-type": "text/event-stream"},
            )
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            stream = await adapter.chat_completion(
                {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                {
                    "model": "gpt-4o",
                    "api_key": "fake",
                    "base_url": "https://api.openai.com/v1",
                    "timeout_seconds": 30,
                },
                stream=True,
            )

            chunks = []
            async for chunk in stream:
                chunks.append(chunk)

        assert len(chunks) >= 2
        assert "data:" in chunks[0]
        assert "[DONE]" in chunks[-1]

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_healthy(self):
        respx.get("https://api.openai.com/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            healthy = await adapter.health_check(
                {"base_url": "https://api.openai.com/v1", "api_key": "fake"}
            )

        assert healthy is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_unhealthy(self):
        respx.get("https://api.openai.com/v1/models").mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            healthy = await adapter.health_check(
                {"base_url": "https://api.openai.com/v1", "api_key": "fake"}
            )

        assert healthy is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_handling(self):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            with pytest.raises(httpx.ReadTimeout):
                await adapter.chat_completion(
                    {"model": "gpt-4o", "messages": []},
                    {
                        "model": "gpt-4o",
                        "api_key": "fake",
                        "base_url": "https://api.openai.com/v1",
                        "timeout_seconds": 1,
                    },
                )

    @pytest.mark.asyncio
    @respx.mock
    async def test_connection_error(self):
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            with pytest.raises(httpx.ConnectError):
                await adapter.chat_completion(
                    {"model": "gpt-4o", "messages": []},
                    {
                        "model": "gpt-4o",
                        "api_key": "fake",
                        "base_url": "https://api.openai.com/v1",
                        "timeout_seconds": 1,
                    },
                )


class TestAnthropicAdapter:
    @pytest.mark.asyncio
    @respx.mock
    async def test_request_translation(self):
        route = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=ANTHROPIC_CHAT_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            adapter = AnthropicAdapter(client)
            await adapter.chat_completion(
                {
                    "model": "claude-sonnet",
                    "messages": [
                        {"role": "system", "content": "Be helpful."},
                        {"role": "user", "content": "Hello"},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 200,
                },
                {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "fake-key",
                    "timeout_seconds": 30,
                },
            )

        # Verify the request was translated correctly
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["model"] == "claude-sonnet-4-20250514"
        assert sent_body["system"] == "Be helpful."
        assert sent_body["max_tokens"] == 200
        assert sent_body["temperature"] == 0.5
        # System message should NOT be in messages
        assert all(m["role"] != "system" for m in sent_body["messages"])

    @pytest.mark.asyncio
    @respx.mock
    async def test_response_translation(self):
        respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=ANTHROPIC_CHAT_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            adapter = AnthropicAdapter(client)
            result = await adapter.chat_completion(
                {"model": "claude-sonnet", "messages": [{"role": "user", "content": "Hi"}]},
                {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "fake-key",
                    "timeout_seconds": 30,
                },
            )

        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "Hello from Anthropic!"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["usage"]["total_tokens"] == 15

    @pytest.mark.asyncio
    @respx.mock
    async def test_default_max_tokens(self):
        route = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=ANTHROPIC_CHAT_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            adapter = AnthropicAdapter(client)
            await adapter.chat_completion(
                {"model": "claude", "messages": [{"role": "user", "content": "Hi"}]},
                {"model": "claude-sonnet-4-20250514", "api_key": "k", "timeout_seconds": 30},
            )

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["max_tokens"] == 4096

    @pytest.mark.asyncio
    @respx.mock
    async def test_anthropic_headers(self):
        route = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json=ANTHROPIC_CHAT_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            adapter = AnthropicAdapter(client)
            await adapter.chat_completion(
                {"model": "claude", "messages": [{"role": "user", "content": "Hi"}]},
                {"model": "claude-sonnet-4-20250514", "api_key": "test-key", "timeout_seconds": 30},
            )

        headers = route.calls[0].request.headers
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"


class TestVLLMAdapter:
    @pytest.mark.asyncio
    @respx.mock
    async def test_custom_base_url(self):
        respx.post("http://localhost:8000/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )

        async with httpx.AsyncClient() as client:
            adapter = VLLMAdapter(client)
            result = await adapter.chat_completion(
                {"model": "local", "messages": [{"role": "user", "content": "Hi"}]},
                {
                    "model": "meta-llama/Llama-3.1-70B-Instruct",
                    "api_key": "fake",
                    "base_url": "http://localhost:8000/v1",
                    "timeout_seconds": 30,
                },
            )

        assert result["choices"][0]["message"]["content"] == "Hello from the test!"


class TestCreateAdapter:
    def test_openai(self):
        client = httpx.AsyncClient()
        adapter = create_adapter("openai", client)
        assert isinstance(adapter, OpenAIAdapter)

    def test_anthropic(self):
        client = httpx.AsyncClient()
        adapter = create_adapter("anthropic", client)
        assert isinstance(adapter, AnthropicAdapter)

    def test_vllm(self):
        client = httpx.AsyncClient()
        adapter = create_adapter("vllm", client)
        assert isinstance(adapter, VLLMAdapter)

    def test_unknown_raises(self):
        client = httpx.AsyncClient()
        with pytest.raises(ValueError, match="Unknown provider"):
            create_adapter("magic", client)
