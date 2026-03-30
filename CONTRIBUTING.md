# Contributing to pw-router

Thanks for your interest in contributing. pw-router is deliberately minimal, and we'd like to keep it that way. This guide covers development setup, code standards, and what makes a good contribution.

## Development Setup

```bash
# Clone
git clone https://github.com/Protocol-Wealth/pw-router.git
cd pw-router

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check pw_router/ tests/ plugins/

# Run formatter
ruff format pw_router/ tests/ plugins/
```

## Running Locally

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your API keys

pw-router --config config.yaml
```

## Code Standards

- **Python 3.12+** — use modern syntax (type unions with `|`, etc.)
- **Ruff** for linting and formatting — config in `pyproject.toml`
- **Type hints** on all function signatures
- **No new dependencies** without discussion in an issue first
- **MIT license header** on every `.py` file:

```python
# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router
```

## Testing

- All tests use `pytest` with `pytest-asyncio`
- HTTP calls are mocked with `respx` — no real API calls in tests
- Run the full suite before submitting a PR: `pytest -v`
- Aim for coverage on new code: `pytest --cov=pw_router`

## What Makes a Good Contribution

### Yes, please

- Bug fixes with a test that reproduces the issue
- New provider adapters (OpenAI-compatible providers are ~30 lines)
- Performance improvements that don't add complexity
- Documentation improvements
- Security fixes (see [SECURITY.md](SECURITY.md) for reporting)

### Probably a plugin

If your feature is opinionated about any of these, it belongs in a middleware plugin, not core:

- Compliance rules or PII handling
- Authentication beyond API keys (OAuth, JWT, etc.)
- Logging destinations (database, file, external service)
- Data classification or routing policies
- Rate limiting strategies

### Probably not

- Features that add a new dependency
- Anything that pushes core past ~1,500 lines
- UI, dashboard, or web interface
- Vendor-specific integrations in core (write a plugin)

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Write tests for your changes
3. Run `ruff check` and `pytest` — both must pass
4. Keep PRs focused — one feature or fix per PR
5. Write a clear description of what and why

## Commit Messages

Use conventional commits:

```
feat(providers): add Google Vertex adapter
fix(router): circuit breaker not resetting after cooldown
docs: add Kubernetes deployment guide
test(middleware): cover plugin loading error paths
```

## Questions?

Open a [discussion](https://github.com/Protocol-Wealth/pw-router/discussions) or [issue](https://github.com/Protocol-Wealth/pw-router/issues).
