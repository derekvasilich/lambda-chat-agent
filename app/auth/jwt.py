import time
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from jose.backends import RSAKey
import httpx
from pydantic import BaseModel
from app.config import settings
import structlog

logger = structlog.get_logger()

bearer_scheme = HTTPBearer(auto_error=True)

_jwks_cache: dict = {}
_jwks_fetched_at: float = 0
_JWKS_TTL = 3600


class UserClaims(BaseModel):
    sub: str
    email: Optional[str] = None
    username: Optional[str] = None


async def _fetch_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.OAUTH2_JWKS_URL, timeout=10)
        resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_fetched_at = now
    return _jwks_cache


def _credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthorized", "message": detail, "details": {}}},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserClaims:
    token = credentials.credentials

    if not settings.OAUTH2_JWKS_URL:
        # Dev/test mode: accept any well-formed JWT without verification
        try:
            payload = jwt.decode(token, key="", options={"verify_signature": False})
            sub = payload.get("sub")
            if not sub:
                raise _credentials_exception("Token missing 'sub' claim")
            return UserClaims(sub=sub, email=payload.get("email"), username=payload.get("cognito:username"))
        except JWTError as e:
            raise _credentials_exception(str(e))

    try:
        jwks = await _fetch_jwks()
    except Exception as e:
        logger.error("jwks_fetch_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={
            "error": {"code": "auth_service_unavailable", "message": "Authentication service unreachable", "details": {}}
        })

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
        if not key:
            raise _credentials_exception("No matching signing key found")

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.OAUTH2_AUDIENCE or None,
            options={"verify_aud": bool(settings.OAUTH2_AUDIENCE)},
        )
    except ExpiredSignatureError:
        raise _credentials_exception("Token has expired")
    except JWTError as e:
        raise _credentials_exception(f"Invalid token: {e}")

    sub = payload.get("sub")
    if not sub:
        raise _credentials_exception("Token missing 'sub' claim")

    return UserClaims(sub=sub, email=payload.get("email"), username=payload.get("cognito:username"))
