# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for API endpoints with mocked providers."""

import httpx
from starlette.testclient import TestClient

from pw_router.server import create_app
from tests.conftest import OPENAI_CHAT_RESPONSE


def _make_client(sample_config, respx_mock):
    """Create TestClient with respx active (ensures httpx is mocked during lifespan)."""
    app = create_app(config=sample_config)
    return TestClient(app)


class TestAuth:
    def test_valid_api_key(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 200

    def test_missing_auth_header(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "test-model", "messages": []},
            )
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]

    def test_invalid_api_key(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={"model": "test-model", "messages": []},
                headers={"Authorization": "Bearer wrong-key"},
            )
        assert response.status_code == 401

    def test_restricted_model_access(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            # test-key-2 only allows local-* models
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-2"},
            )
        assert response.status_code == 403

    def test_wildcard_allows_all(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 200


class TestChatCompletions:
    def test_non_streaming(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        data = response.json()
        assert response.status_code == 200
        assert data["model"] == "test-model"
        assert data["choices"][0]["message"]["content"] == "Hello from the test!"

    def test_streaming(self, sample_config, respx_mock):
        sse_content = (
            b'data: {"id":"chatcmpl-s","object":"chat.completion.chunk",'
            b'"choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}\n\n'
            b"data: [DONE]\n\n"
        )
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=sse_content,
                headers={"content-type": "text/event-stream"},
            )
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 200
        assert "data:" in response.text

    def test_nonexistent_model(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "nonexistent",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 404

    def test_provider_error_returns_502(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "Internal"})
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 502

    def test_default_model_when_none_specified(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 200
        assert response.json()["model"] == "test-model"


class TestModelsEndpoint:
    def test_list_models_wildcard(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get(
                "/v1/models",
                headers={"Authorization": "Bearer test-key-1"},
            )
        data = response.json()
        assert data["object"] == "list"
        model_ids = {m["id"] for m in data["data"]}
        assert "test-model" in model_ids
        assert "local-model" in model_ids

    def test_list_models_restricted(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get(
                "/v1/models",
                headers={"Authorization": "Bearer test-key-2"},
            )
        data = response.json()
        model_ids = {m["id"] for m in data["data"]}
        assert "local-model" in model_ids
        assert "test-model" not in model_ids

    def test_list_models_no_auth(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/v1/models")
        assert response.status_code == 401


class TestRequestSanitization:
    def test_unknown_fields_stripped(self, sample_config, respx_mock):
        """Ensure arbitrary fields like 'n' and 'user' are stripped before forwarding."""
        captured = {}

        def capture_request(request):
            captured["body"] = request.content
            return httpx.Response(200, json=OPENAI_CHAT_RESPONSE)

        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=capture_request
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "n": 100,
                    "user": "impersonated",
                    "logit_bias": {"50256": -100},
                    "temperature": 0.5,
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.status_code == 200
        import json

        sent_body = json.loads(captured["body"])
        # Temperature is allowed, n/user/logit_bias are stripped
        assert "temperature" in sent_body
        assert "n" not in sent_body
        assert "user" not in sent_body
        assert "logit_bias" not in sent_body

    def test_invalid_json_returns_400(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                content=b"not json",
                headers={
                    "Authorization": "Bearer test-key-1",
                    "Content-Type": "application/json",
                },
            )
        assert response.status_code == 400


class TestSecurityHeaders:
    def test_api_responses_have_security_headers(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_api_responses_have_no_store(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        with TestClient(create_app(config=sample_config)) as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
        assert response.headers.get("Cache-Control") == "no-store"


class TestMetricsEndpoint:
    def test_metrics_requires_auth(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/metrics")
        assert response.status_code == 401

    def test_metrics_returns_usage(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        with TestClient(create_app(config=sample_config)) as client:
            # Make a request to generate usage data
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": "Bearer test-key-1"},
            )
            # Check metrics
            response = client.get(
                "/metrics",
                headers={"Authorization": "Bearer test-key-1"},
            )
        data = response.json()
        assert response.status_code == 200
        assert data["totals"]["requests"] == 1
        assert "uptime_seconds" in data
        assert "test-client" in data["by_client"]
        assert "test-model" in data["by_client"]["test-client"]
        model_usage = data["by_client"]["test-client"]["test-model"]
        assert model_usage["prompt_tokens"] == 10
        assert model_usage["completion_tokens"] == 5


class TestRateLimiting:
    def test_rate_limit_returns_429(self, sample_config, respx_mock):
        respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=OPENAI_CHAT_RESPONSE)
        )
        # Set very low rate limit
        sample_config["rate_limit"] = {"max_requests": 2, "window_seconds": 60}
        with TestClient(create_app(config=sample_config)) as client:
            for _ in range(2):
                response = client.post(
                    "/v1/chat/completions",
                    json={"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"Authorization": "Bearer test-key-1"},
                )
                assert response.status_code == 200
            # Third request should be rate limited
            response = client.post(
                "/v1/chat/completions",
                json={"model": "test-model", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": "Bearer test-key-1"},
            )
            assert response.status_code == 429


class TestRequestId:
    def test_response_has_request_id(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/health")
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 16

    def test_client_request_id_propagated(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/health", headers={"X-Request-Id": "my-custom-id-123"})
        assert response.headers["x-request-id"] == "my-custom-id-123"


class TestHealthEndpoint:
    def test_health_returns_status(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "models" in data
        assert "test-model" in data["models"]
        assert data["models"]["test-model"]["circuit"] == "closed"

    def test_health_no_auth_required(self, sample_config, respx_mock):
        with TestClient(create_app(config=sample_config)) as client:
            response = client.get("/health")
        assert response.status_code == 200
