"""Top-level package wrapper to expose the MCP server modules."""

from __future__ import annotations

import sys

from .mark_mcp import (
    agent_tools,
    docker_tools,
    fs_tools,
    logging_config,
    mcp_server,
    memory_tools,
    metrics,
    oidc,
    repo_tools,
    security,
)

_MODULES = {
    "agent_tools": agent_tools,
    "docker_tools": docker_tools,
    "fs_tools": fs_tools,
    "logging_config": logging_config,
    "mcp_server": mcp_server,
    "memory_tools": memory_tools,
    "metrics": metrics,
    "oidc": oidc,
    "repo_tools": repo_tools,
    "security": security,
}

globals().update(_MODULES)
for name, module in _MODULES.items():
    sys.modules[f"{__name__}.{name}"] = module

__all__ = list(_MODULES.keys())
