"""
Google OAuth 2.0 + JWT utilities for P7.
"""
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import Request, HTTPException
from jose import jwt, JWTError
from sqlalchemy.orm import Session

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
SECRET_KEY    = os.getenv("SECRET_KEY", "dev-secret-change-this-in-production")
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")
REDIRECT_URI  = f"{FRONTEND_URL}/auth/google/callback"

ALGORITHM         = "HS256"
TOKEN_EXPIRE_DAYS = 7
COOKIE_NAME       = "tm_session"


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_google_auth_url(state: str) -> str:
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
    }
    return GOOGLE_AUTH_URL + "?" + urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens."""
    resp = httpx.post(GOOGLE_TOKEN_URL, data={
        "code":          code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_google_user(access_token: str) -> dict:
    """Fetch user profile from Google."""
    resp = httpx.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_jwt(token: str) -> str:
    """Return user_id or raise HTTPException."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_current_user(request: Request, db: Session):
    """Dependency: return User from JWT cookie or raise 401."""
    from models import User
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = verify_jwt(token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(request: Request, db: Session):
    """Dependency: return User or None (no error if not logged in)."""
    from models import User
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        user_id = verify_jwt(token)
        return db.query(User).filter(User.id == user_id).first()
    except HTTPException:
        return None


def set_auth_cookie(response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,       # set True in production with HTTPS
        max_age=60 * 60 * 24 * TOKEN_EXPIRE_DAYS,
        path="/",
    )


def clear_auth_cookie(response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
