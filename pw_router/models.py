# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Shared data models and exceptions."""


class ModelNotFoundError(Exception):
    """Requested model does not exist in config."""

    def __init__(self, model: str):
        self.model = model
        super().__init__(f"Model '{model}' not found")


class ModelNotAllowedError(Exception):
    """Client is not allowed to use the requested model."""

    def __init__(self, model: str):
        self.model = model
        super().__init__(f"Model '{model}' not allowed for this API key")


class AllModelsUnavailableError(Exception):
    """All models in the fallback chain are unhealthy."""

    def __init__(self):
        super().__init__("All models unavailable")
