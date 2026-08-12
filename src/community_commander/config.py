from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

DEFAULT_GRAPH_API_BASE_URL = "https://hackathon-neo4j-2026-ymnmap7mja-uc.a.run.app"
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConfigurationError(RuntimeError):
    """Raised when required server configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    graph_api_token: str
    graph_api_base_url: str = DEFAULT_GRAPH_API_BASE_URL
    graph_api_timeout_seconds: float = 10.0
    log_level: LogLevel = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        token = os.getenv("GRAPH_API_TOKEN", "").strip()
        if not token:
            raise ConfigurationError("GRAPH_API_TOKEN is required")

        base_url = os.getenv("GRAPH_API_BASE_URL", DEFAULT_GRAPH_API_BASE_URL).strip()
        if not base_url.startswith(("http://", "https://")):
            raise ConfigurationError("GRAPH_API_BASE_URL must be an HTTP(S) URL")

        raw_timeout = os.getenv("GRAPH_API_TIMEOUT_SECONDS", "10").strip()
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ConfigurationError("GRAPH_API_TIMEOUT_SECONDS must be a number") from exc
        if timeout <= 0:
            raise ConfigurationError("GRAPH_API_TIMEOUT_SECONDS must be greater than zero")

        raw_log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if raw_log_level not in VALID_LOG_LEVELS:
            raise ConfigurationError(
                "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )

        return cls(
            graph_api_token=token,
            graph_api_base_url=base_url.rstrip("/"),
            graph_api_timeout_seconds=timeout,
            log_level=cast(LogLevel, raw_log_level),
        )
