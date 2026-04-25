from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional, List
import json

from app.security import get_current_user, verify_password, get_password_hash
from app.database import get_db
from app import models

router = APIRouter(prefix="/users", tags=["account"])


class MeUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    avatar: Optional[str] = None
    user_type: Optional[str] = None
    level: Optional[str] = None
    markets: Optional[List[str]] = None


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str


def _user_dict(user) -> dict:
    """Consistent response shape for all /me endpoints."""
    try:
        markets = json.loads(user.markets) if user.markets else []
    except Exception:
        markets = []

    return {
        "id": user.id,
        "email": user.email,
        "username": getattr(user, "username", None),
        "avatar": getattr(user, "avatar", "👤") or "👤",
        "user_type": getattr(user, "user_type", None),
        "level": getattr(user, "level", None),
        "markets": markets,
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return _user_dict(user)


@router.put("/me")
def update_me(
    payload: MeUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # Only update fields that were actually sent (not None)
    if payload.email is not None:
        # Check uniqueness if email changed
        if payload.email != user.email:
            clash = db.query(models.User).filter(
                models.User.email == payload.email
            ).first()
            if clash:
                raise HTTPException(400, "Email already in use")
        user.email = payload.email

    if payload.username is not None:
        user.username = payload.username

    if payload.avatar is not None:
        user.avatar = payload.avatar

    if payload.user_type is not None:
        user.user_type = payload.user_type

    if payload.level is not None:
        user.level = payload.level

    if payload.markets is not None:
        user.markets = json.dumps(payload.markets)

    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.put("/me/password")
def update_password(
    payload: PasswordUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.hashed_password = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()
    return {"ok": True}