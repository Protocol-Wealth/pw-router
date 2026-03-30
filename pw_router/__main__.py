# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""CLI entry point: python -m pw_router"""

import argparse
import logging
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="pw-router: minimal LLM gateway")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8100, help="Port to bind")
    args = parser.parse_args()

    if args.config:
        os.environ["CONFIG_PATH"] = args.config

    # Configure pw_router loggers to emit to stderr (picked up by Fly.io)
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler()],
    )

    uvicorn.run(
        "pw_router.server:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
