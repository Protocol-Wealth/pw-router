# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Model selection, circuit breaker, and fallback chains."""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass
from enum import Enum

from pw_router.models import AllModelsUnavailableError, ModelNotAllowedError, ModelNotFoundError


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Per-model circuit breaker. In-memory, resets on restart."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    success_count: int = 0
    unhealthy_threshold: int = 3
    healthy_threshold: int = 1
    cooldown_seconds: float = 30.0

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.healthy_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        self.success_count = 0
        if self.failure_count >= self.unhealthy_threshold:
            self.state = CircuitState.OPEN

    def should_allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time > self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                return True
            return False
        # HALF_OPEN: allow probe
        return True


def _is_allowed(model_name: str, allowed_models: list[str]) -> bool:
    """Check if a model is allowed by client's allowlist (supports wildcards)."""
    return any(p == "*" or fnmatch.fnmatch(model_name, p) for p in allowed_models)


class RouterEngine:
    """Model selection engine with circuit breakers and fallback chains."""

    def __init__(self, config: dict):
        routing = config.get("routing", {})
        health = config.get("health", {})

        self.model_names: set[str] = set(config.get("models", {}).keys())
        self.default_model: str = routing.get("default_model", "")
        self.fallback_chains: dict[str, list[str]] = routing.get("fallback_chains", {})
        self.rules: list[dict] = routing.get("rules", [])

        threshold = health.get("unhealthy_threshold", 3)
        healthy_threshold = health.get("healthy_threshold", 1)
        cooldown = health.get("cooldown_seconds", health.get("check_interval_seconds", 30))
        if cooldown <= 0:
            cooldown = 30.0

        self.circuits: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(
                unhealthy_threshold=threshold,
                healthy_threshold=healthy_threshold,
                cooldown_seconds=float(cooldown),
            )
            for name in self.model_names
        }

    def select_model(
        self,
        requested_model: str | None,
        tags: set[str],
        allowed_models: list[str],
    ) -> str:
        """Select the best available model.

        Priority:
        1. Explicit model in request (must be client-allowed)
        2. First matching routing rule based on tags
        3. Default model
        4. Walk fallback chain if selected model's circuit is open

        Raises ModelNotFoundError, ModelNotAllowedError, or AllModelsUnavailableError.
        """
        if requested_model:
            if requested_model not in self.model_names:
                raise ModelNotFoundError(requested_model)
            if not _is_allowed(requested_model, allowed_models):
                raise ModelNotAllowedError(requested_model)

        candidates = self._resolve_candidates(requested_model, tags)

        for model in candidates:
            if not _is_allowed(model, allowed_models):
                continue
            cb = self.circuits.get(model)
            if cb is None or cb.should_allow():
                return model

        raise AllModelsUnavailableError()

    def _resolve_candidates(self, requested_model: str | None, tags: set[str]) -> list[str]:
        """Build ordered list of candidate models to try."""
        if requested_model:
            chain = self._find_chain(requested_model)
            if chain:
                idx = chain.index(requested_model)
                return chain[idx:]
            return [requested_model]

        # Check tag-based routing rules
        for rule in self.rules:
            match_tag = rule.get("match", {}).get("tag")
            if match_tag and match_tag in tags:
                chain_name = rule.get("route_to_chain")
                chain = self.fallback_chains.get(chain_name, [])
                if chain:
                    return list(chain)

        # Default model + its chain
        chain = self._find_chain(self.default_model)
        if chain:
            idx = chain.index(self.default_model)
            return chain[idx:]
        return [self.default_model]

    def _find_chain(self, model_name: str) -> list[str] | None:
        """Find a fallback chain containing the given model."""
        for chain in self.fallback_chains.values():
            if model_name in chain:
                return list(chain)
        return None

    def record_success(self, model_name: str) -> None:
        cb = self.circuits.get(model_name)
        if cb:
            cb.record_success()

    def record_failure(self, model_name: str) -> None:
        cb = self.circuits.get(model_name)
        if cb:
            cb.record_failure()
