# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for config loading and env var expansion."""

import os
import tempfile

import pytest
import yaml

from pw_router.config import (
    _expand_recursive,
    expand_env_vars,
    load_config,
    validate_config,
)


class TestExpandEnvVars:
    def test_no_expansion(self):
        assert expand_env_vars("plain string") == "plain string"

    def test_single_var(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "secret123")
        assert expand_env_vars("${TEST_KEY}") == "secret123"

    def test_var_in_string(self, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        assert expand_env_vars("https://${HOST}/api") == "https://example.com/api"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "8080")
        result = expand_env_vars("${HOST}:${PORT}")
        assert result == "example.com:8080"

    def test_missing_env_var_raises(self):
        with pytest.raises(ValueError, match="NONEXISTENT_VAR_12345 not set"):
            expand_env_vars("${NONEXISTENT_VAR_12345}")

    def test_non_string_passthrough(self):
        assert expand_env_vars(42) == 42
        assert expand_env_vars(None) is None
        assert expand_env_vars(True) is True


class TestExpandRecursive:
    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("KEY", "value")
        obj = {"a": {"b": "${KEY}"}}
        result = _expand_recursive(obj)
        assert result == {"a": {"b": "value"}}

    def test_list(self, monkeypatch):
        monkeypatch.setenv("X", "y")
        obj = ["${X}", "plain", 42]
        result = _expand_recursive(obj)
        assert result == ["y", "plain", 42]

    def test_mixed(self, monkeypatch):
        monkeypatch.setenv("V", "expanded")
        obj = {"list": [{"key": "${V}"}], "num": 5}
        result = _expand_recursive(obj)
        assert result == {"list": [{"key": "expanded"}], "num": 5}


class TestLoadConfig:
    def test_load_valid_yaml(self, monkeypatch, sample_config):
        # Write a minimal valid config to a temp file (no env vars needed)
        config_data = {
            "server": {
                "host": "0.0.0.0",
                "port": 8100,
                "api_keys": [
                    {"key": "test", "name": "default", "allowed_models": ["*"]}
                ],
            },
            "models": {
                "m1": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "fake",
                    "base_url": "https://api.openai.com/v1",
                }
            },
            "routing": {"default_model": "m1"},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            f.flush()
            config = load_config(f.name)

        assert config["server"]["port"] == 8100
        assert "m1" in config["models"]
        os.unlink(f.name)

    def test_env_var_expansion_in_file(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "sk-test-123")
        config_data = {
            "server": {
                "api_keys": [
                    {"key": "k", "name": "d", "allowed_models": ["*"]}
                ]
            },
            "models": {
                "m1": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "${MY_API_KEY}",
                }
            },
            "routing": {"default_model": "m1"},
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            f.flush()
            config = load_config(f.name)

        assert config["models"]["m1"]["api_key"] == "sk-test-123"
        os.unlink(f.name)

    def test_invalid_yaml_raises(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("not: valid: yaml: [")
            f.flush()
            with pytest.raises(yaml.YAMLError):
                load_config(f.name)
        os.unlink(f.name)

    def test_empty_file_raises(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            f.flush()
            with pytest.raises(ValueError, match="Invalid config"):
                load_config(f.name)
        os.unlink(f.name)


class TestValidateConfig:
    def test_missing_server(self):
        with pytest.raises(ValueError, match="server"):
            validate_config(
                {"models": {"m": {"provider": "openai"}}, "routing": {"default_model": "m"}}
            )

    def test_missing_api_keys(self):
        with pytest.raises(ValueError, match="api_keys"):
            validate_config(
                {
                    "server": {"api_keys": []},
                    "models": {"m": {"provider": "openai"}},
                    "routing": {"default_model": "m"},
                }
            )

    def test_missing_models(self):
        with pytest.raises(ValueError, match="models"):
            validate_config(
                {
                    "server": {"api_keys": [{"key": "k", "name": "n"}]},
                    "routing": {"default_model": "m"},
                }
            )

    def test_missing_routing(self):
        with pytest.raises(ValueError, match="routing"):
            validate_config(
                {
                    "server": {"api_keys": [{"key": "k", "name": "n"}]},
                    "models": {"m": {"provider": "openai"}},
                }
            )

    def test_default_model_not_in_models(self):
        with pytest.raises(ValueError, match="not found in models"):
            validate_config(
                {
                    "server": {"api_keys": [{"key": "k", "name": "n"}]},
                    "models": {"m": {"provider": "openai"}},
                    "routing": {"default_model": "nonexistent"},
                }
            )

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="invalid provider"):
            validate_config(
                {
                    "server": {"api_keys": [{"key": "k", "name": "n"}]},
                    "models": {"m": {"provider": "magic"}},
                    "routing": {"default_model": "m"},
                }
            )

    def test_valid_config_passes(self, sample_config):
        validate_config(sample_config)
