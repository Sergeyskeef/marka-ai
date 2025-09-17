from fastapi import Header, HTTPException, status
from .config import settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
	if not authorization or not authorization.startswith("Bearer "):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
	token = authorization.split(" ", 1)[1]
	if token != settings.bearer_token:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
