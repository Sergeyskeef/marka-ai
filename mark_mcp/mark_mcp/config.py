"""Configuration helpers for the MCP server."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Lightweight settings object backed by environment variables."""

    app_name: str = Field(default="mark-mcp")
    bearer_token: str = Field(default_factory=lambda: os.getenv("MCP_TOKEN", "change-me"))
    graphiti_url: str = Field(
        default_factory=lambda: os.getenv("GRAPHITI_URL", "http://graphiti:7878").rstrip("/")
    )
    allow_paths: List[str] = Field(
        default_factory=lambda: [
            p for p in os.getenv("ALLOW_PATHS", "/srv/mark,/var/log/mark,/data/mark").split(",") if p
        ]
    )
    log_file: str = Field(default_factory=lambda: os.getenv("LOG_FILE", "/var/log/mark/mark-mcp.log"))
    max_read_bytes: int = Field(default_factory=lambda: int(os.getenv("MCP_MAX_READ_BYTES", "1048576")))
    max_glob_items: int = Field(default_factory=lambda: int(os.getenv("MCP_MAX_GLOB_ITEMS", "500")))
    request_timeout_s: int = Field(default_factory=lambda: int(os.getenv("MCP_REQUEST_TIMEOUT", "20")))
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8788")))
    env: str = Field(default_factory=lambda: os.getenv("ENV", "dev"))
    dry_run_default: bool = Field(default_factory=lambda: os.getenv("DRY_RUN_DEFAULT", "true").lower() == "true")

    # OAuth related settings
    oauth_enabled: bool = Field(default_factory=lambda: os.getenv("OAUTH_ENABLED", "false").lower() == "true")
    oauth_issuer: str | None = Field(default_factory=lambda: os.getenv("OAUTH_ISSUER"))
    oauth_resource: str | None = Field(default_factory=lambda: os.getenv("OAUTH_RESOURCE"))


@lru_cache(1)
def get_settings() -> Settings:
    """Provide a cached settings instance to simplify testing."""

    return Settings()


settings = get_settings()
