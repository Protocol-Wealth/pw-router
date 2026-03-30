# Deployment Guide

pw-router is a stateless Python/FastAPI service. It runs anywhere you can run a Docker container or a Python process.

## Requirements

- Python 3.12+
- ~50MB RAM at idle (no ML models loaded — this is a thin proxy)
- Network access to your configured LLM provider endpoints

## Local / Development

```bash
# Install
pip install -e ".[dev]"

# Configure
cp config.example.yaml config.yaml
cp .env.example .env
# Edit both files with your API keys

# Run
source .env  # or use direnv, dotenv, etc.
pw-router --config config.yaml
```

The server starts on `http://localhost:8100` by default.

## Docker

### Build

```bash
docker build -t pw-router .
```

### Run

```bash
docker run -p 8100:8100 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e PW_ROUTER_API_KEY_1=your-key \
  -v $(pwd)/config.yaml:/app/config.yaml \
  pw-router
```

Or use an env file:

```bash
docker run -p 8100:8100 \
  --env-file .env \
  -v $(pwd)/config.yaml:/app/config.yaml \
  pw-router
```

### Dockerfile

The included `Dockerfile` is production-ready:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY pw_router/ pw_router/
COPY plugins/ plugins/
EXPOSE 8100
CMD ["uvicorn", "pw_router.server:app", "--host", "0.0.0.0", "--port", "8100"]
```

512MB RAM is more than sufficient.

## Fly.io

### Setup

```bash
# Copy the example config
cp fly.toml.example fly.toml

# Edit fly.toml — set your app name and region
# Then launch
fly launch

# Set secrets (env vars for config.yaml expansion)
fly secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  OPENAI_API_KEY=sk-... \
  RUNPOD_API_KEY=... \
  PW_ROUTER_API_KEY_1=your-key
```

### Deploy

```bash
fly deploy
```

### fly.toml.example

```toml
app = "your-pw-router"
primary_region = "ewr"

[build]

[http_service]
  internal_port = 8100
  force_https = true
  auto_stop_machines = "suspend"
  auto_start_machines = true
  min_machines_running = 0

[vm]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1

[checks]
  [checks.health]
    port = 8100
    type = "http"
    interval = "30s"
    timeout = "5s"
    path = "/health"
```

### Tips

- `auto_stop_machines = "suspend"` saves cost when idle — machines resume in ~1s on first request
- `min_machines_running = 0` means zero cost when no requests are flowing
- Health checks use the `/health` endpoint which reports per-model circuit breaker status
- Set `min_machines_running = 1` for production workloads where cold start latency matters

## Railway / Render / Other Platforms

pw-router is a standard Python web service. Any platform that supports Docker or `uvicorn` works:

```bash
# Start command for most platforms
uvicorn pw_router.server:app --host 0.0.0.0 --port $PORT
```

Set `CONFIG_PATH` as an env var to point to your config file, or mount it at the default path (`config.yaml` in the working directory).

## Health Checks

The `/health` endpoint returns:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "models": {
    "claude-sonnet": {"status": "healthy", "circuit": "closed"},
    "local-llama": {"status": "unhealthy", "circuit": "open"}
  }
}
```

Point your platform's health check at `GET /health`. The endpoint does not require authentication.

## Configuration at Runtime

pw-router reads config once at startup. To change config:

1. Update `config.yaml` (or env vars)
2. Restart the service

There is no hot-reload. This is intentional — config changes in a regulated environment should be deliberate and auditable.
