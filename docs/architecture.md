# pw-router

**A minimal, auditable LLM gateway for regulated environments.**

MIT License | Python/FastAPI | OpenAI-compatible API

---

## Executive Summary

pw-router is a deliberately minimal LLM routing gateway designed for environments where every line of code must be auditable — financial services, healthcare, legal, and any regulated industry running AI workloads with sensitive data. The entire core is under 1,000 lines. No magic, no bloat, no 800 open GitHub issues.

**Design philosophy:** The selling point isn't speed benchmarks. It's that a compliance officer can read the entire codebase in an afternoon.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    pw-router                         │
│                   (FastAPI)                          │
│                                                     │
│  ┌─────────┐   ┌──────────┐   ┌─────────────────┐  │
│  │ Inbound │──▶│  Router   │──▶│    Provider      │  │
│  │Middleware│   │  Engine   │   │    Adapters      │  │
│  │ Pipeline │   │          │   │                  │  │
│  │          │   │ • match   │   │ • OpenAI         │  │
│  │ • auth   │   │ • fallback│   │ • Anthropic      │  │
│  │ • pre-   │   │ • circuit │   │ • vLLM/RunPod   │  │
│  │   hooks  │   │   breaker │   │ • Ollama         │  │
│  │ • log    │   │          │   │ • Custom HTTP    │  │
│  └─────────┘   └──────────┘   └─────────────────┘  │
│        │                              │              │
│        ▼                              ▼              │
│  ┌──────────┐                  ┌──────────┐         │
│  │ Outbound │◀─────────────────│ Response │         │
│  │Middleware │                  │ Adapter  │         │
│  │ Pipeline │                  │          │         │
│  │          │                  │ • normalize       │  │
│  │ • post-  │                  │   to OpenAI       │  │
│  │   hooks  │                  │   format          │  │
│  │ • log    │                  └──────────┘         │
│  └──────────┘                                       │
└─────────────────────────────────────────────────────┘
```

---

## License & Attribution

**pw-router** is released under the **MIT License**.

Architectural patterns in the router engine (circuit breaker, fallback chain, health-check loop) are informed by [Bifrost](https://github.com/maximhq/bifrost) (Apache 2.0, Maxim AI). No code was copied; patterns were reimplemented in Python/FastAPI. Per Apache 2.0 §4, this notice serves as attribution.

---

## Core Modules

The entire project is six files plus config:

```
pw-router/
├── LICENSE                 # MIT
├── README.md
├── pyproject.toml          # uv/pip, minimal deps
├── config.yaml             # Model & routing config
├── pw_router/
│   ├── __init__.py
│   ├── server.py           # FastAPI app, OpenAI-compatible endpoints (~150 lines)
│   ├── router.py           # Model selection, fallback, circuit breaker (~200 lines)
│   ├── providers.py        # Provider adapters (OpenAI, Anthropic, vLLM, etc.) (~250 lines)
│   ├── middleware.py        # Pre/post hook system (~150 lines)
│   ├── health.py           # Background health checks per endpoint (~100 lines)
│   └── logging.py          # Structured request/response logging (~100 lines)
├── plugins/                # Optional middleware plugins (not required)
│   ├── __init__.py
│   └── example_redact.py   # Example PII redaction plugin (~50 lines)
└── tests/
    ├── test_router.py
    ├── test_providers.py
    └── test_middleware.py
```

**Total core: ~950 lines.** The `plugins/` directory is optional and not part of the core.

---

## Configuration

Single YAML file. No database required for basic operation.

```yaml
# config.yaml
server:
  host: "0.0.0.0"
  port: 8100
  api_keys:                           # Static API keys for client auth
    - key: "${PW_ROUTER_API_KEY_1}"   # Env var expansion
      name: "pw-nexus"
      allowed_models: ["*"]           # Wildcard = all models
    - key: "${PW_ROUTER_API_KEY_2}"
      name: "pw-portal"
      allowed_models: ["claude-*", "local-*"]

models:
  # Claude API (external)
  claude-sonnet:
    provider: anthropic
    model: "claude-sonnet-4-20250514"
    api_key: "${ANTHROPIC_API_KEY}"
    max_retries: 2
    timeout_seconds: 120
    tags: ["external", "reasoning"]

  claude-haiku:
    provider: anthropic
    model: "claude-haiku-4-5-20251001"
    api_key: "${ANTHROPIC_API_KEY}"
    max_retries: 2
    timeout_seconds: 60
    tags: ["external", "fast"]

  # Self-hosted on RunPod (vLLM)
  local-llama:
    provider: vllm
    base_url: "https://api.runpod.ai/v2/${RUNPOD_LLAMA_ID}/openai/v1"
    api_key: "${RUNPOD_API_KEY}"
    model: "meta-llama/Llama-3.1-70B-Instruct"
    max_retries: 1
    timeout_seconds: 90
    tags: ["self-hosted", "client-safe"]

  local-qwen:
    provider: vllm
    base_url: "https://api.runpod.ai/v2/${RUNPOD_QWEN_ID}/openai/v1"
    api_key: "${RUNPOD_API_KEY}"
    model: "Qwen/Qwen2.5-72B-Instruct"
    max_retries: 1
    timeout_seconds: 90
    tags: ["self-hosted", "client-safe"]

