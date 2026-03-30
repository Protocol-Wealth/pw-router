# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for model selection, circuit breaker, and fallback chains."""

import time

import pytest

from pw_router.models import AllModelsUnavailableError, ModelNotAllowedError, ModelNotFoundError
from pw_router.router import CircuitBreaker, CircuitState, RouterEngine, _is_allowed


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.should_allow() is True

    def test_opens_after_failures(self):
        cb = CircuitBreaker(unhealthy_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.should_allow() is False

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(unhealthy_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.should_allow() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success_from_half_open(self):
        cb = CircuitBreaker(unhealthy_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.should_allow()  # transitions to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_from_half_open(self):
        cb = CircuitBreaker(unhealthy_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.should_allow()  # HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(unhealthy_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED


class TestIsAllowed:
    def test_wildcard(self):
        assert _is_allowed("anything", ["*"]) is True

    def test_exact_match(self):
        assert _is_allowed("model-a", ["model-a", "model-b"]) is True

    def test_no_match(self):
        assert _is_allowed("model-c", ["model-a", "model-b"]) is False

    def test_glob_pattern(self):
        assert _is_allowed("local-llama", ["local-*"]) is True
        assert _is_allowed("remote-llama", ["local-*"]) is False


class TestRouterEngine:
    def test_select_explicit_model(self, sample_config):
        engine = RouterEngine(sample_config)
        model = engine.select_model("test-model", set(), ["*"])
        assert model == "test-model"

    def test_select_explicit_not_found(self, sample_config):
        engine = RouterEngine(sample_config)
        with pytest.raises(ModelNotFoundError):
            engine.select_model("nonexistent", set(), ["*"])

    def test_select_explicit_not_allowed(self, sample_config):
        engine = RouterEngine(sample_config)
        with pytest.raises(ModelNotAllowedError):
            engine.select_model("test-model", set(), ["local-*"])

    def test_select_default_model(self, sample_config):
        engine = RouterEngine(sample_config)
        model = engine.select_model(None, set(), ["*"])
        assert model == "test-model"

    def test_select_tag_match(self, sample_config):
        engine = RouterEngine(sample_config)
        model = engine.select_model(None, {"client-data"}, ["*"])
        assert model == "local-model"

    def test_fallback_on_circuit_open(self, sample_config):
        engine = RouterEngine(sample_config)
        # Open the test-model circuit
        for _ in range(3):
            engine.record_failure("test-model")
        assert engine.circuits["test-model"].state == CircuitState.OPEN

        model = engine.select_model(None, set(), ["*"])
        assert model == "local-model"

    def test_all_unhealthy_raises(self, sample_config):
        engine = RouterEngine(sample_config)
        # Open all circuits in the reasoning chain
        for name in ["test-model", "local-model"]:
            for _ in range(3):
                engine.record_failure(name)

        with pytest.raises(AllModelsUnavailableError):
            engine.select_model(None, set(), ["*"])

    def test_fallback_skips_disallowed(self, sample_config):
        engine = RouterEngine(sample_config)
        # Open test-model circuit
        for _ in range(3):
            engine.record_failure("test-model")

        # Restricted client only allowed local-*
        model = engine.select_model(None, set(), ["local-*"])
        assert model == "local-model"

    def test_record_success(self, sample_config):
        engine = RouterEngine(sample_config)
        engine.record_failure("test-model")
        engine.record_success("test-model")
        assert engine.circuits["test-model"].failure_count == 0

    def test_record_failure(self, sample_config):
        engine = RouterEngine(sample_config)
        engine.record_failure("test-model")
        assert engine.circuits["test-model"].failure_count == 1

    def test_explicit_model_fallback_on_open(self, sample_config):
        engine = RouterEngine(sample_config)
        # Open test-model circuit
        for _ in range(3):
            engine.record_failure("test-model")

        # Request test-model explicitly, should fall back
        model = engine.select_model("test-model", set(), ["*"])
        assert model == "local-model"
