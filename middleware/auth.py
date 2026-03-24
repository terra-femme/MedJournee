# middleware/auth.py
"""
JWT authentication dependency for FastAPI routes.

Usage
-----
    from fastapi import Depends
    from middleware.auth import require_auth

    @router.get("/protected")
    async def handler(user: dict = Depends(require_auth)):
        user_id = user["sub"]   # Supabase user UUID

Public endpoints (health checks, static pages) should NOT use this dependency.
All data-access endpoints MUST use it.

Environment variable required
------------------------------
    SUPABASE_JWT_SECRET  — found in Supabase Dashboard → Settings → API → JWT Secret
"""

import os

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()


def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """
    Validate a Supabase-issued JWT Bearer token.

    Returns the decoded JWT payload dict on success.
    Raises HTTP 401 on expired / invalid tokens.
    Raises HTTP 500 if SUPABASE_JWT_SECRET is not configured.
    """
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="Server authentication is not configured. Set SUPABASE_JWT_SECRET.",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def verify_ws_token(token: str) -> dict:
    """
    Validate a JWT passed as a query parameter on WebSocket connections.

    Browsers cannot send custom headers during the WebSocket handshake, so
    the token must be passed as ?token=<jwt>.

    Returns the decoded payload dict on success.
    Raises HTTPException 1008 (Policy Violation) on failure so the WebSocket
    can be closed cleanly.
    """
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Auth not configured.")

    if not token:
        raise HTTPException(status_code=1008, detail="Missing token.")

    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=1008, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=1008, detail="Invalid token.")