routing:
  # Default model when none specified
  default_model: "claude-sonnet"

  # Fallback chains: if primary fails, try next
  fallback_chains:
    reasoning: ["claude-sonnet", "local-llama"]
    fast: ["claude-haiku", "local-qwen"]
    client-safe: ["local-llama", "local-qwen"]   # Never routes to external

  # Tag-based routing rules
  rules:
    - match:
        tag: "client-data"              # Middleware can tag requests
      route_to_chain: "client-safe"     # Only self-hosted models
    - match:
        tag: "fast"
      route_to_chain: "fast"

health:
  check_interval_seconds: 30
  unhealthy_threshold: 3                # Consecutive failures before circuit opens
  healthy_threshold: 1                  # Successes to close circuit
  check_timeout_seconds: 5

middleware:
  pre_request:
    - plugin: "plugins.example_redact"  # Optional; loads from plugins/ dir
      config:
        endpoint: "${PW_REDACT_URL}"
  post_response: []

logging:
  level: "INFO"
  format: "json"                        # Structured JSON to stdout
  log_request_body: false               # Default off; compliance plugins can override
  log_response_body: false
```

---

## API Surface

OpenAI-compatible. Drop-in replacement for any OpenAI SDK client.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completions (streaming + non-streaming) |
| POST | `/v1/completions` | Text completions |
| POST | `/v1/embeddings` | Embeddings |
| GET | `/v1/models` | List available models |
| GET | `/health` | Router health + per-model circuit status |
| GET | `/metrics` | Request counts, latency percentiles, error rates |

### Request Flow

```
1. Client sends OpenAI-format request with Authorization header
2. server.py validates API key, extracts client identity
3. middleware.py runs pre_request hooks (PII scan, tagging, logging)
4. router.py selects model:
   a. If request specifies model name → use that model (if client allowed)
   b. If request has routing tag → match rule → select chain
   c. Else → default_model
   d. If selected model circuit is open → walk fallback chain
5. providers.py adapts request to provider format (if needed)
6. providers.py sends request, handles streaming
7. providers.py normalizes response to OpenAI format
8. middleware.py runs post_response hooks (PII scan on output, logging)
9. server.py returns response to client
```

### Client Usage

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8100/v1",  # pw-router
    api_key="your-pw-router-key"
)

# Routes to default model
response = client.chat.completions.create(
    model="claude-sonnet",
    messages=[{"role": "user", "content": "Analyze this portfolio allocation"}]
)

# Force self-hosted only (by model name)
response = client.chat.completions.create(
    model="local-llama",
    messages=[{"role": "user", "content": "Client X has..."}]
)

# Streaming works identically
for chunk in client.chat.completions.create(
    model="claude-sonnet",
    messages=[{"role": "user", "content": "..."}],
    stream=True
):
    print(chunk.choices[0].delta.content, end="")
```

---

## Middleware Plugin Interface

Plugins are Python modules with a single async function. This is the entire interface:

```python
# plugins/example_redact.py
"""Example PII redaction middleware plugin for pw-router."""

from pw_router.middleware import MiddlewareContext, MiddlewareResult


async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    """
    Called before the request is sent to the model provider.

    Args:
        ctx: MiddlewareContext with:
            - request_body: dict (OpenAI-format request, mutable)
            - client_name: str (from API key config)
            - tags: set[str] (mutable; add tags to influence routing)
            - metadata: dict (mutable; passed through to post_response)
            - config: dict (from config.yaml middleware.pre_request[].config)

    Returns:
        MiddlewareResult with:
            - allow: bool (False = reject request with error)
            - error_message: str | None (if allow=False)
    """
    # Example: call pw-redact endpoint to scan for PII
    import httpx

    messages = ctx.request_body.get("messages", [])
    full_text = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            ctx.config["endpoint"],
            json={"text": full_text}
        )
        result = resp.json()

    if result.get("pii_detected"):
        # Tag the request so router sends to self-hosted only
        ctx.tags.add("client-data")
        # Store original for audit
        ctx.metadata["pii_entities"] = result.get("entities", [])

    return MiddlewareResult(allow=True)


async def post_response(ctx: MiddlewareContext) -> MiddlewareResult:
    """
    Called after the response is received from the model provider.

    ctx additionally contains:
        - response_body: dict (OpenAI-format response, mutable)
        - model_used: str (actual model name that handled the request)
        - latency_ms: float
        - provider: str
    """
    # Example: scan response for accidentally generated PII
    return MiddlewareResult(allow=True)
```

