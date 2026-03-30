# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""FastAPI app, lifespan, route handlers, auth middleware."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from pw_router import __version__
from pw_router.audit_log import generate_request_id, log_auth_failure, log_request
from pw_router.config import load_config
from pw_router.health import health_check_loop
from pw_router.middleware import MiddlewareContext, load_plugins_from_config
from pw_router.models import AllModelsUnavailableError, ModelNotAllowedError, ModelNotFoundError
from pw_router.providers import create_adapter
from pw_router.rate_limit import RateLimiter
from pw_router.router import RouterEngine, _is_allowed
from pw_router.usage import UsageTracker

logger = logging.getLogger("pw_router.server")

MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_STREAM_DURATION_SECONDS = 300  # 5 minutes max for streaming responses

# Allowlisted fields for chat completion requests.
# Anything not in this set is stripped before forwarding to providers.
ALLOWED_REQUEST_FIELDS = {
    "model",
    "messages",
    "temperature",
    "top_p",
    "max_tokens",
    "stream",
    "stop",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "response_format",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers and X-Request-Id to all responses."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or generate_request_id()
        request.state.request_id = request_id

        response = await call_next(request)

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "interest-cohort=()"
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def _sanitize_request_body(body: dict) -> dict:
    """Strip unknown fields from request body before forwarding to providers."""
    return {k: v for k, v in body.items() if k in ALLOWED_REQUEST_FIELDS}


def _get_remote_ip(request: Request) -> str | None:
    """Get client IP, preferring X-Forwarded-For (Fly.io sets this)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def create_app(config: dict | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        config: Pre-loaded config dict (used in tests). If None, loads from file.
    """
    injected_config = config

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = injected_config
        if cfg is None:
            path = os.environ.get("CONFIG_PATH", "config.yaml")
            cfg = load_config(path)

        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

        adapters = {}
        for model_name, model_cfg in cfg["models"].items():
            adapters[model_name] = create_adapter(model_cfg["provider"], http_client)

        router_engine = RouterEngine(cfg)
        pre_hooks, post_hooks = load_plugins_from_config(cfg.get("middleware", {}))

        # Rate limiter: configurable via config, defaults to 60 req/min per key
        rl_config = cfg.get("rate_limit", {})
        rate_limiter = RateLimiter(
            max_requests=rl_config.get("max_requests", 60),
            window_seconds=rl_config.get("window_seconds", 60),
        )

        app.state.config = cfg
        app.state.http_client = http_client
        app.state.adapters = adapters
        app.state.router_engine = router_engine
        app.state.pre_request_hooks = pre_hooks
        app.state.post_response_hooks = post_hooks
        app.state.usage = UsageTracker()
        app.state.rate_limiter = rate_limiter

        health_task = None
        interval = cfg.get("health", {}).get("check_interval_seconds", 30)
        if interval > 0:
            health_task = asyncio.create_task(
                health_check_loop(adapters, router_engine.circuits, cfg)
            )

        yield

        if health_task:
            health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health_task
        await http_client.aclose()

    application = FastAPI(
        title="pw-router",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    application.add_middleware(SecurityHeadersMiddleware)

    # --- Auth dependency ---

    async def authenticate(request: Request) -> None:
        request_id = getattr(request.state, "request_id", generate_request_id())
        auth_header = request.headers.get("authorization")
        if not auth_header:
            log_auth_failure(
                request_id=request_id,
                reason="missing_header",
                remote_ip=_get_remote_ip(request),
            )
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        if not auth_header.startswith("Bearer "):
            log_auth_failure(
                request_id=request_id,
                reason="invalid_format",
                remote_ip=_get_remote_ip(request),
            )
            raise HTTPException(status_code=401, detail="Invalid Authorization format")

        token = auth_header[7:]
        for key_cfg in request.app.state.config["server"]["api_keys"]:
            if hmac.compare_digest(token, key_cfg["key"]):
                request.state.client_name = key_cfg["name"]
                request.state.allowed_models = key_cfg["allowed_models"]
                return

        log_auth_failure(
            request_id=request_id,
            reason="invalid_key",
            remote_ip=_get_remote_ip(request),
        )
        raise HTTPException(status_code=401, detail="Invalid API key")

    # --- Routes ---

    @application.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        await authenticate(request)

        # Rate limiting per client
        client_name = request.state.client_name
        rate_limiter: RateLimiter = request.app.state.rate_limiter
        if not rate_limiter.is_allowed(client_name):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        request_id = getattr(request.state, "request_id", generate_request_id())

        # Enforce body size limit on actual bytes, not Content-Length header
        body_bytes = await request.body()
        if len(body_bytes) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large (max 10MB)")

        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        # Strip unknown fields before forwarding to providers
        body = _sanitize_request_body(body)

        allowed_models = request.state.allowed_models
        router_engine: RouterEngine = request.app.state.router_engine
        adapters = request.app.state.adapters
        models_config = request.app.state.config["models"]

        # 1. Create middleware context
        ctx = MiddlewareContext(
            request_body=body,
            client_name=client_name,
        )

        # 2. Run pre-request middleware
        for hook, hook_config in request.app.state.pre_request_hooks:
            ctx.config = hook_config
            result = await hook(ctx)
            if not result.allow:
                return JSONResponse(
                    status_code=result.status_code,
                    content={"error": {"message": result.error_message}},
                )

        # 3. Select model
        requested_model = ctx.request_body.get("model")
        try:
            model_name = router_engine.select_model(requested_model, ctx.tags, allowed_models)
        except ModelNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ModelNotAllowedError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
        except AllModelsUnavailableError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

        # 4. Get adapter and config
        adapter = adapters[model_name]
        model_cfg = models_config[model_name]
        is_stream = ctx.request_body.get("stream", False)
        start = time.monotonic()

        # 5. Forward request
        usage_tracker: UsageTracker = request.app.state.usage
        try:
            if is_stream:
                stream = await adapter.chat_completion(ctx.request_body, model_cfg, stream=True)
                usage_tracker.record_stream_request(client_name, model_name)
                log_request(
                    request_id=request_id,
                    client_name=client_name,
                    model=model_name,
                    provider=model_cfg["provider"],
                    status="streaming",
                    latency_ms=0,
                    stream=True,
                )
                return StreamingResponse(
                    _wrap_stream(stream, model_name, router_engine, start),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                        "X-Request-Id": request_id,
                    },
                )
            else:
                response_data = await adapter.chat_completion(
                    ctx.request_body, model_cfg, stream=False
                )
                latency_ms = (time.monotonic() - start) * 1000
                router_engine.record_success(model_name)

                # Record token usage
                resp_usage = response_data.get("usage", {})
                p_tokens = resp_usage.get("prompt_tokens", 0)
                c_tokens = resp_usage.get("completion_tokens", 0)
                usage_tracker.record_request(
                    client_name=client_name,
                    model_name=model_name,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    latency_ms=latency_ms,
                )

                # Audit log
                log_request(
                    request_id=request_id,
                    client_name=client_name,
                    model=model_name,
                    provider=model_cfg["provider"],
                    status="ok",
                    latency_ms=latency_ms,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                )

                # Override model name to router alias
                response_data["model"] = model_name

                # 6. Run post-response middleware
                ctx.response_body = response_data
                ctx.model_used = model_name
                ctx.latency_ms = latency_ms
                ctx.provider = model_cfg["provider"]
                for hook, hook_config in request.app.state.post_response_hooks:
                    ctx.config = hook_config
                    result = await hook(ctx)
                    if not result.allow:
                        return JSONResponse(
                            status_code=result.status_code,
                            content={"error": {"message": result.error_message}},
                        )

                return JSONResponse(content=ctx.response_body)

        except httpx.HTTPStatusError as e:
            latency_ms = (time.monotonic() - start) * 1000
            router_engine.record_failure(model_name)
            usage_tracker.record_error(client_name, model_name)
            log_request(
                request_id=request_id,
                client_name=client_name,
                model=model_name,
                provider=model_cfg["provider"],
                status="provider_error",
                latency_ms=latency_ms,
                error=f"status_{e.response.status_code}",
            )
            raise HTTPException(
                status_code=502,
                detail="Upstream provider error",
            ) from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            latency_ms = (time.monotonic() - start) * 1000
            router_engine.record_failure(model_name)
            usage_tracker.record_error(client_name, model_name)
            log_request(
                request_id=request_id,
                client_name=client_name,
                model=model_name,
                provider=model_cfg["provider"],
                status="provider_unavailable",
                latency_ms=latency_ms,
                error=type(e).__name__,
            )
            raise HTTPException(
                status_code=502,
                detail="Upstream provider unavailable",
            ) from e

    @application.get("/v1/models")
    async def list_models(request: Request):
        await authenticate(request)
        allowed = request.state.allowed_models
        models_config = request.app.state.config["models"]

        data = []
        for name, cfg in models_config.items():
            if _is_allowed(name, allowed):
                data.append(
                    {
                        "id": name,
                        "object": "model",
                        "owned_by": cfg.get("provider", "unknown"),
                    }
                )
        return {"object": "list", "data": data}

    @application.get("/metrics")
    async def metrics(request: Request):
        await authenticate(request)
        usage_tracker: UsageTracker = request.app.state.usage
        return usage_tracker.snapshot()

    @application.get("/")
    async def root():
        return {
            "service": "pw-router",
            "version": __version__,
            "description": "Minimal, auditable LLM routing gateway",
            "docs": "https://github.com/Protocol-Wealth/pw-router",
            "endpoints": {
                "POST /v1/chat/completions": "OpenAI-compatible chat completions",
                "GET /v1/models": "List available models (requires auth)",
                "GET /health": "Router health + per-model circuit breaker status",
                "GET /metrics": "Token usage per client and model (requires auth)",
            },
        }

    security_txt_body = (
        "Contact: mailto:security@protocolwealthllc.com\n"
        "Expires: 2027-04-01T00:00:00.000Z\n"
        "Preferred-Languages: en\n"
        "Policy: https://github.com/Protocol-Wealth/pw-router/blob/main/SECURITY.md\n"
    )

    @application.get("/robots.txt", response_class=PlainTextResponse)
    async def robots_txt():
        return "User-agent: *\nDisallow: /\n"

    @application.get("/security.txt", response_class=PlainTextResponse)
    async def security_txt_root():
        return security_txt_body

    @application.get("/.well-known/security.txt", response_class=PlainTextResponse)
    async def security_txt():
        return security_txt_body

    @application.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @application.get("/health")
    async def health_check(request: Request):
        router_engine: RouterEngine = request.app.state.router_engine
        models_status = {}
        for name, cb in router_engine.circuits.items():
            models_status[name] = {
                "status": "healthy" if cb.state.value == "closed" else "unhealthy",
                "circuit": cb.state.value,
            }
        return {
            "status": "healthy",
            "version": __version__,
            "models": models_status,
        }

    return application


async def _wrap_stream(
    stream: AsyncIterator[str],
    model_name: str,
    router_engine: RouterEngine,
    start_time: float,
) -> AsyncIterator[str]:
    """Wrap a provider stream to record metrics and enforce timeout."""
    try:
        async with asyncio.timeout(MAX_STREAM_DURATION_SECONDS):
            async for chunk in stream:
                yield chunk
        router_engine.record_success(model_name)
    except TimeoutError:
        router_engine.record_failure(model_name)
        logger.warning(
            "Stream timeout for model %s after %ds", model_name, MAX_STREAM_DURATION_SECONDS
        )
    except Exception:
        router_engine.record_failure(model_name)
        raise


# Module-level app for `uvicorn pw_router.server:app`
app = create_app()
