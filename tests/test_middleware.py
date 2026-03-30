# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for middleware context, hooks, and plugin loading."""

import pytest

from pw_router.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    load_plugin,
    load_plugins_from_config,
)


class TestMiddlewareContext:
    def test_defaults(self):
        ctx = MiddlewareContext(
            request_body={"model": "test"},
            client_name="client",
        )
        assert ctx.tags == set()
        assert ctx.metadata == {}
        assert ctx.response_body is None
        assert ctx.model_used is None

    def test_mutable_tags(self):
        ctx = MiddlewareContext(request_body={}, client_name="c")
        ctx.tags.add("pii")
        ctx.tags.add("client-data")
        assert "pii" in ctx.tags
        assert "client-data" in ctx.tags


class TestMiddlewareResult:
    def test_defaults(self):
        result = MiddlewareResult()
        assert result.allow is True
        assert result.error_message is None
        assert result.status_code == 400

    def test_blocking(self):
        result = MiddlewareResult(
            allow=False, error_message="Blocked", status_code=403
        )
        assert result.allow is False
        assert result.error_message == "Blocked"


class TestHookExecution:
    @pytest.mark.asyncio
    async def test_pre_request_modifies_body(self):
        async def hook(ctx: MiddlewareContext) -> MiddlewareResult:
            ctx.request_body["injected"] = True
            return MiddlewareResult(allow=True)

        ctx = MiddlewareContext(
            request_body={"model": "test"}, client_name="c"
        )
        result = await hook(ctx)
        assert result.allow is True
        assert ctx.request_body["injected"] is True

    @pytest.mark.asyncio
    async def test_pre_request_adds_tags(self):
        async def hook(ctx: MiddlewareContext) -> MiddlewareResult:
            ctx.tags.add("tagged")
            return MiddlewareResult(allow=True)

        ctx = MiddlewareContext(request_body={}, client_name="c")
        await hook(ctx)
        assert "tagged" in ctx.tags

    @pytest.mark.asyncio
    async def test_pre_request_blocks(self):
        async def hook(ctx: MiddlewareContext) -> MiddlewareResult:
            return MiddlewareResult(
                allow=False, error_message="Denied", status_code=403
            )

        ctx = MiddlewareContext(request_body={}, client_name="c")
        result = await hook(ctx)
        assert result.allow is False
        assert result.error_message == "Denied"

    @pytest.mark.asyncio
    async def test_post_response_receives_body(self):
        async def hook(ctx: MiddlewareContext) -> MiddlewareResult:
            assert ctx.response_body is not None
            assert ctx.model_used == "test-model"
            return MiddlewareResult(allow=True)

        ctx = MiddlewareContext(
            request_body={},
            client_name="c",
            response_body={"choices": []},
            model_used="test-model",
            latency_ms=100.0,
        )
        result = await hook(ctx)
        assert result.allow is True

    @pytest.mark.asyncio
    async def test_hooks_execute_in_order(self):
        order = []

        async def hook1(ctx: MiddlewareContext) -> MiddlewareResult:
            order.append(1)
            return MiddlewareResult(allow=True)

        async def hook2(ctx: MiddlewareContext) -> MiddlewareResult:
            order.append(2)
            return MiddlewareResult(allow=True)

        ctx = MiddlewareContext(request_body={}, client_name="c")
        for hook in [hook1, hook2]:
            await hook(ctx)
        assert order == [1, 2]


class TestLoadPlugin:
    def test_load_existing_plugin(self):
        hook = load_plugin("plugins.example_redact", "pre_request")
        assert callable(hook)

    def test_load_logger_plugin(self):
        hook = load_plugin("plugins.example_logger", "post_response")
        assert callable(hook)

    def test_missing_function_raises(self):
        with pytest.raises(ValueError, match="no pre_request"):
            load_plugin("plugins.example_logger", "pre_request")

    def test_missing_module_raises(self):
        with pytest.raises(ModuleNotFoundError):
            load_plugin("plugins.nonexistent_plugin", "pre_request")


class TestLoadPluginsFromConfig:
    def test_empty_config(self):
        pre, post = load_plugins_from_config({})
        assert pre == []
        assert post == []

    def test_loads_pre_request(self):
        config = {
            "pre_request": [
                {"plugin": "plugins.example_redact", "config": {"endpoint": "http://test"}},
            ],
            "post_response": [],
        }
        pre, post = load_plugins_from_config(config)
        assert len(pre) == 1
        assert pre[0][1] == {"endpoint": "http://test"}
        assert post == []

    def test_loads_post_response(self):
        config = {
            "pre_request": [],
            "post_response": [
                {"plugin": "plugins.example_logger", "config": {}},
            ],
        }
        pre, post = load_plugins_from_config(config)
        assert pre == []
        assert len(post) == 1

    def test_invalid_plugin_skipped(self):
        config = {
            "pre_request": [
                {"plugin": "plugins.nonexistent_xyz", "config": {}},
            ],
            "post_response": [],
        }
        pre, post = load_plugins_from_config(config)
        assert pre == []