### MiddlewareContext (dataclass)

```python
@dataclass
class MiddlewareContext:
    request_body: dict          # Mutable OpenAI-format request
    client_name: str            # Authenticated client identity
    tags: set[str]              # Mutable routing tags
    metadata: dict              # Pass data between pre and post hooks
    config: dict                # Plugin-specific config from YAML
    # Post-response only:
    response_body: dict | None = None
    model_used: str | None = None
    latency_ms: float | None = None
    provider: str | None = None
```

### MiddlewareResult (dataclass)

```python
@dataclass
class MiddlewareResult:
    allow: bool = True                  # False = block request/response
    error_message: str | None = None    # Returned to client if blocked
    status_code: int = 400              # HTTP status if blocked
```

---

## Router Engine

### Model Selection

```python
def select_model(request_body: dict, tags: set[str], client_allowed: list[str]) -> str:
    """
    1. Explicit model: request_body["model"] if present and client-allowed
    2. Tag match: first routing rule where tag ∈ tags → chain
    3. Default: config.routing.default_model
    4. Circuit check: walk chain until healthy model found
    5. If all exhausted: raise 503 Service Unavailable
    """
```

### Circuit Breaker (per model)

States: `CLOSED` (healthy) → `OPEN` (unhealthy) → `HALF_OPEN` (testing)

```
CLOSED: All requests pass through.
        If consecutive failures >= unhealthy_threshold → OPEN

OPEN:   All requests immediately fail (skip to next in chain).
        After check_interval_seconds → HALF_OPEN

HALF_OPEN: Allow one probe request.
           If success → CLOSED
           If failure → OPEN
```

No external dependencies. In-memory state. Resets on restart (safe default).

### Health Checks

Background async task pings each model endpoint every `check_interval_seconds` with a minimal request. Updates circuit state. Exposes status via `/health` endpoint.

---

## Provider Adapters

Each provider adapter implements a single interface:

```python
class ProviderAdapter(Protocol):
    async def chat_completion(
        self, request: dict, model_config: ModelConfig, stream: bool
    ) -> dict | AsyncIterator[dict]:
        """Send chat completion request, return OpenAI-format response."""
        ...

    async def health_check(self, model_config: ModelConfig) -> bool:
        """Return True if endpoint is responsive."""
        ...
```

### Built-in Adapters

| Provider | Notes |
|----------|-------|
| `openai` | Native format; pass-through with auth |
| `anthropic` | Translates OpenAI format ↔ Anthropic Messages API |
| `vllm` | OpenAI-compatible; pass-through with base_url override |
| `ollama` | OpenAI-compatible; local inference |
| `custom_http` | Generic HTTP adapter; configurable request/response mapping |

Adding a new provider: implement `ProviderAdapter`, register in `providers.py`. ~30-50 lines per adapter.

---

## Deployment

### Minimal (local/dev)

```bash
# Install
pip install pw-router

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your API keys and models

# Run
pw-router --config config.yaml
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY pw_router/ pw_router/
COPY config.yaml .
EXPOSE 8100
CMD ["pw-router", "--config", "config.yaml"]
```

### Fly.io (matches PW stack)

```toml
# fly.toml
app = "pw-router"

[build]
  dockerfile = "Dockerfile"

[env]
  CONFIG_PATH = "/app/config.yaml"

[http_service]
  internal_port = 8100
  force_https = true

[[services.ports]]
  port = 443
  handlers = ["tls", "http"]
```

Secrets via `fly secrets set ANTHROPIC_API_KEY=... RUNPOD_API_KEY=...`

---

