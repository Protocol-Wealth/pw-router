# CLAUDE.md — pw-router

> **Repository:** pw-router (PUBLIC — open source)
> **License:** MIT
> **GitHub:** github.com/Protocol-Wealth/pw-router
> **Purpose:** Minimal, auditable LLM routing gateway for regulated environments
> **Stack:** Python 3.12 · FastAPI · httpx · PyYAML · Fly.io
> **Status:** PRE-BUILD — this is the build specification
>
> **Open-source rationale:** pw-router is infrastructure, not proprietary business logic.
> A deliberately minimal LLM gateway whose entire core is auditable in an afternoon.
> The compliance plugins, client routing rules, and PW-specific middleware stay private.
> Publishing the router positions Protocol Wealth as a builder in the RIA-tech space
> and provides the industry with a supply-chain-safe alternative to LiteLLM.

---

## 0. OPEN-SOURCE GROUND RULES

### What goes in this repo (public):

* All routing logic, provider adapters, circuit breaker, health checks
* Middleware plugin system (pre/post request hooks)
* Example plugins (example_redact.py, example_logger.py)
* API server code, tests, documentation
* YAML config loader with env var expansion
* CLAUDE.md (this file — let people see how we build with AI)
* README.md with usage guide, architecture overview, and contribution guide
* Generic deployment examples (Docker, fly.toml.example)

### What NEVER goes in this repo:

* API keys, secrets, tokens, passwords (use env vars exclusively)
* Internal PW URLs (no nexusmcp.site, pwdashboard.com, protocolwealthllc.com in code)
* Client data, real model configs, production routing rules
* PW-specific middleware plugins (pw-redact integration, audit logging, RBAC)
* References to specific clients, advisors, or internal business processes
* AGENTS.md or ria.md (those are private governance docs)

### Deployment separation:

* **Public repo:** github.com/Protocol-Wealth/pw-router (code, tests, docs)
* **Private config:** Fly.io secrets, actual config.yaml, .env — managed outside the repo
* **config.example.yaml** in repo with placeholder values; actual config.yaml in .gitignore

### License header (every .py file):

```python
# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router
```

### Attribution notice (in README and LICENSE):

