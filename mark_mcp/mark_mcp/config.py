"""Configuration helpers for the MCP server."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Tuple

from pydantic import BaseModel, Field


def _split_env(name: str, default: str) -> Tuple[str, ...]:
    """Split comma separated environment variables while ignoring empties."""

    raw = os.getenv(name, default)
    parts = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    return tuple(parts)


class Settings(BaseModel):
    """Lightweight settings object backed by environment variables."""

    app_name: str = Field(default="mark-mcp")
    bearer_token: str = Field(default_factory=lambda: os.getenv("MCP_TOKEN", "change-me"))
    graphiti_url: str = Field(
        default_factory=lambda: os.getenv("GRAPHITI_URL", "http://graphiti:7878").rstrip("/")
    )
    allow_paths: Tuple[str, ...] = Field(
        default_factory=lambda: _split_env(
            "ALLOW_PATHS", "/srv/mark,/var/log/mark,/data/mark"
        )
    )
    log_file: str = Field(default_factory=lambda: os.getenv("LOG_FILE", "/var/log/mark/mark-mcp.log"))
    max_read_bytes: int = Field(
        default_factory=lambda: int(os.getenv("MCP_MAX_READ_BYTES", "1048576"))
    )
    max_glob_items: int = Field(
        default_factory=lambda: int(os.getenv("MCP_MAX_GLOB_ITEMS", "500"))
    )
    request_timeout_s: int = Field(
        default_factory=lambda: int(os.getenv("MCP_REQUEST_TIMEOUT", "20"))
    )
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8788")))
    env: str = Field(default_factory=lambda: os.getenv("ENV", "dev"))
    dry_run_default: bool = Field(
        default_factory=lambda: os.getenv("DRY_RUN_DEFAULT", "true").lower() == "true"
    )

    # OAuth related settings
    oauth_enabled: bool = Field(
        default_factory=lambda: os.getenv("OAUTH_ENABLED", "false").lower() == "true"
    )
    oauth_issuer: str | None = Field(default_factory=lambda: os.getenv("OAUTH_ISSUER"))
    oauth_resource: str | None = Field(default_factory=lambda: os.getenv("OAUTH_RESOURCE"))

    # Optional write approval workflow knobs
    require_write_approval: bool = Field(
        default_factory=lambda: os.getenv("MCP_REQUIRE_WRITE_APPROVAL", "true").lower()
        == "true"
    )
    write_preview_bytes: int = Field(
        default_factory=lambda: int(os.getenv("MCP_WRITE_PREVIEW_BYTES", "200"))
    )

    # Optional audit / oidc integration values for backwards compatibility
    audit_log_file: str = Field(
        default_factory=lambda: os.getenv("MCP_AUDIT_LOG_FILE", "/var/log/mark/mcp-audit.log")
    )
    oidc_client_id: str = Field(default_factory=lambda: os.getenv("OIDC_CLIENT_ID", "mark-mcp"))
    oidc_client_secret: str | None = Field(default_factory=lambda: os.getenv("OIDC_CLIENT_SECRET"))
    oidc_redirect_uri: str | None = Field(default_factory=lambda: os.getenv("OIDC_REDIRECT_URI"))

    def allow_path_list(self) -> List[str]:
        """Return allow-list as a list for legacy callers expecting mutability."""

        return list(self.allow_paths)


@lru_cache(1)
def get_settings() -> Settings:
    """Provide a cached settings instance to simplify testing."""

    return Settings()


settings = get_settings()
