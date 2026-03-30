# AGENTS.md — AI Assistant Guide for pw-router

> Instructions for AI coding assistants (Claude Code, Cursor, Copilot, etc.)
> working on or integrating with pw-router.

## Project Context

pw-router is an open-source, MIT-licensed LLM routing gateway. It is intentionally
minimal (~1,100 lines of core) and must stay that way. Every design decision
prioritizes auditability over features.

**Owner:** Protocol Wealth LLC (SEC-registered investment adviser)
**Repo:** github.com/Protocol-Wealth/pw-router
**Live:** pw-router.fly.dev (Fly.io, ORD region)
**Stack:** Python 3.12, FastAPI, httpx, PyYAML
**Tests:** 103 tests — pytest + pytest-asyncio + respx (mocked HTTP, no real API calls)

## Ground Rules

### Do

- Keep core under ~1,500 lines total across `pw_router/`
- Use type hints on all function signatures
- Add the MIT license header to every new `.py` file
- Write tests for new functionality (mock HTTP with `respx`)
- Run `ruff check` and `pytest` before proposing changes
- Keep the dependency count at 4 runtime deps — strong bias against adding more
- Use `hmac.compare_digest` for any secret comparison
- Fail fast on config errors (startup, not request time)
- Regenerate `requirements.lock` after any dependency change (`pip-compile`)
- Place new middleware plugins in `plugins/` directory only
- Add new request fields to `ALLOWED_REQUEST_FIELDS` in `server.py` if needed

### Do Not

- Add features that belong in a middleware plugin (compliance, auth beyond API keys, logging destinations, PII handling, data classification)
- Log request/response bodies by default
- Write to disk (pw-router is fully stateless)
- Add telemetry, analytics, or any external calls except to configured providers
- Commit secrets, API keys, real config, or deployment files (fly.toml, Dockerfile.fly, config.yaml, .env)
- Reference internal Protocol Wealth URLs, clients, or business processes
- Add dependencies without explicit discussion
- Load plugin modules from outside the `plugins.*` namespace
- Return provider-specific error details (status codes, exception types) to clients

### Open Source Boundaries

**Public (this repo):** All routing logic, provider adapters, circuit breaker, health checks, middleware system, example plugins, tests, documentation.

**Private (never in this repo):** API keys, production configs, internal PW URLs (nexusmcp.site, pwdashboard.com), PW-specific middleware plugins, regulatory governance docs (AGENTS.md from PW workspace is different from this file), client data.

## Architecture Quick Reference

```
pw_router/
├── server.py      # FastAPI app, routes, auth, security headers, body sanitization
├── router.py      # RouterEngine: select_model(), CircuitBreaker, fallback chains
├── providers.py   # ProviderAdapter protocol + OpenAI, Anthropic, vLLM adapters
├── middleware.py   # MiddlewareContext, MiddlewareResult, load_plugin() (namespace-restricted)
├── config.py      # load_config(), expand_env_vars(), validate_config()
├── health.py      # health_check_loop() — background async task
├── models.py      # Exception classes (ModelNotFoundError, etc.)
└── __main__.py    # CLI entry point
```

### Request Flow

```
Auth (server.py)
→ Body size check (actual bytes, not Content-Length)
→ JSON parse + validate
→ Field sanitization (allowlist: ALLOWED_REQUEST_FIELDS)
→ Pre-hooks (middleware.py)
→ Model select (router.py)
→ Provider call (providers.py)
→ Post-hooks (middleware.py)
→ Security headers added (SecurityHeadersMiddleware)
→ Response
```

### Key Patterns

- **Single httpx.AsyncClient** shared across all adapters (created in lifespan, closed on shutdown, explicit pool limits: 100 max connections, 20 keepalive)
- **Circuit breaker** per model, in-memory, resets on restart
- **Config** loaded once at startup from YAML with `${ENV_VAR}` expansion
- **Middleware** loaded via `importlib.import_module`, restricted to `plugins.*` namespace. Load failures are fatal (fail-closed).
- **Auth** is API key in Bearer token, compared with `hmac.compare_digest`
- **Body sanitization** strips unknown fields before forwarding to providers
- **Stream timeout** 5-minute max via `asyncio.timeout` in `_wrap_stream`
- **Error messages** are generic to clients; details logged server-side only

