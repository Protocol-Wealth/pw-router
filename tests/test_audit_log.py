# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for audit logging and request IDs."""

import json

from pw_router.audit_log import generate_request_id, log_auth_failure, log_request


class TestGenerateRequestId:
    def test_returns_string(self):
        rid = generate_request_id()
        assert isinstance(rid, str)
        assert len(rid) == 16

    def test_unique(self):
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100


class TestLogRequest:
    def test_emits_json(self, caplog):
        with caplog.at_level("INFO", logger="pw_router.audit"):
            log_request(
                request_id="abc123",
                client_name="test-client",
                model="claude-sonnet",
                provider="anthropic",
                status="ok",
                latency_ms=450.123,
                prompt_tokens=100,
                completion_tokens=50,
            )
        assert len(caplog.records) == 1
        entry = json.loads(caplog.records[0].message)
        assert entry["event"] == "llm_request"
        assert entry["request_id"] == "abc123"
        assert entry["client"] == "test-client"
        assert entry["model"] == "claude-sonnet"
        assert entry["status"] == "ok"
        assert entry["latency_ms"] == 450.1
        assert entry["prompt_tokens"] == 100
        assert entry["total_tokens"] == 150

    def test_error_field(self, caplog):
        with caplog.at_level("INFO", logger="pw_router.audit"):
            log_request(
                request_id="err123",
                client_name="c",
                model="m",
                provider="p",
                status="provider_error",
                latency_ms=100,
                error="status_500",
            )
        entry = json.loads(caplog.records[0].message)
        assert entry["error"] == "status_500"

    def test_stream_flag(self, caplog):
        with caplog.at_level("INFO", logger="pw_router.audit"):
            log_request(
                request_id="s123",
                client_name="c",
                model="m",
                provider="p",
                status="streaming",
                latency_ms=0,
                stream=True,
            )
        entry = json.loads(caplog.records[0].message)
        assert entry["stream"] is True


class TestLogAuthFailure:
    def test_emits_warning(self, caplog):
        with caplog.at_level("WARNING", logger="pw_router.audit"):
            log_auth_failure(
                request_id="auth123",
                reason="invalid_key",
                remote_ip="1.2.3.4",
            )
        assert len(caplog.records) == 1
        entry = json.loads(caplog.records[0].message)
        assert entry["event"] == "auth_failure"
        assert entry["reason"] == "invalid_key"
        assert entry["remote_ip"] == "1.2.3.4"
