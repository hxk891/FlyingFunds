import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user

router = APIRouter(prefix="/api/learn", tags=["learn"])

VALID_TOPICS = {
    "mpt", "capm", "diversification", "sharpe", "var",
    "drawdown", "volatility", "emh", "active-passive",
    "anomalies", "behavioural", "biases",
}


class MarkReadPayload(BaseModel):
    topic_id: str


@router.post("/progress")
def mark_read(
    payload: MarkReadPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.topic_id not in VALID_TOPICS:
        raise HTTPException(status_code=400, detail="Unknown topic_id")

    read = _get_read(current_user)
    if payload.topic_id not in read:
        read.append(payload.topic_id)
        current_user.read_topics = json.dumps(read)
        db.commit()

    return {"read": read}


@router.delete("/progress/{topic_id}")
def unmark_read(
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    read = _get_read(current_user)
    if topic_id in read:
        read.remove(topic_id)
        current_user.read_topics = json.dumps(read)
        db.commit()

    return {"read": read}


@router.get("/progress")
def get_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"read": _get_read(current_user)}


def _get_read(user: User) -> list[str]:
    try:
        return json.loads(user.read_topics or "[]")
    except Exception:
        return []


@router.post("/progress/reset")
def reset_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.read_topics = "[]"
    db.commit()
    return {"read": []}