Architectural patterns (circuit breaker, fallback chains, health-check loops) are
informed by [Bifrost](https://github.com/maximhq/bifrost) (Apache 2.0, Maxim AI).
No code was copied; patterns were reimplemented in Python/FastAPI. Per Apache 2.0 §4,
this notice serves as attribution.

---

## 1. WHAT THIS SERVICE DOES

pw-router is a stateless LLM routing gateway that provides an OpenAI-compatible API
in front of multiple model providers. It routes requests based on model name, tags
(set by middleware), or fallback chains when a provider is unhealthy.

**Core flow:**

```
Client request (OpenAI format)
        │
        ▼
   pw-router /v1/chat/completions
   ├── Auth: validate API key, resolve client identity + allowed models
   ├── Pre-request middleware pipeline (pluggable hooks)
   │   └── Example: PII scan → tag request as "client-data"
   ├── Router engine:
   │   ├── Select model (explicit name, tag-matched chain, or default)
   │   ├── Check circuit breaker state
   │   └── Walk fallback chain if primary is unhealthy
   ├── Provider adapter:
   │   ├── Translate request format if needed (e.g., OpenAI → Anthropic)
   │   ├── Forward to provider endpoint
   │   └── Normalize response to OpenAI format
   ├── Post-response middleware pipeline (pluggable hooks)
   │   └── Example: scan response for PII, audit log
   └── Return OpenAI-format response to client
```

**Key principles:**

* **MINIMAL:** Core is ~950 lines across 6 files. 4 direct dependencies.
* **AUDITABLE:** A compliance officer can read the entire codebase in an afternoon.
* **STATELESS:** No database. Config from YAML. Circuit state in-memory (resets on restart).
* **PLUGGABLE:** All opinions about compliance, PII, auth go in middleware plugins, not core.
* **SUPPLY-CHAIN-SAFE:** 4 deps vs LiteLLM's 50+. No transitive dependency forests.

---

## 2. ARCHITECTURE

### 2.1 Service Design

```
pw-router (FastAPI on Fly.io or any container platform)
├── PRODUCES: /v1/chat/completions — chat completions (streaming + non-streaming)
├── PRODUCES: /v1/completions — text completions
├── PRODUCES: /v1/embeddings — embeddings
├── PRODUCES: /v1/models — list available models
├── PRODUCES: /health — router health + per-model circuit status
├── PRODUCES: /metrics — request counts, latency percentiles, error rates
├── CONSUMES: Upstream LLM providers (OpenAI, Anthropic, vLLM, Ollama, etc.)
├── AUTH: Static API keys with per-key model allowlists
└── MIDDLEWARE: Pluggable pre/post request hooks for PII, logging, RBAC, etc.
```

### 2.2 File Structure

```
pw-router/
├── CLAUDE.md                    # This file — build instructions (public)
├── LICENSE                      # MIT
├── README.md                    # Public-facing docs, usage guide, architecture
├── CONTRIBUTING.md              # How to contribute, code standards
├── SECURITY.md                  # Vulnerability disclosure policy
├── CHANGELOG.md                 # Version history
├── pyproject.toml               # Dependencies (uv/pip), project metadata
├── Dockerfile                   # Production container
├── fly.toml.example             # Fly.io template with placeholder values
├── config.example.yaml          # Router config template with placeholder values
├── .gitignore                   # MUST include: fly.toml, config.yaml, .env, *.secret
├── .env.example                 # Template with placeholder values
├── .github/
│   ├── workflows/
│   │   └── ci.yml               # Lint + test on push/PR
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── pw_router/                   # Flat package (NOT src/ layout — simpler for small projects)
│   ├── __init__.py              # Package init with __version__
│   ├── __main__.py              # CLI entry point: python -m pw_router
│   ├── server.py                # FastAPI app, lifespan, route handlers (~150 lines)
│   ├── router.py                # Model selection, fallback chains, circuit breaker (~200 lines)
│   ├── providers.py             # Provider adapters (OpenAI, Anthropic, vLLM, etc.) (~250 lines)
│   ├── middleware.py            # Pre/post hook system, plugin loading (~150 lines)
│   ├── health.py                # Background health checks per endpoint (~100 lines)
│   ├── config.py                # YAML config loader with env var expansion (~100 lines)
│   └── models.py                # Pydantic models for internal data structures (~50 lines)
├── plugins/                     # Optional example middleware plugins
│   ├── __init__.py
│   ├── example_redact.py        # Example PII redaction plugin (~50 lines)
│   └── example_logger.py        # Example structured logging plugin (~30 lines)
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures, mock providers
│   ├── test_server.py           # API endpoint tests
│   ├── test_router.py           # Model selection, fallback, circuit breaker tests
│   ├── test_providers.py        # Provider adapter tests (mocked HTTP)
│   ├── test_middleware.py        # Plugin loading, hook execution tests
│   ├── test_health.py           # Health check tests
│   └── test_config.py           # Config loading, env var expansion tests
└── docs/
    ├── architecture.md          # Detailed architecture explanation
    ├── plugins.md               # How to write middleware plugins
    └── deployment.md            # Docker, Fly.io, Railway deployment guide
```

**Total core: ~950 lines in pw_router/. Target: never exceed 1,500 lines.**

### 2.3 Cross-Repo Contracts (PW internal — NOT in public docs)

When used by Protocol Wealth internally, pw-router sits between PW services and LLM providers:

```
pw-nexus (CONSUMER)
├── Calls POST /v1/chat/completions for all LLM inference
├── Uses PW_ROUTER_API_KEY for auth
├── Sends model name or relies on tag-based routing
└── Env vars: PW_ROUTER_URL, PW_ROUTER_API_KEY

pw-portal (CONSUMER)
├── Go backend calls /v1/chat/completions for advisor-facing AI features
├── Uses PW_ROUTER_API_KEY for auth
└── Env vars: PW_ROUTER_URL, PW_ROUTER_API_KEY

pw-redact (UPSTREAM DEPENDENCY — called by pw-router's redact plugin)
├── POST /v1/redact — {"text": "...", "context": "meeting_transcript"}
│   Returns: {"sanitized_text": "...", "manifest": {...}, "security": {...}}
├── POST /v1/rehydrate — {"text": "...", "manifest": {...}}
│   Returns: {"rehydrated_text": "..."}
├── Auth: Bearer token via PW_REDACT_API_KEY
└── Deployed: pw-redact.fly.dev (or RunPod serverless)

LLM Providers (UPSTREAM — pw-router forwards to these)
├── Anthropic API: api.anthropic.com (Claude models)
├── RunPod vLLM: api.runpod.ai (self-hosted Llama, Qwen, etc.)
├── OpenAI API: api.openai.com (if needed)
└── Ollama: localhost:11434 (local dev inference)
```

---

## 3. API SPECIFICATION

### 3.1 POST /v1/chat/completions

OpenAI-compatible chat completions. Drop-in replacement for any OpenAI SDK client.

**Request (standard OpenAI format):**

```json
{
  "model": "claude-sonnet",
  "messages": [
    {"role": "system", "content": "You are a financial analyst."},
    {"role": "user", "content": "Analyze this portfolio allocation."}
  ],
  "temperature": 0.7,
  "max_tokens": 2000,
  "stream": false
}
```

**Response (standard OpenAI format):**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1711000000,
  "model": "claude-sonnet",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Based on the allocation..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 50,
    "completion_tokens": 200,
    "total_tokens": 250
  }
}
```

**Streaming:** When `"stream": true`, returns SSE events in OpenAI format:

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Based"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" on"},"finish_reason":null}]}

data: [DONE]
```

