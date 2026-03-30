# Architecture

This document covers pw-router's internal architecture in detail. For a high-level overview, see the [README](../README.md).

## Design Principles

1. **Minimal** — ~1,000 lines of core. No magic, no bloat.
2. **Auditable** — A compliance officer can read the entire codebase in an afternoon.
3. **Stateless** — No database. Config from YAML. Circuit state in-memory (resets on restart).
4. **Pluggable** — All opinions about compliance, PII, auth go in middleware plugins, not core.
5. **Supply-chain-safe** — 4 runtime dependencies, all well-established packages.

## Request Flow

```
1. Client sends OpenAI-format request with Authorization: Bearer <key>
2. server.py validates API key via constant-time comparison
3. server.py extracts client identity + allowed model list
4. middleware.py runs pre_request hooks in order
   - Hooks can modify request_body, add routing tags, or reject the request
5. router.py selects model:
   a. Explicit model in request → use it (if client-allowed)
   b. Tag matches a routing rule → select that chain
   c. No match → default_model
   d. If selected model's circuit breaker is OPEN → walk fallback chain
   e. If all models exhausted → 503
6. providers.py translates request to provider format (if needed)
7. providers.py sends request, handles streaming
8. providers.py normalizes response to OpenAI format
9. middleware.py runs post_response hooks in order
10. server.py returns response to client
```

## Module Map

```
pw_router/
├── server.py       FastAPI app, lifespan, routes, auth
├── router.py       RouterEngine: model selection, circuit breakers, fallback chains
├── providers.py    ProviderAdapter protocol + OpenAI, Anthropic, vLLM adapters
├── middleware.py    MiddlewareContext, MiddlewareResult, plugin loader
├── config.py       YAML loader with ${ENV_VAR} expansion, validation
├── health.py       Background async task: ping endpoints, update circuit state
├── models.py       Shared exception classes
└── __main__.py     CLI entry point (argparse + uvicorn)
```

## Server (server.py)

The FastAPI app uses a lifespan context manager to:
- Load config (from file or injected dict for tests)
- Create a shared `httpx.AsyncClient` (one client for all providers)
- Initialize provider adapters
- Initialize the router engine
- Load middleware plugins
- Start the background health check task

Auth is inline in each route handler via an `authenticate()` function that:
- Extracts the Bearer token from the Authorization header
- Walks `config.server.api_keys` comparing with `hmac.compare_digest`
- Sets `request.state.client_name` and `request.state.allowed_models`

The module-level `app = create_app()` allows both `uvicorn pw_router.server:app` and the test client to use the same factory.

## Router Engine (router.py)

### Model Selection

`RouterEngine.select_model()` returns the name of the model to use:

1. **Explicit model** — if the request specifies a model name, use it (after checking the client's allowlist). If the model is in a fallback chain and its circuit is open, walk the chain from that model's position.

2. **Tag-based routing** — iterate `routing.rules` in order. If any rule's `match.tag` is in the request's tag set, use that rule's `route_to_chain`.

3. **Default model** — use `routing.default_model`, including its fallback chain.

### Circuit Breaker

Each model gets its own `CircuitBreaker` instance. Three states:

- **CLOSED** — healthy. All requests pass through. If `unhealthy_threshold` consecutive failures occur, transitions to OPEN.
- **OPEN** — unhealthy. Requests skip this model immediately. After `cooldown_seconds`, transitions to HALF_OPEN.
- **HALF_OPEN** — testing. Allows one probe request. Success → CLOSED. Failure → OPEN.

Circuit breakers are updated by:
- The request path (success/failure after provider call)
- The background health check loop

State is in-memory. Resets to CLOSED on restart. This is the safe default — a restart clears transient failures.

### Fallback Chains

Defined in `routing.fallback_chains`. When the selected model's circuit is open, the router walks the chain in order until it finds a model whose circuit allows traffic. If all are exhausted, returns 503.

## Provider Adapters (providers.py)

All adapters implement the `ProviderAdapter` protocol:

```python
class ProviderAdapter(Protocol):
    async def chat_completion(
        self, body: dict, model_config: dict, *, stream: bool = False
    ) -> dict | AsyncIterator[str]: ...

    async def health_check(self, model_config: dict) -> bool: ...
```

### OpenAIAdapter

Pass-through. Overrides `base_url` and auth header, forwards the request as-is.

Streaming: uses `httpx` streaming to forward SSE lines from the provider.

Health check: `GET /models` at the provider's base URL.

### AnthropicAdapter

Translates between OpenAI and Anthropic formats:

**Request translation (OpenAI → Anthropic):**
- System messages extracted and sent as top-level `system` field
- `max_tokens` is required in Anthropic API (defaults to 4096)
- `stop` → `stop_sequences`
- `temperature`, `top_p` passed through

**Response translation (Anthropic → OpenAI):**
- `content[].text` → `choices[0].message.content`
- `stop_reason` mapped: `end_turn`/`stop_sequence` → `stop`, `max_tokens` → `length`
- `usage.input_tokens` / `output_tokens` → `prompt_tokens` / `completion_tokens`

**Streaming translation:**
- Anthropic SSE events (`message_start`, `content_block_delta`, `message_delta`, `message_stop`) are translated to OpenAI chunk format on the fly
- Each chunk is re-serialized as an OpenAI-format SSE line

### VLLMAdapter

Extends `OpenAIAdapter` — vLLM endpoints are OpenAI-compatible, so no translation needed. Only the `base_url` differs.

## Middleware (middleware.py)

The plugin system loads Python modules dynamically via `importlib.import_module`. Each plugin module is expected to export `pre_request` and/or `post_response` async functions.

Plugins are loaded once at startup. Each hook is paired with its config dict from the YAML file.

Hooks execute in the order they appear in config. A pre-request hook returning `allow=False` short-circuits the pipeline — the request is rejected and no further hooks run.

## Health Checks (health.py)

A single background `asyncio` task pings every model endpoint at `check_interval_seconds`. Uses each adapter's `health_check()` method. Updates the model's circuit breaker state based on results.

Timeout failures and connection errors are treated as failures.

## Config (config.py)

Loads YAML, recursively expands `${ENV_VAR}` patterns, then validates:
- `server` section exists with at least one API key
- `models` section exists with at least one model
- `routing` section exists with a `default_model` that references a defined model
- All models have a valid `provider`

Missing env vars raise `ValueError` with a clear message at startup (fail fast, not at request time).

## Adding a Provider

1. Create a new adapter class in `providers.py` implementing `ProviderAdapter`
2. Register it in `create_adapter()`
3. Add the provider name to `valid_providers` in `config.py`
4. Write tests with mocked HTTP in `tests/test_providers.py`

A typical OpenAI-compatible adapter is ~5 lines (subclass `OpenAIAdapter`). A format-translating adapter like Anthropic is ~150 lines.
