import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.security import get_current_user
from app import models

router = APIRouter(prefix="/trading", tags=["trading"])

DEFAULT_BALANCE = 10000.0

_price_cache: dict = {}
_price_cache_lock = Lock()
PRICE_CACHE_TTL = 60


def _get_portfolio_owned(db: Session, user_id: int, portfolio_id: int):
    p = db.query(models.Portfolio).filter(
        models.Portfolio.id == portfolio_id,
        models.Portfolio.user_id == user_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return p


class PaperTradeIn(BaseModel):
    portfolio_id: int
    symbol: str
    quantity: float


@router.post("/buy")
def paper_buy(payload: PaperTradeIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _get_portfolio_owned(db, user.id, payload.portfolio_id)

    symbol = payload.symbol.upper().strip()
    qty = payload.quantity
    if qty <= 0:
        raise HTTPException(400, "Quantity must be > 0")

    price = _live_price(symbol)
    total_cost = price * qty
    balance = _get_balance(user)

    if total_cost > balance:
        raise HTTPException(400, f"Insufficient funds. Need £{total_cost:.2f}, have £{balance:.2f}")

    db_user = db.query(models.User).filter(models.User.id == user.id).first()
    db_user.cash_balance = balance - total_cost

    t = models.Trade(portfolio_id=payload.portfolio_id, symbol=symbol, side="BUY", quantity=qty, price=price)
    db.add(t)

    h = db.query(models.Holding).filter(
        models.Holding.portfolio_id == payload.portfolio_id,
        models.Holding.symbol == symbol,
    ).first()

    if h is None:
        db.add(models.Holding(portfolio_id=payload.portfolio_id, symbol=symbol, quantity=qty, avg_buy_price=price))
    else:
        # weighted average cost basis: (old_qty * old_price + new_qty * new_price) / total_qty
        new_qty = h.quantity + qty
        h.avg_buy_price = ((h.quantity * h.avg_buy_price) + (qty * price)) / new_qty
        h.quantity = new_qty

    db.commit()
    db.refresh(db_user)
    return {"ok": True, "symbol": symbol, "quantity": qty, "price": price, "total_cost": total_cost, "balance": float(db_user.cash_balance)}


@router.post("/sell")
def paper_sell(payload: PaperTradeIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _get_portfolio_owned(db, user.id, payload.portfolio_id)

    symbol = payload.symbol.upper().strip()
    qty = payload.quantity
    if qty <= 0:
        raise HTTPException(400, "Quantity must be > 0")

    h = db.query(models.Holding).filter(
        models.Holding.portfolio_id == payload.portfolio_id,
        models.Holding.symbol == symbol,
    ).first()

    if h is None or h.quantity < qty:
        raise HTTPException(400, f"Not enough shares. Have {h.quantity if h else 0:.4f}, selling {qty}")

    price = _live_price(symbol)
    proceeds = price * qty

    db_user = db.query(models.User).filter(models.User.id == user.id).first()
    db_user.cash_balance = _get_balance(user) + proceeds

    t = models.Trade(portfolio_id=payload.portfolio_id, symbol=symbol, side="SELL", quantity=qty, price=price)
    db.add(t)

    h.quantity = h.quantity - qty
    if h.quantity < 0.0001:
        db.delete(h)

    db.commit()
    db.refresh(db_user)
    return {"ok": True, "symbol": symbol, "quantity": qty, "price": price, "proceeds": proceeds, "balance": float(db_user.cash_balance)}


# price fetching — extracted this after buy and sell both needed it
def _live_price(symbol: str) -> float:
    """Fetch live price with in-memory TTL cache to avoid hammering Finnhub."""
    sym = symbol.upper()
    now = time.time()

    with _price_cache_lock:
        cached = _price_cache.get(sym)
        if cached and (now - cached[1]) < PRICE_CACHE_TTL:
            return cached[0]

    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="FINNHUB_API_KEY not set")
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": sym, "token": api_key},
        timeout=10,
    )
    if not r.ok:
        raise HTTPException(status_code=502, detail=f"Finnhub error: {r.text}")
    price = r.json().get("c")
    if not price:
        raise HTTPException(status_code=502, detail=f"No price data for {symbol}")

    price = float(price)
    with _price_cache_lock:
        _price_cache[sym] = (price, now)
    return price


def _live_price_safe(symbol: str):
    try:
        return _live_price(symbol)
    except Exception:
        return None


class DepositIn(BaseModel):
    amount: float


@router.get("/balance")
def get_balance(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return {"balance": _get_balance(user)}


@router.post("/deposit")
def deposit(payload: DepositIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    if payload.amount > 1_000_000:
        raise HTTPException(400, "Maximum deposit is £1,000,000")
    db_user = db.query(models.User).filter(models.User.id == user.id).first()
    db_user.cash_balance = _get_balance(user) + payload.amount
    db.commit()
    db.refresh(db_user)
    return {"balance": float(db_user.cash_balance)}


# manual trade entry — doesnt hit the API, user provides the price themselves
class ManualTradeIn(BaseModel):
    portfolio_id: int
    symbol: str
    side: str
    quantity: float
    price: float


@router.post("/manual")
def manual_trade(payload: ManualTradeIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _get_portfolio_owned(db, user.id, payload.portfolio_id)

    symbol = payload.symbol.upper().strip()
    side = payload.side.upper().strip()
    if side not in ("BUY", "SELL"):
        raise HTTPException(400, "side must be BUY or SELL")
    if payload.quantity <= 0 or payload.price <= 0:
        raise HTTPException(400, "quantity and price must be > 0")

    t = models.Trade(portfolio_id=payload.portfolio_id, symbol=symbol, side=side, quantity=payload.quantity, price=payload.price)
    db.add(t)

    h = db.query(models.Holding).filter(
        models.Holding.portfolio_id == payload.portfolio_id,
        models.Holding.symbol == symbol,
    ).first()

    if side == "BUY":
        if h is None:
            db.add(models.Holding(portfolio_id=payload.portfolio_id, symbol=symbol, quantity=payload.quantity, avg_buy_price=payload.price))
        else:
            new_qty = h.quantity + payload.quantity
            h.avg_buy_price = ((h.quantity * h.avg_buy_price) + (payload.quantity * payload.price)) / new_qty
            h.quantity = new_qty
    else:
        if h is None or h.quantity < payload.quantity:
            raise HTTPException(400, "Not enough quantity to sell")
        h.quantity -= payload.quantity
        if h.quantity < 0.0001:
            db.delete(h)

    db.commit()
    return {"ok": True, "note": "Manual entry — cash balance not affected"}


# balance helper — extracted late, was inline in deposit/buy/sell originally
def _get_balance(user) -> float:
    val = getattr(user, "cash_balance", None)
    return float(val) if val is not None else DEFAULT_BALANCE


@router.get("/pnl/{portfolio_id}")
def pnl(portfolio_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _get_portfolio_owned(db, user.id, portfolio_id)

    holdings = db.query(models.Holding).filter(
        models.Holding.portfolio_id == portfolio_id,
        models.Holding.quantity > 0,
    ).all()

    if not holdings:
        return {"holdings": [], "total_cost": 0, "total_value": 0, "total_pnl": 0, "total_pnl_pct": 0, "balance": _get_balance(user)}

    symbols = list({h.symbol for h in holdings})
    prices = {}
    with ThreadPoolExecutor(max_workers=min(len(symbols), 6)) as ex:
        future_map = {ex.submit(_live_price_safe, s): s for s in symbols}
        for fut in as_completed(future_map):
            prices[future_map[fut]] = fut.result()

    rows = []
    total_cost = 0.0
    total_value = 0.0

    for h in holdings:
        live = prices.get(h.symbol)
        cost = h.quantity * h.avg_buy_price
        value = h.quantity * live if live is not None else None
        pnl_amt = (value - cost) if value is not None else None
        pnl_pct = ((live - h.avg_buy_price) / h.avg_buy_price * 100) if live is not None else None

        total_cost += cost
        if value is not None:
            total_value += value

        rows.append({
            "symbol": h.symbol,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "live_price": live,
            "cost": cost,
            "value": value,
            "pnl": pnl_amt,
            "pnl_pct": pnl_pct,
        })

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return {
        "holdings": rows,
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "balance": _get_balance(user),
    }


@router.get("/history/{portfolio_id}")
def history(portfolio_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _get_portfolio_owned(db, user.id, portfolio_id)

    trades = (
        db.query(models.Trade)
        .filter(models.Trade.portfolio_id == portfolio_id)
        .order_by(models.Trade.ts.desc())
        .limit(200)
        .all()
    )

    return {
        "trades": [
            {
                "ts": t.ts.isoformat() if t.ts else None,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "price": t.price,
                "total": t.quantity * t.price,
            }
            for t in trades
        ]
    }


@router.get("/investment-chart/{portfolio_id}")
def investment_chart(
    portfolio_id: int,
    symbol: str,
    days: int = 365,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Builds a day-by-day investment value series for a symbol.
    Strategy:
      1. Try Finnhub daily candles (requires paid plan for full history)
      2. Fall back to prices stored in our own DB (uploaded CSV)
      3. Fall back to trade-point-only chart (just the buy/sell moments)
    """
    _get_portfolio_owned(db, user.id, portfolio_id)
    symbol = symbol.upper().strip()

    from collections import defaultdict

    trades = (
        db.query(models.Trade)
        .filter(
            models.Trade.portfolio_id == portfolio_id,
            models.Trade.symbol == symbol,
        )
        .order_by(models.Trade.ts.asc())
        .all()
    )

    if not trades:
        raise HTTPException(404, "No trades found for this symbol in this portfolio")

    trade_map = defaultdict(list)
    for t in trades:
        day = t.ts.strftime("%Y-%m-%d") if t.ts else None
        if day:
            trade_map[day].append(t)

    candle_dates  = []
    candle_closes = []

    try:
        import yfinance as yf
        period = "1y" if days <= 365 else "5y"
        hist = yf.Ticker(symbol).history(period=period, interval="1d")
        if not hist.empty:
            candle_dates  = [ts.strftime("%Y-%m-%d") for ts in hist.index]
            candle_closes = hist["Close"].tolist()
    except Exception:
        pass

    if not candle_dates:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        db_prices = (
            db.query(models.Price)
            .filter(models.Price.symbol == symbol, models.Price.date >= cutoff)
            .order_by(models.Price.date.asc())
            .all()
        )
        if db_prices:
            candle_dates  = [p.date for p in db_prices]
            candle_closes = [p.close for p in db_prices]

    series = []
    source = "trades_only"

    if candle_dates and candle_closes:
        source = "historical"
        price_map = dict(zip(candle_dates, candle_closes))

        trade_events = sorted(
            [(t.ts.strftime("%Y-%m-%d"), t.side, t.quantity, t.price)
             for t in trades if t.ts],
            key=lambda x: x[0],
        )

        running_qty = 0.0
        cost_basis  = 0.0
        trade_idx   = 0

        for date in candle_dates:
            while trade_idx < len(trade_events) and trade_events[trade_idx][0] <= date:
                _, side, qty, price = trade_events[trade_idx]
                if side == "BUY":
                    cost_basis  += qty * price
                    running_qty += qty
                else:
                    running_qty = max(0.0, running_qty - qty)
                trade_idx += 1

            if running_qty > 0 and date in price_map:
                series.append({
                    "date":  date,
                    "value": round(running_qty * price_map[date], 2),
                    "cost":  round(cost_basis, 2),
                    "qty":   round(running_qty, 6),
                    "close": price_map[date],
                })

    else:
        running_qty = 0.0
        cost_basis  = 0.0
        for t in trades:
            if t.side == "BUY":
                cost_basis  += t.quantity * t.price
                running_qty += t.quantity
            else:
                running_qty = max(0, running_qty - t.quantity)
            day = t.ts.strftime("%Y-%m-%d") if t.ts else "unknown"
            if running_qty > 0:
                series.append({
                    "date":  day,
                    "value": round(running_qty * t.price, 2),
                    "cost":  round(cost_basis, 2),
                    "qty":   round(running_qty, 6),
                    "close": t.price,
                })

        try:
            api_key = os.getenv("FINNHUB_API_KEY", "")
            if api_key and running_qty > 0:
                r_live = requests.get(
                    "https://finnhub.io/api/v1/quote",
                    params={"symbol": symbol, "token": api_key},
                    timeout=8,
                )
                if r_live.ok:
                    live = r_live.json().get("c")
                    if live:
                        today = datetime.utcnow().strftime("%Y-%m-%d")
                        if not series or series[-1]["date"] != today:
                            series.append({
                                "date":  today,
                                "value": round(running_qty * float(live), 2),
                                "cost":  round(cost_basis, 2),
                                "qty":   round(running_qty, 6),
                                "close": float(live),
                            })
        except Exception:
            pass

    return {
        "symbol": symbol,
        "series": series,
        "source": source,
        "first_trade": trades[0].ts.isoformat() if trades else None,
    }
