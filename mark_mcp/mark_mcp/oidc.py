"""OIDC login and callback helpers for the MCP server."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .config import settings


OIDC_ISSUER = os.getenv("OIDC_ISSUER", settings.oauth_issuer or "https://auth.markmind.ru/realms/marka")
CLIENT_ID = settings.oidc_client_id
CLIENT_SECRET = settings.oidc_client_secret or ""
REDIRECT_URI = settings.oidc_redirect_uri or "https://mcp.markmind.ru/mcp/callback"

AUTH_URL = f"{OIDC_ISSUER}/protocol/openid-connect/auth"
TOKEN_URL = f"{OIDC_ISSUER}/protocol/openid-connect/token"

router = APIRouter()


def _pkce_pair() -> tuple[str, str]:
    verifier_bytes = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Start the OAuth authorization code + PKCE flow."""

    verifier, challenge = _pkce_pair()
    request.session["pkce_verifier"] = verifier
    state = secrets.token_urlsafe(16)
    request.session["state"] = state

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    return RedirectResponse(url=f"{AUTH_URL}?{urlencode(params)}", status_code=302)


@router.get("/callback")
async def callback(request: Request):
    """Exchange the authorization code for an access token."""

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state or state != request.session.get("state"):
        raise HTTPException(status_code=400, detail="Invalid state or code")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": request.session.get("pkce_verifier"),
    }
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET

    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_URL, data=data, timeout=15)

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="No access_token")

    resp = HTMLResponse("<h3>Connected successfully. You can close this tab.</h3>", status_code=200)
    resp.set_cookie(
        "mcp_access",
        access_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=3600,
    )
    return resp