### 3.2 POST /v1/completions

Text completions endpoint. Same routing logic as chat completions.

### 3.3 POST /v1/embeddings

Embeddings endpoint. Routes to embedding-capable models.

### 3.4 GET /v1/models

Returns list of available models from config (respects client's allowlist).

```json
{
  "object": "list",
  "data": [
    {"id": "claude-sonnet", "object": "model", "owned_by": "anthropic"},
    {"id": "local-llama", "object": "model", "owned_by": "self-hosted"}
  ]
}
```

### 3.5 GET /health

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "models": {
    "claude-sonnet": {"status": "healthy", "circuit": "closed", "latency_ms_p50": 450},
    "local-llama": {"status": "unhealthy", "circuit": "open", "last_error": "timeout"}
  }
}
```

### 3.6 GET /metrics

```json
{
  "uptime_seconds": 86400,
  "total_requests": 1523,
  "requests_by_model": {"claude-sonnet": 1200, "local-llama": 323},
  "errors_by_model": {"claude-sonnet": 2, "local-llama": 15},
  "latency_p50_ms": 420,
  "latency_p95_ms": 1200,
  "latency_p99_ms": 2800
}
```

---

## 4. IMPLEMENTATION DETAILS

### 4.1 Configuration (config.py)

Single YAML file with env var expansion. No database required.

```python
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field


def expand_env_vars(value: str) -> str:
    """Expand ${VAR_NAME} patterns in config values."""
    if isinstance(value, str) and "${" in value:
        import re
        def replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                raise ValueError(f"Environment variable {var_name} not set")
            return env_val
        return re.sub(r'\$\{([^}]+)\}', replacer, value)
    return value


