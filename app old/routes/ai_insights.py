# app/routes/ai_insights.py
"""
Simple rule-based market insights derived from stored Price data or yfinance.
Uses SMA crossover as a trend signal and daily return std dev as a volatility proxy.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter(prefix="/ai", tags=["ai"])


def _sma(values: list, n: int):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _get_closes(symbol: str, db: Session) -> list:
    """Try DB price table first, fall back to yfinance."""
    rows = (
        db.query(models.Price)
        .filter(models.Price.symbol == symbol.upper())
        .order_by(models.Price.date.asc())
        .all()
    )
    if rows:
        return [r.close for r in rows if r.close is not None]

    try:
        import yfinance as yf
        hist = yf.Ticker(symbol.upper()).history(period="3mo", interval="1d")
        if not hist.empty:
            return hist["Close"].tolist()
    except Exception:
        pass

    return []


@router.get("/insights/{symbol}")
def insights(
    symbol: str,
    db: Session = Depends(get_db),
):
    closes = _get_closes(symbol, db)

    if len(closes) < 30:
        raise HTTPException(
            404,
            "Not enough price history for this symbol. "
            "Try a major ticker like AAPL or MSFT."
        )

    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    last  = closes[-1]

    trend = "neutral"
    if sma20 and sma50:
        if sma20 > sma50:
            trend = "bullish"
        elif sma20 < sma50:
            trend = "bearish"

    rets = [
        (closes[i] / closes[i - 1]) - 1
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]
    avg_ret = sum(rets) / len(rets) if rets else 0
    vol = (
        (sum((r - avg_ret) ** 2 for r in rets) / max(1, len(rets) - 1)) ** 0.5
        if len(rets) > 2 else 0
    )

    messages = {
        "bullish": "Momentum is positive — short-term average is above long-term average.",
        "bearish": "Momentum is negative — short-term average is below long-term average.",
        "neutral": "Momentum is mixed — no clear trend signal yet.",
    }

    return {
        "symbol": symbol.upper(),
        "last_close": last,
        "sma20": sma20,
        "sma50": sma50,
        "trend": trend,
        "volatility": round(vol, 6),
        "summary": messages[trend],
    }
