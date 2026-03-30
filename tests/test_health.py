# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for health check loop."""


import httpx
import pytest
import respx

from pw_router.providers import OpenAIAdapter
from pw_router.router import CircuitBreaker, CircuitState


class TestHealthCheckLoop:
    @pytest.mark.asyncio
    @respx.mock
    async def test_healthy_endpoint_stays_closed(self):
        respx.get("https://api.openai.com/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            cb = CircuitBreaker(unhealthy_threshold=3)
            model_config = {
                "base_url": "https://api.openai.com/v1",
                "api_key": "fake",
                "check_timeout_seconds": 5,
            }

            healthy = await adapter.health_check(model_config)
            assert healthy is True
            cb.record_success()
            assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    @respx.mock
    async def test_unhealthy_endpoint_opens_circuit(self):
        respx.get("https://api.openai.com/v1/models").mock(
            return_value=httpx.Response(500)
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            cb = CircuitBreaker(unhealthy_threshold=2)
            model_config = {
                "base_url": "https://api.openai.com/v1",
                "api_key": "fake",
                "check_timeout_seconds": 5,
            }

            for _ in range(2):
                healthy = await adapter.health_check(model_config)
                assert healthy is False
                cb.record_failure()

            assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_counts_as_failure(self):
        respx.get("https://api.openai.com/v1/models").mock(
            side_effect=httpx.ConnectError("timeout")
        )

        async with httpx.AsyncClient() as client:
            adapter = OpenAIAdapter(client)
            model_config = {
                "base_url": "https://api.openai.com/v1",
                "api_key": "fake",
                "check_timeout_seconds": 1,
            }

            healthy = await adapter.health_check(model_config)
            assert healthy is False

    @pytest.mark.asyncio
    async def test_health_loop_skips_when_interval_zero(self):
        from pw_router.health import health_check_loop

        config = {"health": {"check_interval_seconds": 0}}
        # Should return immediately without error
        await health_check_loop({}, {}, config)
