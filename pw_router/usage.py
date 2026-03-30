# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""In-memory usage tracking per client and model. Resets on restart."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class ModelUsage:
    """Token and request counters for a single model."""

    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0


@dataclass
class ClientUsage:
    """Per-client usage breakdown by model."""

    models: dict[str, ModelUsage] = field(default_factory=dict)

    def get_model(self, model: str) -> ModelUsage:
        if model not in self.models:
            self.models[model] = ModelUsage()
        return self.models[model]


class UsageTracker:
    """Thread-safe in-memory usage tracker. Resets on restart."""

    def __init__(self) -> None:
        self._clients: dict[str, ClientUsage] = {}
        self._lock = threading.Lock()
        self._start_time = time.monotonic()

    def record_request(
        self,
        client_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
    ) -> None:
        with self._lock:
            usage = self._get_client(client_name).get_model(model_name)
            usage.requests += 1
            usage.prompt_tokens += prompt_tokens
            usage.completion_tokens += completion_tokens
            usage.total_tokens += prompt_tokens + completion_tokens
            usage.total_latency_ms += latency_ms

    def record_error(self, client_name: str, model_name: str) -> None:
        with self._lock:
            self._get_client(client_name).get_model(model_name).errors += 1

    def record_stream_request(
        self,
        client_name: str,
        model_name: str,
    ) -> None:
        """Record a streaming request (tokens unknown until stream completes)."""
        with self._lock:
            self._get_client(client_name).get_model(model_name).requests += 1

    def snapshot(self) -> dict:
        """Return usage data as a JSON-serializable dict."""
        with self._lock:
            uptime = time.monotonic() - self._start_time
            totals = {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "errors": 0,
            }
            clients = {}
            for client_name, client_usage in self._clients.items():
                client_data: dict[str, dict] = {}
                for model_name, model_usage in client_usage.models.items():
                    client_data[model_name] = {
                        "requests": model_usage.requests,
                        "prompt_tokens": model_usage.prompt_tokens,
                        "completion_tokens": model_usage.completion_tokens,
                        "total_tokens": model_usage.total_tokens,
                        "errors": model_usage.errors,
                        "avg_latency_ms": (
                            round(model_usage.total_latency_ms / model_usage.requests, 1)
                            if model_usage.requests > 0
                            else 0
                        ),
                    }
                    totals["requests"] += model_usage.requests
                    totals["prompt_tokens"] += model_usage.prompt_tokens
                    totals["completion_tokens"] += model_usage.completion_tokens
                    totals["total_tokens"] += model_usage.total_tokens
                    totals["errors"] += model_usage.errors
                clients[client_name] = client_data

            return {
                "uptime_seconds": round(uptime),
                "totals": totals,
                "by_client": clients,
            }

    def _get_client(self, client_name: str) -> ClientUsage:
        if client_name not in self._clients:
            self._clients[client_name] = ClientUsage()
        return self._clients[client_name]
