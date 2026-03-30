# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Pre/post request hook system with plugin loading."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("pw_router.middleware")

# Only allow loading plugins from these module prefixes.
# Prevents arbitrary code execution via config.yaml plugin paths.
ALLOWED_PLUGIN_PREFIXES = ("plugins.",)


@dataclass
class MiddlewareContext:
    """Context passed through middleware pipeline."""

    request_body: dict
    client_name: str
    tags: set[str] = field(default_factory=set)
    metadata: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
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


MiddlewareHook = Callable[[MiddlewareContext], Awaitable[MiddlewareResult]]


def load_plugin(module_path: str, hook_name: str) -> MiddlewareHook:
    """Load a middleware hook function from a module.

    Args:
        module_path: Dotted module path (e.g., "plugins.example_redact")
        hook_name: Function name ("pre_request" or "post_response")

    Returns:
        Async callable middleware hook function.

    Raises:
        ValueError: If module path is not in the allowed namespace or hook not found.
    """
    if not any(module_path.startswith(prefix) for prefix in ALLOWED_PLUGIN_PREFIXES):
        raise ValueError(
            f"Plugin path '{module_path}' not in allowed namespace. "
            f"Plugins must start with one of: {ALLOWED_PLUGIN_PREFIXES}"
        )
    module = importlib.import_module(module_path)
    hook = getattr(module, hook_name, None)
    if hook is None:
        raise ValueError(f"Plugin {module_path} has no {hook_name} function")
    return hook


def load_plugins_from_config(
    middleware_config: dict,
) -> tuple[list[tuple[MiddlewareHook, dict]], list[tuple[MiddlewareHook, dict]]]:
    """Load pre/post hooks from middleware config section.

    Returns:
        Tuple of (pre_request_hooks, post_response_hooks).
        Each hook is paired with its plugin-specific config dict.

    Raises:
        ValueError: If a plugin fails to load (fail-closed for security).
    """
    pre_hooks: list[tuple[MiddlewareHook, dict]] = []
    post_hooks: list[tuple[MiddlewareHook, dict]] = []

    for entry in middleware_config.get("pre_request", []):
        plugin_path = entry["plugin"]
        plugin_config = entry.get("config", {})
        try:
            hook = load_plugin(plugin_path, "pre_request")
            pre_hooks.append((hook, plugin_config))
        except Exception:
            logger.exception("Failed to load pre_request plugin: %s", plugin_path)
            raise

    for entry in middleware_config.get("post_response", []):
        plugin_path = entry["plugin"]
        plugin_config = entry.get("config", {})
        try:
            hook = load_plugin(plugin_path, "post_response")
            post_hooks.append((hook, plugin_config))
        except Exception:
            logger.exception("Failed to load post_response plugin: %s", plugin_path)
            raise

    return pre_hooks, post_hooks
