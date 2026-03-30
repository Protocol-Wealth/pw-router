# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Structured JSON audit logging and request ID generation."""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

logger = logging.getLogger("pw_router.audit")


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return uuid4().hex[:16]


def log_request(
    *,
    request_id: str,
    client_name: str,
    model: str,
    provider: str,
    status: str,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    stream: bool = False,
    error: str | None = None,
) -> None:
    """Emit a structured JSON audit log line for a completed request."""
    entry = {
        "event": "llm_request",
        "ts": time.time(),
        "request_id": request_id,
        "client": client_name,
        "model": model,
        "provider": provider,
        "status": status,
        "latency_ms": round(latency_ms, 1),
        "stream": stream,
    }
    if prompt_tokens or completion_tokens:
        entry["prompt_tokens"] = prompt_tokens
        entry["completion_tokens"] = completion_tokens
        entry["total_tokens"] = prompt_tokens + completion_tokens
    if error:
        entry["error"] = error
    logger.info(json.dumps(entry, separators=(",", ":")))


def log_auth_failure(*, request_id: str, reason: str, remote_ip: str | None = None) -> None:
    """Log an authentication failure."""
    entry = {
        "event": "auth_failure",
        "ts": time.time(),
        "request_id": request_id,
        "reason": reason,
    }
    if remote_ip:
        entry["remote_ip"] = remote_ip
    logger.warning(json.dumps(entry, separators=(",", ":")))
