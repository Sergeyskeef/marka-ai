from fastapi import Header, HTTPException, status, Request
from .config import settings
from jose import jwt
import httpx
from cachetools import TTLCache
import os

_jwks_cache: TTLCache[str, dict] = TTLCache(maxsize=4, ttl=300)

# Строгие скоупы для MCP инструментов
def required_scopes():
	"""Получает список требуемых скоупов из переменной окружения"""
	raw = os.getenv("REQUIRED_MCP_SCOPES", "")
	return [s.strip() for s in raw.split(",") if s.strip()]

def scopes_enforced() -> bool:
	"""Проверяет, включена ли проверка скоупов"""
	return len(required_scopes()) > 0

def has_required_scopes(token_scopes: list[str]) -> bool:
	"""Проверяет наличие необходимых скоупов"""
	if not scopes_enforced():
		return True  # Если проверка отключена, всегда разрешаем
	required = set(required_scopes())
	return bool(required.intersection(token_scopes))


def _auth_error(detail: str):
	raise HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail=detail,
		headers={
			"WWW-Authenticate": 'Bearer authorization_uri="/.well-known/oauth-protected-resource"'
		}
	)


async def _get_jwks(issuer: str) -> dict:
	if issuer in _jwks_cache:
		return _jwks_cache[issuer]
	async with httpx.AsyncClient(timeout=10.0) as client:
		r = await client.get(f"{issuer}/.well-known/openid-configuration")
		r.raise_for_status()
		jwks_uri = r.json().get("jwks_uri")
		if not jwks_uri:
			_auth_error("OIDC config missing jwks_uri")
		rk = await client.get(jwks_uri)
		rk.raise_for_status()
		jwks = rk.json()
		_jwks_cache[issuer] = jwks
		return jwks


async def require_auth(authorization: str | None = Header(default=None), request: Request = None) -> None:
        # Если проверка скоупов отключена, пропускаем аутентификацию
        if not scopes_enforced():
                return

        header_token: str | None = None
        if authorization and authorization.startswith("Bearer "):
                header_token = authorization.split(" ", 1)[1]

        cookie_token = request.cookies.get("mcp_access") if request is not None else None
        token = header_token or cookie_token

        # OAuth enabled path
        if settings.oauth_enabled and settings.oauth_issuer and settings.oauth_resource:
                if not token:
                        resource = (settings.oauth_resource or "https://<DOMAIN>/mcp").rstrip("/")
                        raise HTTPException(
                                status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Missing bearer token",
                                headers={
                                        "WWW-Authenticate": f'Bearer authorization_uri="/.well-known/oauth-protected-resource", resource="{resource}"'
                                },
                        )
                jwks = await _get_jwks(settings.oauth_issuer)
                try:
                        # jose requires setting options or audience; we check later for aud/scope
                        unverified = jwt.get_unverified_header(token)
			kid = unverified.get("kid")
			keys = jwks.get("keys", [])
			key = next((k for k in keys if k.get("kid") == kid), None) if kid else (keys[0] if keys else None)
			if not key:
				_auth_error("JWKS key not found")
			claims = jwt.decode(token, key, algorithms=[key.get("alg", "RS256")], options={"verify_aud": False, "verify_at_hash": False, "verify_sub": False}, issuer=settings.oauth_issuer)
			
			# Проверяем наличие необходимых скоупов
			scopes = (claims.get("scope") or "").split()
			has_required = has_required_scopes(scopes)
			
			# Log for debugging
			print(f"Token validation: issuer={settings.oauth_issuer}, scopes={scopes}, has_required_scopes={has_required}")
			
			# Требуем наличие необходимых скоупов
			if not has_required:
				raise HTTPException(
					status_code=status.HTTP_403_FORBIDDEN, 
					detail=f"Insufficient scopes. Required: {', '.join(required_scopes())}"
				)
			
			request.state.oauth_scopes = scopes
			return
		except HTTPException:
			raise
		except Exception:
			_auth_error("Invalid token")
	# Fallback: static token auth
        if not token:
                resource = (settings.oauth_resource or "https://<DOMAIN>/mcp").rstrip("/")
                raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Missing bearer token",
                        headers={
                                "WWW-Authenticate": f'Bearer authorization_uri="/.well-known/oauth-protected-resource", resource="{resource}"'
                        },
                )
        if token != settings.bearer_token:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")


def require_scope_write(request: Request) -> None:
	if settings.oauth_enabled:
		scopes = getattr(request.state, "oauth_scopes", [])
		if "mcp.write" not in scopes:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing scope mcp.write")
