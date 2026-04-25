"""
trading.py — paper trading + manual entry routes

Endpoints:
  POST /trading/deposit                   — add virtual cash to balance
  GET  /trading/balance                   — get current cash balance
  POST /trading/buy                       — paper buy at live Finnhub price
  POST /trading/sell                      — paper sell at live Finnhub price
  POST /trading/manual                    — log a manual trade at custom price
  GET  /trading/history/{portfolio_id}    — full transaction log
  GET  /trading/pnl/{portfolio_id}        — P&L per holding vs live price
"""

import os
import requests
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import User, Portfolio, Holding, Trade
from app.security import get_current_user

router = APIRouter(prefix="/trading", tags=["trading"])

DEFAULT_BALANCE = 10_000.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_live_price(symbol: str) -> float:
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise HTTPException(500, "FINNHUB_API_KEY not set")
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol.upper(), "token": api_key},
        timeout=10,
    )
    if not r.ok:
        raise HTTPException(502, f"Finnhub error: {r.text}")
    price = r.json().get("c")
    if not price:
        raise HTTPException(404, f"No live price found for {symbol.upper()}")
    return float(price)


def _get_portfolio(portfolio_id: int, user: User, db: Session) -> Portfolio:
    p = db.query(Portfolio).filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == user.id,
    ).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    return p


def _upsert_holding(portfolio_id: int, symbol: str, qty: float, price: float, db: Session):
    """Update or create a holding, recalculating avg buy price on buy."""
    h = db.query(Holding).filter(
        Holding.portfolio_id == portfolio_id,
        Holding.symbol == symbol,
    ).first()

    if h:
        # Weighted average buy price
        total_cost = (h.avg_buy_price * h.quantity) + (price * qty)
        h.quantity += qty
        h.avg_buy_price = total_cost / h.quantity if h.quantity > 0 else price
    else:
        h = Holding(
            portfolio_id=portfolio_id,
            symbol=symbol,
            quantity=qty,
            avg_buy_price=price,
        )
        db.add(h)

    db.flush()
    return h


def _reduce_holding(portfolio_id: int, symbol: str, qty: float, db: Session):
    """Reduce holding quantity on sell. Raises if insufficient shares."""
    h = db.query(Holding).filter(
        Holding.portfolio_id == portfolio_id,
        Holding.symbol == symbol,
    ).first()

    if not h or h.quantity < qty:
        raise HTTPException(400, f"Insufficient shares — you hold {h.quantity if h else 0:.4f} {symbol}")

    h.quantity -= qty
    if h.quantity <= 0:
        db.delete(h)
    db.flush()


# ── Schemas ───────────────────────────────────────────────────────────────────

class DepositPayload(BaseModel):
    amount: float


class BuyPayload(BaseModel):
    portfolio_id: int
    symbol: str
    quantity: float


class SellPayload(BaseModel):
    portfolio_id: int
    symbol: str
    quantity: float


class ManualTradePayload(BaseModel):
    portfolio_id: int
    symbol: str
    side: str           # "BUY" or "SELL"
    quantity: float
    price: float        # user-supplied price


# ── Balance ───────────────────────────────────────────────────────────────────

@router.get("/balance")
def get_balance(
    user: User = Depends(get_current_user),
):
    balance = getattr(user, "cash_balance", None)
    if balance is None:
        balance = DEFAULT_BALANCE
    return {"cash_balance": round(float(balance), 2)}