## Dependencies (minimal by design)

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
anthropic = ["anthropic>=0.40"]     # Only if using Anthropic adapter
```

**Total: 4 required dependencies.** Compare to LiteLLM's 50+ transitive deps.

---

## Security Model

### What pw-router does:
- API key validation on every request
- Per-key model access control (allowlists)
- Tag-based routing to enforce data residency (client data → self-hosted only)
- Structured audit logging of every request (configurable body inclusion)
- Middleware hooks for PII scanning before and after model calls
- No telemetry, no phoning home, no analytics

### What pw-router does NOT do:
- Store any data (stateless; logs go to stdout for your log aggregator)
- Manage model deployments (use RunPod/vLLM/Ollama directly)
- Provide a UI (it's an API gateway, not a platform)
- Make compliance decisions (that's your middleware plugins' job)

### Supply Chain

- 4 direct dependencies, all well-established Python packages
- Pin all versions in lockfile
- Recommend `pip-audit` in CI
- SBOM generation via `pip-licenses` for compliance documentation

---

## Integration with Protocol Wealth (proprietary layer)

This section documents how PW wraps pw-router internally. **This config is NOT part of the open-source project.**

```
┌──────────────────────────────────────────────────────────┐
│                    PW Internal Stack                      │
│                                                          │
│  pw-nexus ──┐                                            │
│  pw-portal ─┤                                            │
│  pw-onchain ┤──▶  pw-router (open-source core)           │
│  pw-strat ──┘       │                                    │
│                     ├── pw-redact plugin (pre/post)       │
│                     ├── audit-log plugin → Neon           │
│                     ├── data-classifier plugin            │
│                     ├── rbac plugin → pw-portal OAuth     │
│                     └── hadrius-record plugin (future)    │
│                                                          │
│  Models:                                                 │
│  ├── Claude API (external, non-client-data)              │
│  ├── RunPod vLLM: Llama 3.1 70B (client-safe)           │
│  ├── RunPod vLLM: Qwen 2.5 72B  (client-safe)           │
│  └── pw-redact endpoint (RunPod serverless)              │
└──────────────────────────────────────────────────────────┘
```

### PW-specific middleware plugins (private repo):

1. **pw-redact-plugin**: Calls RunPod pw-redact endpoint pre/post. Auto-tags requests containing PII as `client-data`, forcing self-hosted routing.

2. **audit-log-plugin**: Writes structured audit records to Neon (request hash, client, model, timestamp, tags, latency). Retention per SEC 17a-4. Does NOT log request/response bodies by default; configurable per data classification.

3. **data-classifier-plugin**: Heuristic + model-based classification of request content. Categories: `public`, `internal`, `client-data`, `pii`. Sets routing tags accordingly.

4. **rbac-plugin**: Validates JWT from pw-portal OAuth. Maps user → role → allowed models/tags. Integrates with pw-portal's existing auth system.

---

## Roadmap

### v0.1.0 — MVP (target: ship in one Claude Code session)
- [ ] FastAPI server with `/v1/chat/completions` (streaming + non-streaming)
- [ ] YAML config loading with env var expansion
- [ ] OpenAI + vLLM provider adapters
- [ ] API key auth
- [ ] Middleware hook system (pre/post)
- [ ] Basic structured logging
- [ ] `/health` endpoint
- [ ] README + MIT LICENSE

### v0.2.0 — Hardening
- [ ] Anthropic provider adapter
- [ ] Circuit breaker per model
- [ ] Background health checks
- [ ] Fallback chains
- [ ] `/v1/models` endpoint
- [ ] `/metrics` endpoint (request counts, latency P50/P95/P99)
- [ ] `pip-audit` in CI
- [ ] Docker image + Fly.io deploy config

### v0.3.0 — Ecosystem
- [ ] Ollama provider adapter
- [ ] Custom HTTP adapter (generic)
- [ ] `/v1/embeddings` endpoint
- [ ] `/v1/completions` endpoint
- [ ] Plugin discovery (auto-load from plugins/ dir)
- [ ] SBOM generation
- [ ] PyPI publish

### Future (community-driven)
- [ ] Token counting + budget limits per API key
- [ ] Response caching (pluggable backend)
- [ ] Request queuing for rate-limited providers
- [ ] OpenTelemetry trace export
- [ ] Prometheus metrics endpoint
- [ ] WebSocket support for long-running streams

---

## Contributing

pw-router is intentionally minimal. Before adding a feature, ask:

1. **Does this belong in core or a plugin?** If it's opinionated about compliance, auth, logging destination, or data handling → plugin.
2. **Does this increase the dependency count?** Strong bias against new deps.
3. **Can a compliance officer still read the core in an afternoon?** If this PR pushes core past ~1,500 lines, it's probably doing too much.

---

## Comparison

| | pw-router | LiteLLM | Bifrost |
|---|---|---|---|
| Language | Python | Python | Go |
| License | MIT | MIT | Apache 2.0 |
| Core LOC | ~950 | ~50,000+ | ~15,000+ |
| Dependencies | 4 | 50+ | ~10 |
| Provider support | 5 built-in | 100+ | 20+ |
| Designed for | Auditability | Breadth | Performance |
| Circuit breaker | ✓ | ✓ | ✓ |
| Middleware hooks | ✓ (pre/post) | Callbacks | Plugins |
| OpenAI-compatible | ✓ | ✓ | ✓ |
| Self-hostable | ✓ | ✓ | ✓ |
| Supply chain attacks | 0 | 1 (March 2026) | 0 |
| Open GitHub issues | — | 800+ | ~50 |

---

*Built by [Protocol Wealth LLC](https://protocolwealthllc.com) — an SEC-registered RIA that actually runs client money through this.*
