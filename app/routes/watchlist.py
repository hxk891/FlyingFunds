from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..deps import get_db
from ..models import WatchlistItem, User
from ..security import get_current_user

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    symbol: str
    notes: Optional[str] = None
    target_price: Optional[float] = None


@router.post("/", status_code=201)
def add_to_watchlist(
    payload: WatchlistAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    symbol = payload.symbol.strip().upper()

    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"{symbol} is already on your watchlist.")

    item = WatchlistItem(
        user_id=current_user.id,
        symbol=symbol,
        notes=payload.notes,
        target_price=payload.target_price,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "symbol": item.symbol,
        "notes": item.notes,
        "target_price": item.target_price,
        "added_at": item.added_at.isoformat(),
    }


@router.delete("/{item_id}", status_code=204)
def remove_from_watchlist(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")

    db.delete(item)
    db.commit()


class WatchlistUpdate(BaseModel):
    notes: Optional[str] = None
    target_price: Optional[float] = None


@router.get("/")
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id)
        .order_by(WatchlistItem.added_at.desc())
        .all()
    )
    return [
        {
            "id": i.id,
            "symbol": i.symbol,
            "notes": i.notes,
            "target_price": i.target_price,
            "added_at": i.added_at.isoformat(),
        }
        for i in items
    ]


@router.patch("/{item_id}")
def update_watchlist_item(
    item_id: int,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")

    if payload.notes is not None:
        item.notes = payload.notes
    if payload.target_price is not None:
        item.target_price = payload.target_price

    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "symbol": item.symbol,
        "notes": item.notes,
        "target_price": item.target_price,
    }
