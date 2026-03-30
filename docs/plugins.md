# Writing Plugins

pw-router's middleware system lets you add custom logic before and after every LLM request without modifying the core. Plugins are plain Python modules — no framework, no decorators, no registration boilerplate.

## Plugin Interface

A plugin is a Python module that exports one or both of these async functions:

```python
from pw_router.middleware import MiddlewareContext, MiddlewareResult

async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    """Called before the request is forwarded to the provider."""
    ...

async def post_response(ctx: MiddlewareContext) -> MiddlewareResult:
    """Called after the response is received from the provider."""
    ...
```

That's the entire interface.

## MiddlewareContext

The context object carries request/response data through the pipeline:

| Field | Type | Available | Mutable | Description |
|-------|------|-----------|---------|-------------|
| `request_body` | `dict` | Pre + Post | Yes | OpenAI-format request |
| `client_name` | `str` | Pre + Post | No | Authenticated client identity |
| `tags` | `set[str]` | Pre + Post | Yes | Routing tags — add to influence model selection |
| `metadata` | `dict` | Pre + Post | Yes | Pass data between pre and post hooks |
| `config` | `dict` | Pre + Post | No | Plugin-specific config from YAML |
| `response_body` | `dict \| None` | Post only | Yes | OpenAI-format response |
| `model_used` | `str \| None` | Post only | No | Actual model that handled the request |
| `latency_ms` | `float \| None` | Post only | No | Request latency in milliseconds |
| `provider` | `str \| None` | Post only | No | Provider name (openai, anthropic, vllm) |

## MiddlewareResult

Return this from your hook:

```python
@dataclass
class MiddlewareResult:
    allow: bool = True              # False = block the request/response
    error_message: str | None = None  # Returned to client if blocked
    status_code: int = 400          # HTTP status if blocked
```

## Configuration

Register plugins in `config.yaml`:

```yaml
middleware:
  pre_request:
    - plugin: "plugins.my_pii_scanner"
      config:
        scan_endpoint: "http://localhost:8080/v1/detect"
        api_key: "${SCANNER_API_KEY}"
  post_response:
    - plugin: "plugins.my_audit_logger"
      config:
        log_level: "info"
```

The `plugin` value is a Python dotted module path. The `config` dict is passed to your hook via `ctx.config`.

Hooks execute in the order listed. If any pre-request hook returns `allow=False`, the request is rejected immediately and subsequent hooks are skipped.

## Examples

### PII Detection + Tag-Based Routing

Scan for PII before sending to a model. If found, tag the request so the router sends it to self-hosted models only:

```python
# plugins/pii_scanner.py
from pw_router.middleware import MiddlewareContext, MiddlewareResult
import httpx

async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    endpoint = ctx.config.get("scan_endpoint")
    if not endpoint:
        return MiddlewareResult(allow=True)

    messages = ctx.request_body.get("messages", [])
    text = " ".join(
        m.get("content", "") for m in messages
        if isinstance(m.get("content"), str)
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(endpoint, json={"text": text})
            resp.raise_for_status()
            if resp.json().get("pii_detected"):
                ctx.tags.add("client-data")
    except Exception:
        # If scanner is down, fail safe — route to self-hosted
        ctx.tags.add("client-data")

    return MiddlewareResult(allow=True)
```

### Audit Logger

Log request metadata (not bodies) for compliance:

```python
# plugins/audit_logger.py
import json
import logging
from pw_router.middleware import MiddlewareContext, MiddlewareResult

logger = logging.getLogger("audit")

async def post_response(ctx: MiddlewareContext) -> MiddlewareResult:
    logger.info(json.dumps({
        "client": ctx.client_name,
        "model": ctx.model_used,
        "latency_ms": round(ctx.latency_ms, 1) if ctx.latency_ms else None,
        "tags": list(ctx.tags),
        "prompt_tokens": ctx.response_body.get("usage", {}).get("prompt_tokens"),
        "completion_tokens": ctx.response_body.get("usage", {}).get("completion_tokens"),
    }))
    return MiddlewareResult(allow=True)
```

### Request Blocker

Reject requests that match a pattern:

```python
# plugins/content_filter.py
from pw_router.middleware import MiddlewareContext, MiddlewareResult

BLOCKED_PATTERNS = ["DROP TABLE", "DELETE FROM"]

async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    messages = ctx.request_body.get("messages", [])
    text = " ".join(
        m.get("content", "").upper() for m in messages
        if isinstance(m.get("content"), str)
    )
    for pattern in BLOCKED_PATTERNS:
        if pattern in text:
            return MiddlewareResult(
                allow=False,
                error_message="Request blocked by content filter",
                status_code=403,
            )
    return MiddlewareResult(allow=True)
```

## Tips

- **Keep plugins stateless.** Don't store request data in module-level variables. Use `ctx.metadata` to pass data between pre and post hooks.
- **Fail open or fail closed — pick one and be explicit.** If your PII scanner is down, do you block all requests or route to self-hosted? Document the choice.
- **Don't create HTTP clients per-request.** If your plugin makes external calls, consider initializing a client once and reusing it.
- **Plugins run in the request path.** Keep them fast. Offload slow work (database writes, external API calls) to background tasks if latency matters.
