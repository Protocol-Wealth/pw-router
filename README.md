# pw-router

**A minimal, auditable LLM gateway for regulated environments.**

[![CI](https://github.com/Protocol-Wealth/pw-router/actions/workflows/ci.yml/badge.svg)](https://github.com/Protocol-Wealth/pw-router/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

MIT License | Python 3.12 / FastAPI | 4 dependencies | ~1,000 lines of core

Built by [Protocol Wealth LLC](https://protocolwealthllc.com), an SEC-registered
investment adviser that actually routes client-adjacent AI workloads through this.

> The selling point isn't speed benchmarks.
> It's that a compliance officer can read the entire codebase in an afternoon.

---

## Why This Exists

In March 2025, [LiteLLM suffered a supply-chain attack](https://www.securityweek.com/malicious-litellm-package-targets-developers/) via a compromised dependency. LiteLLM has 50+ transitive dependencies, 800+ open GitHub issues, and a codebase that's impossible for a compliance team to audit.

If you're routing AI workloads in a regulated environment — financial services, healthcare, legal — you need a gateway you can actually read, understand, and sign off on. pw-router is that gateway.

**What pw-router does:**
- OpenAI-compatible API in front of multiple LLM providers
- Circuit breaker per model with automatic fallback chains
- Tag-based routing (e.g., PII-flagged requests → self-hosted models only)
- Pluggable middleware for compliance hooks (PII scanning, audit logging, RBAC)
- YAML config with env var expansion — no database required

**What pw-router does NOT do:**
- Store any data (stateless — logs go to stdout for your log aggregator)
- Make compliance decisions (that's your middleware plugins' job)
- Provide a UI (it's an API gateway, not a platform)
- Phone home, collect telemetry, or run analytics

---

## How It Works

```
Client (OpenAI SDK)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                      pw-router                          │
│                                                         │
│  1. Auth ─── Validate API key, resolve client identity  │
│       │                                                 │
│  2. Pre-request middleware ─── PII scan, tag, log       │
│       │                                                 │
│  3. Router engine                                       │
│       ├── Match: explicit model / tag rule / default    │
│       ├── Circuit breaker: skip unhealthy providers     │
│       └── Fallback chain: try next if primary is down   │
│       │                                                 │
│  4. Provider adapter ─── Translate to provider format   │
│       │                                                 │
│  5. Post-response middleware ─── Audit, PII scan output │
│       │                                                 │
│  6. Return OpenAI-format response                       │
└─────────────────────────────────────────────────────────┘
    │
    ▼
LLM Providers (Anthropic, OpenAI, vLLM/RunPod, Ollama, ...)
```

The entire core is 8 files:

```
pw_router/
├── server.py      # FastAPI app, routes, auth         (263 lines)
├── providers.py   # OpenAI, Anthropic, vLLM adapters  (306 lines)
├── router.py      # Model selection, circuit breaker   (175 lines)
├── middleware.py   # Pre/post hook system, plugin loader (93 lines)
├── config.py      # YAML loader, env var expansion      (77 lines)
├── health.py      # Background health checks            (51 lines)
├── models.py      # Shared exceptions                   (29 lines)
└── __main__.py    # CLI entry point                     (33 lines)
```

---

## Quick Start

### Install

```bash
pip install pw-router
```

Or from source:

```bash
git clone https://github.com/Protocol-Wealth/pw-router.git
cd pw-router
pip install -e ".[dev]"
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your provider API keys and models:

```yaml
server:
  host: "0.0.0.0"
  port: 8100
  api_keys:
    - key: "${PW_ROUTER_API_KEY_1}"
      name: "my-app"
      allowed_models: ["*"]

models:
  claude-sonnet:
    provider: anthropic
    model: "claude-sonnet-4-20250514"
    api_key: "${ANTHROPIC_API_KEY}"
    timeout_seconds: 120
    tags: ["external", "reasoning"]

  local-llama:
    provider: vllm
    model: "meta-llama/Llama-3.1-70B-Instruct"
    api_key: "${RUNPOD_API_KEY}"
    base_url: "https://api.runpod.ai/v2/${RUNPOD_ENDPOINT_ID}/openai/v1"
    timeout_seconds: 90
    tags: ["self-hosted", "client-safe"]

routing:
  default_model: "claude-sonnet"
  fallback_chains:
    reasoning: ["claude-sonnet", "local-llama"]
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
```

Environment variables referenced as `${VAR_NAME}` in the YAML are expanded at load time.

### Run

```bash
# Set your env vars
export ANTHROPIC_API_KEY=sk-ant-...
export PW_ROUTER_API_KEY_1=your-secret-key

# Start the router
pw-router --config config.yaml

# Or with uvicorn directly
uvicorn pw_router.server:app --host 0.0.0.0 --port 8100
```

### Use

Any OpenAI SDK client works out of the box:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8100/v1",
    api_key="your-secret-key",
)

# Non-streaming
response = client.chat.completions.create(
    model="claude-sonnet",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# Streaming
for chunk in client.chat.completions.create(
    model="claude-sonnet",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="")
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completions (streaming + non-streaming) |
| GET | `/v1/models` | List available models (filtered by API key) |
| GET | `/health` | Router health + per-model circuit breaker status |

All endpoints accept `Authorization: Bearer <your-api-key>` (except `/health`).

### POST /v1/chat/completions

Standard OpenAI chat completions format. Supports `stream: true`.

### GET /v1/models

Returns models the authenticated client is allowed to use:

```json
{
  "object": "list",
  "data": [
    {"id": "claude-sonnet", "object": "model", "owned_by": "anthropic"},
    {"id": "local-llama", "object": "model", "owned_by": "vllm"}
  ]
}
```

### GET /health

No auth required. Returns per-model circuit breaker state:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "models": {
    "claude-sonnet": {"status": "healthy", "circuit": "closed"},
    "local-llama": {"status": "unhealthy", "circuit": "open"}
  }
}
```

---

## Configuration Reference

See [`config.example.yaml`](config.example.yaml) for a complete template.

### API Key Auth

Each API key has a name (for audit logging) and a model allowlist:

```yaml
server:
  api_keys:
    - key: "${KEY_1}"
      name: "backend"
      allowed_models: ["*"]           # Wildcard — all models
    - key: "${KEY_2}"
      name: "frontend"
      allowed_models: ["local-*"]     # Glob — only self-hosted
```

### Routing

**Explicit model:** Client specifies `"model": "claude-sonnet"` in the request. Routed directly if client is allowed.

**Tag-based rules:** Middleware plugins add tags (e.g., `"client-data"`), which match routing rules:

```yaml
routing:
  rules:
    - match:
        tag: "client-data"
      route_to_chain: "client-safe"   # Only self-hosted models
```

**Fallback chains:** If the selected model's circuit breaker is open, the router walks the fallback chain until it finds a healthy model:

```yaml
routing:
  fallback_chains:
    reasoning: ["claude-sonnet", "gpt-4o", "local-llama"]
```

### Circuit Breaker

Per-model, in-memory. Resets on restart (safe default).

```
CLOSED  ──(3 consecutive failures)──▶  OPEN
OPEN    ──(30s cooldown)──▶            HALF_OPEN
HALF_OPEN ──(1 success)──▶            CLOSED
HALF_OPEN ──(1 failure)──▶            OPEN
```

---

## Writing Plugins

Plugins are Python modules with `pre_request` and/or `post_response` async functions.

```python
# plugins/my_plugin.py
from pw_router.middleware import MiddlewareContext, MiddlewareResult

async def pre_request(ctx: MiddlewareContext) -> MiddlewareResult:
    """Called before the request is sent to the provider."""
    # ctx.request_body — mutable OpenAI-format request dict
    # ctx.client_name  — authenticated client identity
    # ctx.tags         — mutable set; add tags to influence routing
    # ctx.metadata     — mutable dict; pass data to post_response
    # ctx.config       — plugin-specific config from YAML

    if contains_pii(ctx.request_body):
        ctx.tags.add("client-data")  # Route to self-hosted only

    return MiddlewareResult(allow=True)

async def post_response(ctx: MiddlewareContext) -> MiddlewareResult:
    """Called after the response is received."""
    # ctx.response_body — OpenAI-format response dict
    # ctx.model_used    — actual model name
    # ctx.latency_ms    — request latency
    # ctx.provider      — provider name

    log_audit_event(ctx)
    return MiddlewareResult(allow=True)
```

Register in `config.yaml`:

```yaml
middleware:
  pre_request:
    - plugin: "plugins.my_plugin"
      config:
        some_setting: "value"
  post_response:
    - plugin: "plugins.my_plugin"
```

To block a request, return `MiddlewareResult(allow=False, error_message="Reason", status_code=403)`.

See [`plugins/example_redact.py`](plugins/example_redact.py) and [`plugins/example_logger.py`](plugins/example_logger.py) for working examples. Full plugin guide: [`docs/plugins.md`](docs/plugins.md).

---

## Provider Adapters

| Provider | Adapter | Notes |
|----------|---------|-------|
| OpenAI | `openai` | Native format pass-through |
| Anthropic | `anthropic` | Translates OpenAI ↔ Anthropic Messages API |
| vLLM / RunPod | `vllm` | OpenAI-compatible with custom `base_url` |

Each adapter implements:
- `chat_completion(body, model_config, stream=False)` — send request, return OpenAI-format response
- `health_check(model_config)` — return `True` if endpoint is responsive

Adding a provider is ~30-50 lines. See [`docs/architecture.md`](docs/architecture.md).

---

## Deployment

### Docker

```bash
docker build -t pw-router .
docker run -p 8100:8100 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e PW_ROUTER_API_KEY_1=your-key \
  -v $(pwd)/config.yaml:/app/config.yaml \
  pw-router
```

### Fly.io

```bash
cp fly.toml.example fly.toml
# Edit fly.toml with your app name
fly launch
fly secrets set ANTHROPIC_API_KEY=sk-ant-... PW_ROUTER_API_KEY_1=your-key
fly deploy
```

See [`docs/deployment.md`](docs/deployment.md) for detailed instructions.

---

## Comparison

| | pw-router | LiteLLM | Bifrost |
|---|---|---|---|
| Language | Python | Python | Go |
| License | MIT | MIT | Apache 2.0 |
| Core LOC | ~1,000 | ~50,000+ | ~15,000+ |
| Dependencies | 4 | 50+ | ~10 |
| Provider support | 3 built-in | 100+ | 20+ |
| Designed for | Auditability | Breadth | Performance |
| Circuit breaker | Yes | Yes | Yes |
| Fallback chains | Yes | Yes | Yes |
| Middleware hooks | Pre/post | Callbacks | Plugins |
| OpenAI-compatible | Yes | Yes | Yes |

pw-router deliberately trades breadth for auditability. If you need 100 provider integrations, use LiteLLM. If you need to hand your codebase to a compliance officer and have them understand it by lunch, use pw-router.

---

## Roadmap

### v0.1.0 (current)
- [x] `/v1/chat/completions` (streaming + non-streaming)
- [x] `/v1/models` and `/health`
- [x] OpenAI, Anthropic, and vLLM provider adapters
- [x] YAML config with env var expansion
- [x] API key auth with per-key model allowlists
- [x] Circuit breaker per model with fallback chains
- [x] Pluggable pre/post middleware hooks
- [x] Background health checks
- [x] Full test suite

### v0.2.0 (next)
- [ ] `/v1/completions` and `/v1/embeddings`
- [ ] `/metrics` endpoint (request counts, latency percentiles)
- [ ] Ollama adapter
- [ ] Custom HTTP adapter (generic)
- [ ] Token counting / budget limits per API key
- [ ] Response caching

---

## Contributing

pw-router is intentionally minimal. Before adding a feature, ask:

1. **Does this belong in core or a plugin?** Anything opinionated about compliance, auth, logging, or data handling should be a plugin.
2. **Does this increase the dependency count?** Strong bias against new dependencies.
3. **Can a compliance officer still read the core in an afternoon?** If a PR pushes core past ~1,500 lines, it's probably doing too much.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

---

## Security

Report vulnerabilities via [SECURITY.md](SECURITY.md). Do **not** open a public issue.

---

## License

MIT. See [LICENSE](LICENSE).

Architectural patterns (circuit breaker, fallback chains, health-check loops) are informed by [Bifrost](https://github.com/maximhq/bifrost) (Apache 2.0, Maxim AI). No code was copied; patterns were reimplemented in Python/FastAPI. Per Apache 2.0 Section 4, this notice serves as attribution.

---

*Built by [Protocol Wealth LLC](https://protocolwealthllc.com) — SEC-registered investment adviser (CRD #335298).*
