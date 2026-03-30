# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""
Example structured logging middleware plugin for pw-router.
Logs request metadata (NOT request/response bodies by default).
"""

import json
import logging

from pw_router.middleware import MiddlewareContext, MiddlewareResult

logger = logging.getLogger("pw_router.audit")


async def post_response(ctx: MiddlewareContext) -> MiddlewareResult:
    """Log request metadata after response is received."""
    log_entry = {
        "client": ctx.client_name,
        "model": ctx.model_used,
        "latency_ms": round(ctx.latency_ms, 1) if ctx.latency_ms else None,
        "tags": sorted(ctx.tags),
        "prompt_tokens": (ctx.response_body or {}).get("usage", {}).get("prompt_tokens"),
        "completion_tokens": (ctx.response_body or {}).get("usage", {}).get(
            "completion_tokens"
        ),
    }
    logger.info(json.dumps(log_entry))
    return MiddlewareResult(allow=True)
