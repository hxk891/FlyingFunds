# app/routes/market.py
import os, time
import requests
from threading import Lock
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/market", tags=["market"])

# ── Server-side candle cache ───────────────────────────────────────────────────
_candle_cache: dict = {}
_candle_lock = Lock()
_CANDLE_TTL = {
    "1D":  5 * 60,
    "1W":  15 * 60,
    "1M":  60 * 60,
    "3M":  4 * 60 * 60,
    "6M":  4 * 60 * 60,
    "1Y":  24 * 60 * 60,
    "ALL": 24 * 60 * 60,
}

# yfinance period/interval mapping
_YF_MAP = {
    "1D":  {"period": "1d",  "interval": "5m"},
    "1W":  {"period": "5d",  "interval": "30m"},
    "1M":  {"period": "1mo", "interval": "1d"},
    "3M":  {"period": "3mo", "interval": "1d"},
    "6M":  {"period": "6mo", "interval": "1d"},
    "1Y":  {"period": "1y",  "interval": "1wk"},
    "ALL": {"period": "5y",  "interval": "1wk"},
}


def _require_finnhub_key():
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="FINNHUB_API_KEY not set")
    return api_key


def _fetch_yfinance(sym: str, range: str) -> dict:
    """Fetch OHLCV data from Yahoo Finance via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(503, "yfinance not installed")

    params = _YF_MAP[range]
    ticker = yf.Ticker(sym)
    hist = ticker.history(period=params["period"], interval=params["interval"])

    if hist.empty:
        raise HTTPException(404, f"No price data found for {sym}")

    # Convert DatetimeIndex to Unix timestamps (seconds)
    timestamps = [int(ts.timestamp()) for ts in hist.index]

    return {
        "symbol": sym,
        "range": range,
        "resolution": params["interval"],
        "t": timestamps,
        "o": [round(v, 4) for v in hist["Open"].tolist()],
        "h": [round(v, 4) for v in hist["High"].tolist()],
        "l": [round(v, 4) for v in hist["Low"].tolist()],
        "c": [round(v, 4) for v in hist["Close"].tolist()],
        "v": [int(v) for v in hist["Volume"].tolist()],
    }


@router.get("/public/quote/{symbol}")
def public_quote(symbol: str):
    """Live quote from Finnhub (works on free tier)."""
    api_key = _require_finnhub_key()
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol.upper(), "token": api_key},
        timeout=10
    )
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    data = r.json()
    return {
        "symbol": symbol.upper(),
        "price": data.get("c"),
        "change": data.get("d"),
        "change_pct": data.get("dp"),
        "prev_close": data.get("pc"),
        "high": data.get("h"),
        "low": data.get("l"),
        "open": data.get("o"),
    }


@router.get("/public/candles/{symbol}")
def public_candles(
    symbol: str,
    range: str = Query("1M", pattern="^(1D|1W|1M|3M|6M|1Y|ALL)$"),
):
    """
    OHLCV candles via yfinance (free, no API key needed).
    Finnhub candles require a paid plan so we use Yahoo Finance instead.
    Results are cached server-side to avoid hammering Yahoo.
    """
    sym = symbol.upper()
    now = int(time.time())
    cache_key = (sym, range)

    with _candle_lock:
        cached = _candle_cache.get(cache_key)
        if cached and (now - cached["ts"]) < _CANDLE_TTL[range]:
            return cached["data"]

    result = _fetch_yfinance(sym, range)

    with _candle_lock:
        _candle_cache[cache_key] = {"data": result, "ts": now}

    return result