### Security Controls

| Control | Location | Description |
|---------|----------|-------------|
| Field allowlist | `server.py:ALLOWED_REQUEST_FIELDS` | Only permitted fields forwarded to providers |
| Body size check | `server.py:157-159` | Enforced on actual bytes, not Content-Length header |
| Stream timeout | `server.py:MAX_STREAM_DURATION_SECONDS` | 5-minute max for streaming responses |
| Plugin namespace | `middleware.py:ALLOWED_PLUGIN_PREFIXES` | Only `plugins.*` modules can be loaded |
| Fail-closed plugins | `middleware.py:load_plugins_from_config` | Server won't start if plugin fails to load |
| Security headers | `server.py:SecurityHeadersMiddleware` | nosniff, DENY, no-referrer, no-store |
| Generic errors | `server.py:250-265` | No provider details leaked to clients |
| Pool limits | `server.py:88-91` | Explicit httpx connection limits |
| Non-root container | `Dockerfile` | Runs as `appuser` |
| Pinned deps | `requirements.lock` | All transitive dependencies pinned |

## How to Add Things

### New Provider Adapter

1. Create class in `providers.py` implementing `ProviderAdapter` protocol
2. If OpenAI-compatible: subclass `OpenAIAdapter` (~5 lines)
3. If custom format: implement `chat_completion()` and `health_check()` with translation
4. Register in `create_adapter()` factory function
5. Add provider name to `valid_providers` set in `config.py`
6. Add tests in `tests/test_providers.py` using `respx` mocks

### New Middleware Plugin

1. Create `plugins/your_plugin.py` with `pre_request()` and/or `post_response()`
2. Both are async functions taking `MiddlewareContext`, returning `MiddlewareResult`
3. Module path MUST start with `plugins.` (enforced by `ALLOWED_PLUGIN_PREFIXES`)
4. Register in `config.yaml` under `middleware.pre_request` or `middleware.post_response`
5. Plugin config from YAML passed via `ctx.config`
6. Load failures are fatal — server won't start if your plugin can't be imported

### New API Endpoint

1. Add route handler in `server.py`
2. Follow existing pattern: `authenticate()` → business logic → `JSONResponse`
3. Add tests in `tests/test_server.py`
4. Update `llms.txt` and `llms-full.txt` with the new endpoint

### New Allowed Request Field

If a legitimate OpenAI API field needs to be forwarded:
1. Add it to `ALLOWED_REQUEST_FIELDS` set in `server.py`
2. Verify the field is safe (no cost amplification like `n`, no impersonation like `user`)
3. Add a test in `TestRequestSanitization` verifying it passes through

## Testing

```bash
pytest -v              # All 103 tests
pytest -v -k router    # Just router tests
pytest --cov=pw_router # With coverage
```

All provider HTTP calls are mocked with `respx`. The `sample_config` fixture in
`tests/conftest.py` provides a minimal config for test use. App instances are
created via `create_app(config=sample_config)` to avoid loading from disk.

## Commands

```bash
pip install -e ".[dev]"           # Dev install
ruff check pw_router/ tests/      # Lint
ruff format pw_router/ tests/     # Format
pw-router --config config.yaml    # Run
python -m pw_router               # Alternative run
pytest -v --tb=short              # Test
pip-compile --output-file=requirements.lock pyproject.toml  # Regen lockfile
```

## Version & Roadmap

**Current: v0.1.0** — chat completions (streaming + non-streaming), 3 provider adapters, circuit breaker, fallback chains, middleware hooks, health checks, security hardening, full test suite (103 tests).

**Next: v0.2.0** — /v1/completions, /v1/embeddings, /metrics, Ollama adapter, token counting.