@router.post("/deposit")
def deposit(
    payload: DepositPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.amount <= 0:
        raise HTTPException(400, "Deposit amount must be positive")
    if payload.amount > 1_000_000:
        raise HTTPException(400, "Max single deposit is £1,000,000")

    current = float(getattr(user, "cash_balance") or DEFAULT_BALANCE)
    user.cash_balance = current + payload.amount
    db.commit()
    return {"cash_balance": round(float(user.cash_balance), 2), "deposited": payload.amount}


# ── Paper trading ─────────────────────────────────────────────────────────────

@router.post("/buy")
def paper_buy(
    payload: BuyPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.quantity <= 0:
        raise HTTPException(400, "Quantity must be positive")

    portfolio = _get_portfolio(payload.portfolio_id, user, db)
    symbol = payload.symbol.upper()
    price = _get_live_price(symbol)
    cost = price * payload.quantity

    balance = float(getattr(user, "cash_balance") or DEFAULT_BALANCE)
    if balance < cost:
        raise HTTPException(400, f"Insufficient funds — need £{cost:.2f}, have £{balance:.2f}")

    # Deduct cash
    user.cash_balance = balance - cost

    # Update holding
    _upsert_holding(portfolio.id, symbol, payload.quantity, price, db)

    # Log trade
    db.add(Trade(
        portfolio_id=portfolio.id,
        symbol=symbol,
        side="BUY",
        quantity=payload.quantity,
        price=price,
        ts=datetime.utcnow(),
    ))

    db.commit()
    return {
        "symbol": symbol,
        "side": "BUY",
        "quantity": payload.quantity,
        "price": price,
        "total_cost": round(cost, 2),
        "cash_balance": round(float(user.cash_balance), 2),
    }


@router.post("/sell")
def paper_sell(
    payload: SellPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.quantity <= 0:
        raise HTTPException(400, "Quantity must be positive")

    portfolio = _get_portfolio(payload.portfolio_id, user, db)
    symbol = payload.symbol.upper()
    price = _get_live_price(symbol)
    proceeds = price * payload.quantity

    # Reduce holding (raises if not enough shares)
    _reduce_holding(portfolio.id, symbol, payload.quantity, db)

    # Credit cash
    balance = float(getattr(user, "cash_balance") or DEFAULT_BALANCE)
    user.cash_balance = balance + proceeds

    # Log trade
    db.add(Trade(
        portfolio_id=portfolio.id,
        symbol=symbol,
        side="SELL",
        quantity=payload.quantity,
        price=price,
        ts=datetime.utcnow(),
    ))

    db.commit()
    return {
        "symbol": symbol,
        "side": "SELL",
        "quantity": payload.quantity,
        "price": price,
        "proceeds": round(proceeds, 2),
        "cash_balance": round(float(user.cash_balance), 2),
    }


# ── Manual entry ──────────────────────────────────────────────────────────────

@router.post("/manual")
def manual_trade(
    payload: ManualTradePayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.quantity <= 0:
        raise HTTPException(400, "Quantity must be positive")
    if payload.price <= 0:
        raise HTTPException(400, "Price must be positive")

    side = payload.side.upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(400, "Side must be BUY or SELL")

    portfolio = _get_portfolio(payload.portfolio_id, user, db)
    symbol = payload.symbol.upper()

    if side == "BUY":
        _upsert_holding(portfolio.id, symbol, payload.quantity, payload.price, db)
    else:
        _reduce_holding(portfolio.id, symbol, payload.quantity, db)

    db.add(Trade(
        portfolio_id=portfolio.id,
        symbol=symbol,
        side=side,
        quantity=payload.quantity,
        price=payload.price,
        ts=datetime.utcnow(),
    ))

    db.commit()
    return {
        "symbol": symbol,
        "side": side,
        "quantity": payload.quantity,
        "price": payload.price,
        "total": round(payload.quantity * payload.price, 2),
        "note": "Manual entry — cash balance not affected",
    }


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history/{portfolio_id}")
def trade_history(
    portfolio_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_portfolio(portfolio_id, user, db)  # ownership check

    trades = (
        db.query(Trade)
        .filter(Trade.portfolio_id == portfolio_id)
        .order_by(Trade.ts.desc())
        .all()
    )

    return {
        "portfolio_id": portfolio_id,
        "trades": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "price": t.price,
                "total": round(t.quantity * t.price, 2),
                "ts": t.ts.isoformat() if t.ts else None,
            }
            for t in trades
        ],
    }


# ── P&L ───────────────────────────────────────────────────────────────────────

@router.get("/pnl/{portfolio_id}")
def portfolio_pnl(
    portfolio_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_portfolio(portfolio_id, user, db)

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio_id).all()
    if not holdings:
        return {"portfolio_id": portfolio_id, "holdings": [], "total_pnl": 0.0}

    rows = []
    total_invested = 0.0
    total_current = 0.0

    for h in holdings:
        try:
            live_price = _get_live_price(h.symbol)
        except Exception:
            live_price = None

        cost_basis    = h.avg_buy_price * h.quantity
        current_value = (live_price * h.quantity) if live_price else None
        pnl           = (current_value - cost_basis) if current_value is not None else None
        pnl_pct       = (pnl / cost_basis * 100) if (pnl is not None and cost_basis > 0) else None

        total_invested += cost_basis
        if current_value:
            total_current += current_value

        rows.append({
            "symbol": h.symbol,
            "quantity": h.quantity,
            "avg_buy_price": round(h.avg_buy_price, 4),
            "live_price": round(live_price, 4) if live_price else None,
            "cost_basis": round(cost_basis, 2),
            "current_value": round(current_value, 2) if current_value else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
        })

    total_pnl = total_current - total_invested

    return {
        "portfolio_id": portfolio_id,
        "holdings": rows,
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / total_invested * 100), 2) if total_invested > 0 else 0.0,
    }