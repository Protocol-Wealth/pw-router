# Changelog

All notable changes to pw-router will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-30

### Added

- OpenAI-compatible `/v1/chat/completions` endpoint (streaming and non-streaming)
- `/v1/models` endpoint with per-client model filtering
- `/health` endpoint with per-model circuit breaker status
- Provider adapters: OpenAI, Anthropic (with format translation), vLLM/RunPod
- Circuit breaker per model (CLOSED / OPEN / HALF_OPEN states)
- Fallback chains — automatic failover when a provider is unhealthy
- Tag-based routing rules (e.g., PII-flagged requests to self-hosted models)
- Pluggable middleware system with pre-request and post-response hooks
- YAML configuration with `${ENV_VAR}` expansion
- API key authentication with per-key model allowlists and constant-time comparison
- Background health check loop for all configured model endpoints
- Example plugins: PII redaction scanner, structured audit logger
- CLI entry point: `pw-router --config config.yaml`
- Full test suite with mocked HTTP via respx

[0.1.0]: https://github.com/Protocol-Wealth/pw-router/releases/tag/v0.1.0
