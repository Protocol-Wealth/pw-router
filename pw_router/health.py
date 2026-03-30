# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Background health check loop for model endpoints."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("pw_router.health")


async def health_check_loop(
    adapters: dict,
    circuits: dict,
    config: dict,
) -> None:
    """Background task: ping each model endpoint at configured interval.

    Updates circuit breaker state based on results.
    """
    health_config = config.get("health", {})
    interval = health_config.get("check_interval_seconds", 30)
    timeout = health_config.get("check_timeout_seconds", 5)

    if interval <= 0:
        return

    models_config = config.get("models", {})

    while True:
        for model_name, adapter in adapters.items():
            model_cfg = models_config.get(model_name, {})
            model_cfg["check_timeout_seconds"] = timeout
            try:
                healthy = await asyncio.wait_for(
                    adapter.health_check(model_cfg),
                    timeout=timeout,
                )
                if healthy:
                    circuits[model_name].record_success()
                else:
                    circuits[model_name].record_failure()
            except (TimeoutError, Exception) as e:
                logger.warning("Health check failed for %s: %s", model_name, e)
                circuits[model_name].record_failure()

        await asyncio.sleep(interval)
