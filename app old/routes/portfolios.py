from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Portfolio, Holding, User, Trade
from ..security import get_current_user

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str
    category: Optional[str] = "General"

class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None

class HoldingCreate(BaseModel):
    symbol: str
    quantity: float
    avg_buy_price: float

class ReorderPayload(BaseModel):
    ordered_ids: List[int]  # portfolio IDs in desired order


def _owned(db, user_id, portfolio_id):
    p = db.query(Portfolio).filter(Portfolio.id == portfolio_id, Portfolio.user_id == user_id).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    return p


@router.post("/", status_code=201)
def create_portfolio(payload: PortfolioCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = Portfolio(name=payload.name, user_id=current_user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "category": getattr(p, "category", "General"), "sort_order": getattr(p, "sort_order", 0)}


@router.get("/")
def list_portfolios(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == current_user.id).all()
    # sort by sort_order if present, else id
    portfolios.sort(key=lambda p: (getattr(p, "sort_order", 0) or 0, p.id))
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": getattr(p, "category", "General") or "General",
            "sort_order": getattr(p, "sort_order", 0) or 0,
            "holding_count": len(p.holdings),
        }
        for p in portfolios
    ]


@router.patch("/{portfolio_id}")
def update_portfolio(portfolio_id: int, payload: PortfolioUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = _owned(db, current_user.id, portfolio_id)
    if payload.name is not None:
        p.name = payload.name
    if payload.category is not None:
        try:
            p.category = payload.category
        except Exception:
            pass
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "category": getattr(p, "category", "General")}


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = _owned(db, current_user.id, portfolio_id)
    db.delete(p)
    db.commit()


@router.post("/reorder")
def reorder_portfolios(payload: ReorderPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    for idx, pid in enumerate(payload.ordered_ids):
        p = db.query(Portfolio).filter(Portfolio.id == pid, Portfolio.user_id == current_user.id).first()
        if p:
            try:
                p.sort_order = idx
            except Exception:
                pass
    db.commit()
    return {"ok": True}


@router.post("/{portfolio_id}/holdings", status_code=201)
def add_holding(portfolio_id: int, payload: HoldingCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = _owned(db, current_user.id, portfolio_id)
    h = Holding(portfolio_id=portfolio.id, symbol=payload.symbol.upper(), quantity=payload.quantity, avg_buy_price=payload.avg_buy_price)
    db.add(h)
    db.commit()
    db.refresh(h)
    return {"id": h.id, "symbol": h.symbol, "quantity": h.quantity, "avg_buy_price": h.avg_buy_price}


@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = _owned(db, current_user.id, portfolio_id)
    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "category": getattr(portfolio, "category", "General") or "General",
        "holdings": [{"id": h.id, "symbol": h.symbol, "quantity": h.quantity, "avg_buy_price": h.avg_buy_price} for h in holdings],
    }