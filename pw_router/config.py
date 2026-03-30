# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""YAML config loader with environment variable expansion."""

import os
import re

import yaml


def expand_env_vars(value: str) -> str:
    """Expand ${VAR_NAME} patterns in config string values."""
    if not isinstance(value, str) or "${" not in value:
        return value

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(f"Environment variable {var_name} not set")
        return env_val

    return re.sub(r"\$\{([^}]+)}", replacer, value)


def _expand_recursive(obj: object) -> object:
    """Recursively expand env vars in a config structure."""
    if isinstance(obj, str):
        return expand_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _expand_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_recursive(item) for item in obj]
    return obj


def load_config(path: str = "config.yaml") -> dict:
    """Load and validate router config from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not raw or not isinstance(raw, dict):
        raise ValueError(f"Invalid config file: {path}")
    config = _expand_recursive(raw)
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    """Validate required config sections exist."""
    if "server" not in config:
        raise ValueError("Config missing 'server' section")
    if "api_keys" not in config["server"] or not config["server"]["api_keys"]:
        raise ValueError("Config missing 'server.api_keys'")
    if "models" not in config or not config["models"]:
        raise ValueError("Config missing 'models' section")
    if "routing" not in config:
        raise ValueError("Config missing 'routing' section")
    if "default_model" not in config["routing"]:
        raise ValueError("Config missing 'routing.default_model'")

    default = config["routing"]["default_model"]
    if default not in config["models"]:
        raise ValueError(
            f"routing.default_model '{default}' not found in models"
        )

    valid_providers = {"openai", "anthropic", "vllm", "ollama", "custom_http"}
    for name, model_cfg in config["models"].items():
        if "provider" not in model_cfg:
            raise ValueError(f"Model '{name}' missing 'provider'")
        if model_cfg["provider"] not in valid_providers:
            raise ValueError(
                f"Model '{name}' has invalid provider '{model_cfg['provider']}'"
            )
