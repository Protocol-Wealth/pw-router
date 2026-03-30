# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Shared test fixtures and mock data."""

import pytest


@pytest.fixture
def sample_config():
    """Minimal config for testing."""
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 8100,
            "api_keys": [
                {"key": "test-key-1", "name": "test-client", "allowed_models": ["*"]},
                {
                    "key": "test-key-2",
                    "name": "restricted",
                    "allowed_models": ["local-*"],
                },
            ],
        },
        "models": {
            "test-model": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "fake-key",
                "base_url": "https://api.openai.com/v1",
                "timeout_seconds": 30,
                "tags": ["external"],
            },
            "local-model": {
                "provider": "vllm",
                "model": "meta-llama/Llama-3.1-70B-Instruct",
                "api_key": "fake-key",
                "base_url": "http://localhost:8000/v1",
                "timeout_seconds": 30,
                "tags": ["self-hosted", "client-safe"],
            },
            "anthropic-model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "api_key": "fake-anthropic-key",
                "timeout_seconds": 30,
                "tags": ["external"],
            },
        },
        "routing": {
            "default_model": "test-model",
            "fallback_chains": {
                "reasoning": ["test-model", "local-model"],
                "client-safe": ["local-model"],
            },
            "rules": [
                {"match": {"tag": "client-data"}, "route_to_chain": "client-safe"},
            ],
        },
        "health": {
            "check_interval_seconds": 0,
            "unhealthy_threshold": 3,
            "healthy_threshold": 1,
            "check_timeout_seconds": 5,
        },
        "middleware": {"pre_request": [], "post_response": []},
        "logging": {"level": "INFO", "format": "json"},
    }


OPENAI_CHAT_RESPONSE = {
    "id": "chatcmpl-test123",
    "object": "chat.completion",
    "created": 1711000000,
    "model": "gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello from the test!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


ANTHROPIC_CHAT_RESPONSE = {
    "id": "msg_test123",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "Hello from Anthropic!"}],
    "model": "claude-sonnet-4-20250514",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


CHAT_REQUEST_BODY = {
    "model": "test-model",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Say hello."},
    ],
    "temperature": 0.7,
    "max_tokens": 100,
}
