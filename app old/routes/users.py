"""
users.py — auth routes

Features:
  - Register (email + password)
  - Login by email OR username
  - TOTP 2FA setup + verify + disable
  - Forgot password / reset password (Gmail SMTP)
  - GET /me
  - PUT /me  (update profile, avatar, preferences, password)
"""

import io
import os
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional

import pyotp
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import hash_password, verify_password, create_access_token
from app.security import get_current_user
from app.services.email_service import send_password_reset

router = APIRouter(prefix="/users", tags=["users"])

RESET_TOKEN_EXPIRY_HOURS = 1


# ── Pydantic models ──────────────────────────────────────────────────────────

class RegisterPayload(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None
    avatar: Optional[str] = None
    user_type: Optional[str] = None
    level: Optional[str] = None
    markets: Optional[list] = None


class LoginPayload(BaseModel):
    identifier: str   # email OR username
    password: str


class LoginStep2Payload(BaseModel):
    """Second step when 2FA is enabled."""
    temp_token: str
    totp_code: str


class ForgotPasswordPayload(BaseModel):
    email: EmailStr


class ResetPasswordPayload(BaseModel):
    token: str
    new_password: str


class TOTPVerifyPayload(BaseModel):
    code: str


class TOTPDisablePayload(BaseModel):
    code: str


class UpdateProfilePayload(BaseModel):
    username:         Optional[str] = None
    avatar:           Optional[str] = None
    user_type:        Optional[str] = None
    level:            Optional[str] = None
    markets:          Optional[str] = None   # JSON string e.g. '["US","UK"]'
    current_password: Optional[str] = None
    new_password:     Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_dict(user: User) -> dict:
    try:
        markets = json.loads(user.markets) if user.markets else []
    except Exception:
        markets = []
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "avatar": user.avatar or "👤",
        "user_type": user.user_type,
        "level": user.level,
        "markets": markets,
        "totp_enabled": bool(user.totp_enabled),
        "created_at": str(user.created_at) if user.created_at else None,
    }


def _lookup_user(identifier: str, db: Session) -> Optional[User]:
    """Find user by email or username."""
    user = db.query(User).filter(User.email == identifier.lower().strip()).first()
    if user:
        return user
    return db.query(User).filter(User.username == identifier.strip()).first()


# ── Register ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(payload: RegisterPayload, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")

    if payload.username:
        clash = db.query(User).filter(User.username == payload.username).first()
        if clash:
            raise HTTPException(400, "Username already taken")

    if len(payload.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        username=payload.username,
        avatar=payload.avatar or "👤",
        user_type=payload.user_type,
        level=payload.level,
        markets=json.dumps(payload.markets or []),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}


# ── Login (step 1) ────────────────────────────────────────────────────────────

@router.post("/login")
def login(payload: LoginPayload, db: Session = Depends(get_db)):
    user = _lookup_user(payload.identifier, db)

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.totp_enabled:
        temp_token = create_access_token(
            {"sub": str(user.id), "2fa_pending": True},
            expires_delta=timedelta(minutes=5)
        )
        return {"requires_2fa": True, "temp_token": temp_token}

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}


# ── Login (step 2 — 2FA) ──────────────────────────────────────────────────────

@router.post("/login/2fa")
def login_2fa(payload: LoginStep2Payload, db: Session = Depends(get_db)):
    from jose import jwt, JWTError
    from app.auth import SECRET_KEY, ALGORITHM

    try:
        data = jwt.decode(payload.temp_token, SECRET_KEY, algorithms=[ALGORITHM])
        if not data.get("2fa_pending"):
            raise HTTPException(400, "Invalid token type")
        user_id = int(data["sub"])
    except JWTError:
        raise HTTPException(401, "Temp token invalid or expired")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.totp_secret:
        raise HTTPException(401, "User not found")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.totp_code, valid_window=1):
        raise HTTPException(401, "Invalid 2FA code")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": _user_dict(user)}


# ── Me (GET) ──────────────────────────────────────────────────────────────────

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_dict(user)


# ── Me (PUT) — update profile / preferences / password ───────────────────────

@router.put("/me")
def update_me(
    payload: UpdateProfilePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Re-fetch within this session to avoid detached-instance errors
    user = db.query(User).filter(User.id == current_user.id).first()

    if payload.username is not None:
        # Check uniqueness (ignore self)
        clash = db.query(User).filter(
            User.username == payload.username,
            User.id != user.id
        ).first()
        if clash:
            raise HTTPException(400, "Username already taken")
        user.username = payload.username

    if payload.avatar    is not None: user.avatar    = payload.avatar
    if payload.user_type is not None: user.user_type = payload.user_type
    if payload.level     is not None: user.level     = payload.level
    if payload.markets   is not None: user.markets   = payload.markets  # stored as JSON string

    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(400, "current_password is required to set a new password")
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(400, "Current password is incorrect")
        if len(payload.new_password) < 8:
            raise HTTPException(400, "New password must be at least 8 characters")
        user.hashed_password = hash_password(payload.new_password)

    db.commit()
    db.refresh(user)
    return _user_dict(user)


# ── 2FA Setup ─────────────────────────────────────────────────────────────────

@router.post("/me/2fa/setup")
def setup_2fa(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.totp_enabled:
        raise HTTPException(400, "2FA is already enabled")

    secret = pyotp.random_base32()
    user.totp_secret = secret
    db.commit()

    totp = pyotp.TOTP(secret)
    label = f"FlyingFunds:{user.email}"
    uri = totp.provisioning_uri(name=label, issuer_name="FlyingFunds")

    return {
        "secret": secret,
        "uri": uri,
        "qr_url": f"/users/me/2fa/qr"
    }


@router.get("/me/2fa/qr")
def get_2fa_qr(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user.totp_secret:
        raise HTTPException(400, "Run /me/2fa/setup first")

    totp = pyotp.TOTP(user.totp_secret)
    uri  = totp.provisioning_uri(name=f"FlyingFunds:{user.email}", issuer_name="FlyingFunds")

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.post("/me/2fa/verify")
def verify_2fa(
    payload: TOTPVerifyPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.totp_secret:
        raise HTTPException(400, "Run /me/2fa/setup first")
    if user.totp_enabled:
        raise HTTPException(400, "2FA is already enabled")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(400, "Invalid code — check your authenticator app")

    user.totp_enabled = True
    db.commit()
    return {"ok": True, "message": "2FA enabled successfully"}


@router.post("/me/2fa/disable")
def disable_2fa(
    payload: TOTPDisablePayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.totp_enabled:
        raise HTTPException(400, "2FA is not enabled")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(400, "Invalid code")

    user.totp_enabled = False
    user.totp_secret = None
    db.commit()
    return {"ok": True, "message": "2FA disabled"}


# ── Forgot / Reset password ───────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordPayload, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)
        db.commit()
        try:
            send_password_reset(user.email, token)
        except Exception as e:
            print(f"[Email error] {e}")

    return {"ok": True, "message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordPayload, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.reset_token == payload.token).first()

    if not user or not user.reset_token_expiry:
        raise HTTPException(400, "Invalid or expired reset link")

    if datetime.utcnow() > user.reset_token_expiry:
        raise HTTPException(400, "Reset link has expired — please request a new one")

    if len(payload.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    user.hashed_password = hash_password(payload.new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()

    return {"ok": True, "message": "Password updated — you can now log in"}