def load_config(path: str = "config.yaml") -> dict:
    """Load and validate router config from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return _expand_recursive(raw)


def _expand_recursive(obj):
    """Recursively expand env vars in config dict."""
    if isinstance(obj, str):
        return expand_env_vars(obj)
    elif isinstance(obj, dict):
        return {k: _expand_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_recursive(item) for item in obj]
    return obj
```

### 4.2 Server (server.py)

FastAPI app with lifespan for background health checks. ~150 lines.

```python
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse
import time

# Lifespan manages:
# - Load config from YAML
# - Initialize provider adapters
# - Start background health check task
# - Load middleware plugins

# Routes:
# POST /v1/chat/completions → main handler
# POST /v1/completions → text completions handler
# POST /v1/embeddings → embeddings handler
# GET /v1/models → list models (filtered by client allowlist)
# GET /health → health status
# GET /metrics → request metrics

# Auth middleware:
# - Extract Bearer token from Authorization header
# - Look up API key in config.server.api_keys
# - Reject if not found (401) or model not allowed (403)
# - Attach client_name to request state
```

**Request handling flow:**

```python
async def handle_chat_completion(request: Request):
    body = await request.json()
    client_name = request.state.client_name
    allowed_models = request.state.allowed_models

    # 1. Create middleware context
    ctx = MiddlewareContext(
        request_body=body,
        client_name=client_name,
        tags=set(),
        metadata={},
        config={},
    )

    # 2. Run pre-request middleware
    for hook in pre_request_hooks:
        result = await hook(ctx)
        if not result.allow:
            return JSONResponse(
                status_code=result.status_code,
                content={"error": {"message": result.error_message}}
            )

    # 3. Select model via router
    model_name = select_model(
        request_body=ctx.request_body,
        tags=ctx.tags,
        client_allowed=allowed_models,
    )

    # 4. Get provider adapter
    adapter = get_adapter(model_name)

    # 5. Forward request
    stream = ctx.request_body.get("stream", False)
    start = time.monotonic()

    if stream:
        response_iter = await adapter.chat_completion(ctx.request_body, model_config, stream=True)
        return StreamingResponse(
            _wrap_stream(response_iter, ctx, model_name, start),
            media_type="text/event-stream",
        )
    else:
        response = await adapter.chat_completion(ctx.request_body, model_config, stream=False)
        latency_ms = (time.monotonic() - start) * 1000

        # 6. Run post-response middleware
        ctx.response_body = response
        ctx.model_used = model_name
        ctx.latency_ms = latency_ms
        for hook in post_response_hooks:
            result = await hook(ctx)
            if not result.allow:
                return JSONResponse(
                    status_code=result.status_code,
                    content={"error": {"message": result.error_message}}
                )

        # 7. Record metrics
        record_request(model_name, latency_ms, success=True)

        return JSONResponse(content=ctx.response_body)
```

### 4.3 Router Engine (router.py)

Model selection + circuit breaker. ~200 lines.

**Model selection logic:**

```python
def select_model(request_body: dict, tags: set[str], client_allowed: list[str]) -> str:
    """
    Select model for request.

    Priority:
    1. Explicit model in request_body["model"] (must be client-allowed)
    2. First matching routing rule based on tags
    3. Default model from config
    4. Walk fallback chain if selected model's circuit is open

    Raises 503 if all models in the chain are unhealthy.
    """
```

**Circuit breaker (per model, in-memory):**

```python
from enum import Enum
from dataclasses import dataclass
import time


class CircuitState(Enum):
    CLOSED = "closed"       # Healthy — all requests pass through
    OPEN = "open"           # Unhealthy — requests immediately fail
    HALF_OPEN = "half_open" # Testing — allow one probe request


@dataclass
class CircuitBreaker:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    unhealthy_threshold: int = 3     # Consecutive failures to open
    healthy_threshold: int = 1       # Successes to close from half-open
    cooldown_seconds: float = 30.0   # Time in OPEN before trying HALF_OPEN

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
        self.failure_count = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.unhealthy_threshold:
            self.state = CircuitState.OPEN

    def should_allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time > self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                return True  # Allow one probe
            return False
        # HALF_OPEN: allow (testing)
        return True
```

### 4.4 Provider Adapters (providers.py)

Each adapter implements a protocol. ~250 lines total for all adapters.

```python
from typing import Protocol, AsyncIterator
import httpx


class ProviderAdapter(Protocol):
    async def chat_completion(
        self, request: dict, model_config: dict, stream: bool
    ) -> dict | AsyncIterator[dict]:
        """Send chat completion request, return OpenAI-format response."""
        ...

    async def health_check(self, model_config: dict) -> bool:
        """Return True if endpoint is responsive."""
        ...
```

**Built-in adapters:**

1. **OpenAIAdapter** — pass-through (request is already OpenAI format). Changes base_url and api_key. Handles streaming SSE.

2. **AnthropicAdapter** — translates OpenAI format ↔ Anthropic Messages API:
   - `messages` format is similar but system prompt handled differently
   - `max_tokens` → `max_tokens` (required in Anthropic API)
   - Response shape differs: `content[0].text` vs `choices[0].message.content`
   - Streaming: Anthropic uses different SSE event types (`content_block_delta`)
   - Must translate back to OpenAI chunk format for client compatibility

3. **VLLMAdapter** — OpenAI-compatible; effectively same as OpenAIAdapter but with RunPod-specific base_url patterns and auth.

4. **OllamaAdapter** — OpenAI-compatible at `/api/chat` endpoint. Minor format differences.

5. **CustomHTTPAdapter** — generic adapter for any HTTP endpoint. Configurable request/response field mapping in YAML.

**Important implementation note:** Use a single `httpx.AsyncClient` per adapter instance (created at startup, closed at shutdown via lifespan). Do NOT create a new client per request.

### 4.5 Middleware System (middleware.py)

Plugin loading and hook execution. ~150 lines.

```python
from dataclasses import dataclass, field
from typing import Callable, Awaitable
import importlib


@dataclass
class MiddlewareContext:
    """Context passed through middleware pipeline."""
    request_body: dict          # Mutable OpenAI-format request
    client_name: str            # Authenticated client identity
    tags: set[str]              # Mutable routing tags (plugins add these)
    metadata: dict              # Pass data between pre and post hooks
    config: dict                # Plugin-specific config from YAML
    # Post-response only (None during pre-request):
    response_body: dict | None = None
    model_used: str | None = None
    latency_ms: float | None = None
    provider: str | None = None


@dataclass
class MiddlewareResult:
    """Result from a middleware hook."""
    allow: bool = True
    error_message: str | None = None
    status_code: int = 400


# Type alias for hook functions
MiddlewareHook = Callable[[MiddlewareContext], Awaitable[MiddlewareResult]]


def load_plugin(module_path: str, hook_name: str) -> MiddlewareHook:
    """
    Dynamically load a middleware hook function from a module.

    Args:
        module_path: Dotted module path (e.g., "plugins.example_redact")
        hook_name: Function name to load ("pre_request" or "post_response")

    Returns:
        Async callable middleware hook function.
    """
    module = importlib.import_module(module_path)
    hook = getattr(module, hook_name, None)
    if hook is None:
        raise ValueError(f"Plugin {module_path} has no {hook_name} function")
    return hook
```

### 4.6 Health Checks (health.py)

Background task that pings each model endpoint. ~100 lines.

```python
import asyncio
import logging

logger = logging.getLogger("pw_router.health")


async def health_check_loop(adapters: dict, circuits: dict, config: dict):
    """
    Background task: ping each model endpoint at configured interval.
    Updates circuit breaker state based on results.
    """
    interval = config.get("check_interval_seconds", 30)
    timeout = config.get("check_timeout_seconds", 5)

    while True:
        for model_name, adapter in adapters.items():
            try:
                healthy = await asyncio.wait_for(
                    adapter.health_check(config["models"][model_name]),
                    timeout=timeout,
                )
                if healthy:
                    circuits[model_name].record_success()
                else:
                    circuits[model_name].record_failure()
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Health check failed for {model_name}: {e}")
                circuits[model_name].record_failure()

        await asyncio.sleep(interval)
```

---

## 5. CONFIGURATION FILE

### config.example.yaml (committed to repo)

```yaml
# pw-router configuration
# Copy to config.yaml and fill in real values
# DO NOT commit config.yaml — it's in .gitignore

server:
  host: "0.0.0.0"
  port: 8100
  api_keys:
    - key: "${PW_ROUTER_API_KEY_1}"
      name: "default"
      allowed_models: ["*"]

models:
  # Example: OpenAI
  gpt-4o:
    provider: openai
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
    base_url: "https://api.openai.com/v1"
    max_retries: 2
    timeout_seconds: 120
    tags: ["external", "reasoning"]

  # Example: Anthropic
  claude-sonnet:
    provider: anthropic
    model: "claude-sonnet-4-20250514"
    api_key: "${ANTHROPIC_API_KEY}"
    max_retries: 2
    timeout_seconds: 120
    tags: ["external", "reasoning"]

  # Example: Self-hosted vLLM on RunPod
  local-llama:
    provider: vllm
    model: "meta-llama/Llama-3.1-70B-Instruct"
    api_key: "${RUNPOD_API_KEY}"
    base_url: "https://api.runpod.ai/v2/${RUNPOD_ENDPOINT_ID}/openai/v1"
    max_retries: 1
    timeout_seconds: 90
    tags: ["self-hosted", "client-safe"]

  # Example: Local Ollama
  local-dev:
    provider: ollama
    model: "llama3.1"
    base_url: "http://localhost:11434"
    timeout_seconds: 60
    tags: ["local", "dev"]

routing:
  default_model: "claude-sonnet"
  fallback_chains:
    reasoning: ["claude-sonnet", "gpt-4o", "local-llama"]
    fast: ["gpt-4o", "local-llama"]
    client-safe: ["local-llama"]
  rules:
    - match:
        tag: "client-data"
      route_to_chain: "client-safe"

health:
  check_interval_seconds: 30
  unhealthy_threshold: 3
  healthy_threshold: 1
  check_timeout_seconds: 5

middleware:
  pre_request: []
  post_response: []
  # Example with plugin:
  # pre_request:
  #   - plugin: "plugins.example_redact"
  #     config:
  #       endpoint: "${PW_REDACT_URL}"
  #       api_key: "${PW_REDACT_API_KEY}"

logging:
  level: "INFO"
  format: "json"
  log_request_body: false
  log_response_body: false
```

---

## 6. EXAMPLE PLUGINS

### 6.1 plugins/example_redact.py

Demonstrates integration with a PII redaction service (like pw-redact).

```python
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

# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

from pw_router.middleware import MiddlewareContext, MiddlewareResult
import httpx


async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    """Scan request for PII via external redaction service."""
    endpoint = ctx.config.get("endpoint")
    api_key = ctx.config.get("api_key")

    if not endpoint:
        return MiddlewareResult(allow=True)  # No endpoint configured, skip

    # Extract text from messages
    messages = ctx.request_body.get("messages", [])
    full_text = " ".join(
        m.get("content", "")
        for m in messages
        if isinstance(m.get("content"), str)
    )

    if not full_text.strip():
        return MiddlewareResult(allow=True)

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(
                f"{endpoint}/v1/detect",
                json={"text": full_text, "context": "general"},
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            result = resp.json()

        entities = result.get("entities", [])
        if entities:
            # PII detected — tag so router uses self-hosted models only
            ctx.tags.add("client-data")
            ctx.metadata["pii_entities_count"] = len(entities)
            ctx.metadata["pii_entity_types"] = list(set(
                e["entity_type"] for e in entities
            ))

    except Exception:
        # If redaction service is down, fail open but tag for caution
        ctx.tags.add("client-data")
        ctx.metadata["pii_check_failed"] = True

    return MiddlewareResult(allow=True)
```

### 6.2 plugins/example_logger.py

Demonstrates structured request logging.

```python
"""
Example structured logging middleware plugin for pw-router.
Logs request metadata (NOT request/response bodies by default).
"""

# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

import logging
import json
from pw_router.middleware import MiddlewareContext, MiddlewareResult

logger = logging.getLogger("pw_router.audit")


async def post_response(ctx: MiddlewareContext) -> MiddlewareResult:
    """Log request metadata after response is received."""
    log_entry = {
        "client": ctx.client_name,
        "model": ctx.model_used,
        "latency_ms": round(ctx.latency_ms, 1) if ctx.latency_ms else None,
        "tags": list(ctx.tags),
        "prompt_tokens": ctx.response_body.get("usage", {}).get("prompt_tokens"),
        "completion_tokens": ctx.response_body.get("usage", {}).get("completion_tokens"),
    }
    logger.info(json.dumps(log_entry))
    return MiddlewareResult(allow=True)
```

---

## 7. DEPENDENCIES

### pyproject.toml

```toml
[project]
name = "pw-router"
version = "0.1.0"
description = "Minimal, auditable LLM routing gateway for regulated environments"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.12"
authors = [
    {name = "Protocol Wealth LLC", email = "engineering@protocolwealthllc.com"},
]
keywords = ["llm", "gateway", "router", "openai", "ai", "compliance", "ria"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Intended Audience :: Financial and Insurance Industry",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
anthropic = ["anthropic>=0.40"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.7",
    "respx>=0.22",
]

[project.scripts]
pw-router = "pw_router.__main__:main"

[project.urls]
Homepage = "https://github.com/Protocol-Wealth/pw-router"
Repository = "https://github.com/Protocol-Wealth/pw-router"
Issues = "https://github.com/Protocol-Wealth/pw-router/issues"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Total: 4 required dependencies.** All well-established, widely audited packages.

---

## 8. DEPLOYMENT

### 8.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY pw_router/ pw_router/
COPY plugins/ plugins/

EXPOSE 8100

CMD ["uvicorn", "pw_router.server:app", "--host", "0.0.0.0", "--port", "8100"]
```

### 8.2 fly.toml.example

```toml
# Copy to fly.toml and customize
# DO NOT commit fly.toml — it's in .gitignore
app = "your-pw-router"
primary_region = "ewr"

[build]

[http_service]
  internal_port = 8100
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

[vm]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1

[checks]
  [checks.health]
    port = 8100
    type = "http"
    interval = "30s"
    timeout = "5s"
    path = "/health"
```

**Note:** 512MB is sufficient — no ML models loaded. This is a thin proxy.

### 8.3 .env.example

```bash
# Copy to .env and fill in real values
# DO NOT commit .env — it's in .gitignore

# Router config path
CONFIG_PATH=config.yaml

# API keys for upstream providers (referenced in config.yaml)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...

# Router client API keys
PW_ROUTER_API_KEY_1=change-me-to-strong-random-key

# Optional: PII redaction service (for redact plugin)
PW_REDACT_URL=http://localhost:8080
PW_REDACT_API_KEY=change-me
```

### 8.4 .gitignore

```
# Private deployment config — NEVER commit
fly.toml
config.yaml
.env
*.secret

# Python
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.pytest_cache/
.ruff_cache/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db
```

---

## 9. TESTING REQUIREMENTS

### 9.1 Test Strategy

All provider HTTP calls are mocked using `respx`. No real API calls in tests.

### 9.2 Mandatory Test Cases

**Config loading (test_config.py):**
- Load valid YAML config
- Env var expansion works: `${VAR_NAME}` → resolved value
- Missing env var raises clear error
- Invalid YAML raises clear error
- Empty/missing config file handled gracefully

**API key auth (test_server.py):**
- Valid key → 200
- Missing Authorization header → 401
- Invalid key → 403
- Key with restricted model list → 403 when requesting disallowed model
- Wildcard (`*`) allows all models

**Model routing (test_router.py):**
- Explicit model name in request → that model selected
- No model + matching tag → correct chain selected
- No model + no tag → default model selected
- Circuit open → next model in fallback chain
- All models in chain unhealthy → 503
- Client not allowed for model → 403

**Circuit breaker (test_router.py):**
- Starts CLOSED
- N consecutive failures → OPEN
- OPEN for cooldown period → HALF_OPEN
- HALF_OPEN + success → CLOSED
- HALF_OPEN + failure → OPEN

**Provider adapters (test_providers.py):**
- OpenAI adapter: pass-through works (non-streaming + streaming)
- Anthropic adapter: OpenAI→Anthropic request translation correct
- Anthropic adapter: Anthropic→OpenAI response translation correct
- vLLM adapter: base_url override works
- Timeout handling: provider timeout → circuit breaker notified
- Connection error → circuit breaker notified

**Middleware (test_middleware.py):**
- Pre-request hook can modify request_body
- Pre-request hook can add tags
- Pre-request hook returning allow=False blocks request
- Post-response hook receives response_body
- Multiple hooks execute in order
- Plugin loading from module path works
- Missing plugin raises clear error

**Health checks (test_health.py):**
- Healthy endpoint → circuit stays CLOSED
- Unhealthy endpoint → circuit opens after threshold
- /health endpoint returns per-model status

### 9.3 Test Fixtures (conftest.py)

```python
import pytest
from fastapi.testclient import TestClient
import os


@pytest.fixture
def sample_config():
    """Minimal config for testing."""
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 8100,
            "api_keys": [
                {"key": "test-key-1", "name": "test-client", "allowed_models": ["*"]},
                {"key": "test-key-2", "name": "restricted", "allowed_models": ["local-*"]},
            ],
        },
        "models": {
            "test-model": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "fake-key",
                "base_url": "https://api.openai.com/v1",
                "timeout_seconds": 30,
                "tags": ["external"],
            },
            "local-model": {
                "provider": "vllm",
                "model": "meta-llama/Llama-3.1-70B-Instruct",
                "api_key": "fake-key",
                "base_url": "http://localhost:8000/v1",
                "timeout_seconds": 30,
                "tags": ["self-hosted", "client-safe"],
            },
        },
        "routing": {
            "default_model": "test-model",
            "fallback_chains": {
                "reasoning": ["test-model", "local-model"],
                "client-safe": ["local-model"],
            },
            "rules": [
                {"match": {"tag": "client-data"}, "route_to_chain": "client-safe"},
            ],
        },
        "health": {
            "check_interval_seconds": 30,
            "unhealthy_threshold": 3,
            "healthy_threshold": 1,
            "check_timeout_seconds": 5,
        },
        "middleware": {"pre_request": [], "post_response": []},
        "logging": {"level": "INFO", "format": "json"},
    }
```

---

## 10. SECURITY REQUIREMENTS

1. **No logging of request/response bodies by default.** The `logging.log_request_body` and `logging.log_response_body` flags default to `false`. Middleware plugins can override for audit purposes.
2. **No disk writes.** pw-router never writes request data, configs, or intermediate results to disk. Everything is in-memory.
3. **API key comparison uses constant-time comparison** (`hmac.compare_digest`) to prevent timing attacks.
4. **Request size limits.** Max request body: 10MB. Reject larger payloads with 413.
5. **No telemetry, no analytics, no phoning home.** Zero external calls except to configured model providers.
6. **Provider API keys never logged.** Config loader must mask API keys in any debug output.
7. **TLS only in production.** Fly.io handles TLS termination. The `force_https = true` in fly.toml enforces this.

---

## 11. BUILD SEQUENCE

When Claude Code builds this repo, follow this order:

1. **Scaffold** — pyproject.toml, Dockerfile, fly.toml.example, config.example.yaml, .env.example, .gitignore, LICENSE (already exists), directory structure
2. **Config** — config.py: YAML loader with env var expansion, validation
3. **Models** — models.py: Pydantic dataclasses for internal types
4. **Middleware** — middleware.py: MiddlewareContext, MiddlewareResult, plugin loader, hook runner
5. **Providers** — providers.py: ProviderAdapter protocol, OpenAI + Anthropic + vLLM + Ollama adapters
6. **Router** — router.py: model selection, circuit breaker, fallback chains
7. **Health** — health.py: background health check loop
8. **Server** — server.py: FastAPI app, lifespan, all route handlers, auth middleware
9. **CLI** — __main__.py: `python -m pw_router` entry point
10. **Plugins** — plugins/example_redact.py, plugins/example_logger.py
11. **Tests** — All test files with mocked HTTP via respx
12. **README.md** — Public-facing documentation (replace starter README)
13. **Docs** — docs/architecture.md, docs/plugins.md, docs/deployment.md
14. **CI** — .github/workflows/ci.yml (ruff lint + pytest)
15. **Contributing** — CONTRIBUTING.md, SECURITY.md, CHANGELOG.md
16. **GitHub** — Issue templates, PR template

### Priority: Steps 1-11 are the MVP. Steps 12-16 are polish.

### V0.1.0 MVP scope:
- `/v1/chat/completions` (streaming + non-streaming) ✓
- `/v1/models` ✓
- `/health` ✓
- OpenAI + Anthropic + vLLM adapters ✓
- YAML config with env var expansion ✓
- API key auth with model allowlists ✓
- Circuit breaker per model ✓
- Fallback chains ✓
- Middleware hook system ✓
- Background health checks ✓
- Full test suite ✓

### Deferred to V0.2.0:
- `/v1/completions`
- `/v1/embeddings`
- `/metrics` endpoint
- Ollama adapter
- Custom HTTP adapter
- Token counting / budget limits
- Response caching

---

## 12. README.md SPECIFICATION

The README is the public face of the project. Structure:

```
# pw-router

**A minimal, auditable LLM gateway for regulated environments.**

MIT License | Python/FastAPI | 4 dependencies | ~950 lines of core

Built by [Protocol Wealth LLC](https://protocolwealthllc.com), an SEC-registered
investment adviser that actually routes client-adjacent AI workloads through this.

> The selling point isn't speed benchmarks.
> It's that a compliance officer can read the entire codebase in an afternoon.

## Why This Exists

[LiteLLM supply chain attack context, 800+ open issues, 50+ deps]
[The case for a deliberately minimal alternative]

## How It Works

[Architecture diagram from spec]

## Quick Start

[pip install, config.yaml setup, run]

## Configuration

[YAML config reference]

## Writing Plugins

[Middleware interface, example plugin]

## Comparison

[Table: pw-router vs LiteLLM vs Bifrost]

## Deployment

[Docker, Fly.io]

## Contributing

See CONTRIBUTING.md

## License

MIT. Architectural patterns informed by Bifrost (Apache 2.0). See LICENSE.

## Built By

Protocol Wealth LLC — SEC-registered investment adviser (CRD #335298)
```

---

*Protocol Wealth LLC | SEC-Registered Investment Adviser (CRD #335298)*
*pw-router is open-source infrastructure under MIT license.*
*Internal deployment config and compliance plugins are private.*
