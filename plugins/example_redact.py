# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""
Example PII redaction middleware plugin for pw-router.

Scans request content for PII before sending to model provider.
If PII is detected, tags the request as "client-data" so the router
sends it to self-hosted models only.

Configure in config.yaml:
  middleware:
    pre_request:
      - plugin: "plugins.example_redact"
        config:
          endpoint: "${PW_REDACT_URL}"
          api_key: "${PW_REDACT_API_KEY}"
"""

import httpx

from pw_router.middleware import MiddlewareContext, MiddlewareResult


async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    """Scan request for PII via external redaction service."""
    endpoint = ctx.config.get("endpoint")
    api_key = ctx.config.get("api_key")

    if not endpoint:
        return MiddlewareResult(allow=True)

    messages = ctx.request_body.get("messages", [])
    full_text = " ".join(
        m.get("content", "") for m in messages if isinstance(m.get("content"), str)
    )

    if not full_text.strip():
        return MiddlewareResult(allow=True)

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = await http.post(
                f"{endpoint}/v1/detect",
                json={"text": full_text, "context": "general"},
                headers=headers,
            )
            resp.raise_for_status()
            result = resp.json()

        entities = result.get("entities", [])
        if entities:
            ctx.tags.add("client-data")
            ctx.metadata["pii_entities_count"] = len(entities)
            ctx.metadata["pii_entity_types"] = list({e["entity_type"] for e in entities})

    except Exception:
        # Redaction service down: fail open but tag for caution
        ctx.tags.add("client-data")
        ctx.metadata["pii_check_failed"] = True

    return MiddlewareResult(allow=True)
