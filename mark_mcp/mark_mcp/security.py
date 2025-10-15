"""Authentication helpers for the MCP server."""

from __future__ import annotations

import os
from typing import List

import httpx
from cachetools import TTLCache
from fastapi import Header, HTTPException, Request, status
from jose import jwt

from .config import settings


_JWKS_CACHE: TTLCache[str, dict] = TTLCache(maxsize=4, ttl=300)


def required_scopes() -> List[str]:
    """Return the list of scopes required for write operations."""

    raw = os.getenv("REQUIRED_MCP_SCOPES", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def scopes_enforced() -> bool:
    """Determine whether scope checking is enabled."""

    return bool(required_scopes())


def has_required_scopes(token_scopes: List[str]) -> bool:
    """Check that the presented scopes satisfy the requirement."""

    if not scopes_enforced():
        return True
    required = set(required_scopes())
    return bool(required.intersection(token_scopes))


def _auth_error(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={
            "WWW-Authenticate": 'Bearer authorization_uri="/.well-known/oauth-protected-resource"'
        },
    )


async def _get_jwks(issuer: str) -> dict:
    if issuer in _JWKS_CACHE:
        return _JWKS_CACHE[issuer]
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        jwks_uri = response.json().get("jwks_uri")
        if not jwks_uri:
            _auth_error("OIDC config missing jwks_uri")
        jwks_response = await client.get(jwks_uri)
        jwks_response.raise_for_status()
        jwks = jwks_response.json()
        _JWKS_CACHE[issuer] = jwks
        return jwks


async def require_auth(
    authorization: str | None = Header(default=None),
    request: Request | None = None,
) -> None:
    """Validate bearer tokens from the Authorization header or cookie."""

    header_token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        header_token = authorization.split(" ", 1)[1]

    cookie_token = request.cookies.get("mcp_access") if request is not None else None
    token = header_token or cookie_token

    resource = (settings.oauth_resource or "https://<DOMAIN>/mcp").rstrip("/")

    if settings.oauth_enabled and settings.oauth_issuer and settings.oauth_resource:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={
                    "WWW-Authenticate": (
                        f'Bearer authorization_uri="/.well-known/oauth-protected-resource", resource="{resource}"'
                    )
                },
            )

        jwks = await _get_jwks(settings.oauth_issuer)
        try:
            unverified = jwt.get_unverified_header(token)
            kid = unverified.get("kid")
            keys = jwks.get("keys", [])
            key = next((k for k in keys if k.get("kid") == kid), None) if kid else (keys[0] if keys else None)
            if not key:
                _auth_error("JWKS key not found")
            claims = jwt.decode(
                token,
                key,
                algorithms=[key.get("alg", "RS256")],
                options={"verify_aud": False, "verify_at_hash": False, "verify_sub": False},
                issuer=settings.oauth_issuer,
            )

            scopes = (claims.get("scope") or "").split()
            if not has_required_scopes(scopes):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient scopes. Required: {', '.join(required_scopes())}",
                )

            if request is not None:
                request.state.oauth_scopes = scopes
            return
        except HTTPException:
            raise
        except Exception:
            _auth_error("Invalid token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={
                "WWW-Authenticate": (
                    f'Bearer authorization_uri="/.well-known/oauth-protected-resource", resource="{resource}"'
                )
            },
        )
    if token != settings.bearer_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    if request is not None:
        request.state.oauth_scopes = []


def require_scope_write(request: Request) -> None:
    if settings.oauth_enabled:
        scopes = getattr(request.state, "oauth_scopes", [])
        if "mcp.write" not in scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing scope mcp.write")
