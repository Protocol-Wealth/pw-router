# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email **engineering@protocolwealthllc.com** with:

1. Description of the vulnerability
2. Steps to reproduce
3. Impact assessment (what an attacker could do)
4. Suggested fix (if you have one)

We will acknowledge receipt within 48 hours and aim to provide a fix or mitigation within 7 days for critical issues.

## Security Model

pw-router is a thin routing proxy. Its security posture:

- **API key auth** with constant-time comparison (`hmac.compare_digest`)
- **Per-key model allowlists** to restrict which models each client can access
- **No data storage** — stateless, no database, no disk writes
- **No request/response body logging** by default
- **10MB request size limit** to prevent abuse
- **No telemetry or external calls** except to configured model providers
- **TLS termination** handled by the deployment platform (Fly.io, etc.)

### What's in scope

- Authentication bypasses
- Authorization issues (accessing models outside allowlist)
- Request/response data leakage
- Dependency vulnerabilities
- Middleware plugin sandbox escapes

### What's out of scope

- Denial of service via high request volume (use a reverse proxy / rate limiter)
- Vulnerabilities in upstream LLM providers
- Issues requiring physical access to the host

## Dependency Policy

pw-router has 4 runtime dependencies, all well-established packages:

- `fastapi` — web framework
- `uvicorn` — ASGI server
- `httpx` — HTTP client
- `pyyaml` — YAML parser

We recommend running `pip-audit` in CI to catch known vulnerabilities in dependencies.
