# app/routes/fx.py
"""
FX (Foreign Exchange) feature.
Live rates from Frankfurter API (free, no key needed).
Historical OHLCV from yfinance (free).
Both endpoints cached server-side.
"""
import time
import requests
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fx", tags=["fx"])

FRANKFURTER = "https://api.frankfurter.app"

# Major currency pairs shown in the UI
MAJOR_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "CNY", "HKD", "SGD", "NOK", "SEK"]

# yfinance ticker format for forex pairs
YF_PAIRS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "USDCNY": "USDCNY=X", "USDHKD": "USDHKD=X",
    "USDSGD": "USDSGD=X",
}

# ── Caches ─────────────────────────────────────────────────────────────────────
_rates_cache: dict = {}
_rates_lock  = Lock()
RATES_TTL    = 5 * 60   # 5 minutes

_currencies_cache: dict = {}
_currencies_lock  = Lock()
CURRENCIES_TTL    = 60 * 60  # 1 hour — the list barely changes

_hist_cache: dict = {}
_hist_lock  = Lock()
_HIST_TTL = {"1W": 15*60, "1M": 60*60, "3M": 4*60*60, "6M": 4*60*60, "1Y": 24*60*60}

_YF_PERIOD = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
_YF_INTERVAL = {"1W": "30m", "1M": "1d", "3M": "1d", "6M": "1d", "1Y": "1wk"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _frankfurter_rates(base: str = "USD") -> dict:
    """Fetch latest rates from Frankfurter API with caching."""
    now = time.time()
    key = base.upper()
    with _rates_lock:
        cached = _rates_cache.get(key)
        if cached and (now - cached["ts"]) < RATES_TTL:
            return cached["data"]

    r = requests.get(f"{FRANKFURTER}/latest", params={"from": key}, timeout=8)
    if not r.ok:
        raise HTTPException(502, f"Frankfurter API error: {r.status_code}")
    data = r.json()

    with _rates_lock:
        _rates_cache[key] = {"data": data, "ts": now}
    return data


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/currencies")
def fx_currencies():
    """
    Returns the full list of currencies supported by Frankfurter.
    Cached 1 hour — the list changes very rarely.
    """
    now = time.time()
    with _currencies_lock:
        if _currencies_cache.get("data") and (now - _currencies_cache.get("ts", 0)) < CURRENCIES_TTL:
            return _currencies_cache["data"]

    try:
        r = requests.get(f"{FRANKFURTER}/currencies", timeout=8)
        if not r.ok:
            raise HTTPException(502, "Could not fetch currency list")
        # Frankfurter returns { "AUD": "Australian Dollar", "BGN": "Bulgarian Lev", ... }
        data = r.json()
    except requests.RequestException:
        raise HTTPException(502, "Could not reach Frankfurter API")

    result = [{"code": code, "name": name} for code, name in sorted(data.items())]

    with _currencies_lock:
        _currencies_cache["data"] = result
        _currencies_cache["ts"]   = now

    return result


@router.get("/rates")
def fx_rates(base: str = Query("USD", min_length=3, max_length=3)):
    """
    Live exchange rates for all major currencies from a given base.
    e.g. GET /api/fx/rates?base=GBP
    """
    base = base.upper()
    data = _frankfurter_rates(base)
    rates = data.get("rates", {})

    # Build enriched list: only the currencies we care about
    result = []
    for cur in MAJOR_CURRENCIES:
        if cur == base:
            continue
        rate = rates.get(cur)
        if rate is None:
            continue
        result.append({
            "currency": cur,
            "rate": round(float(rate), 6),
            "display": f"1 {base} = {rate:.4f} {cur}",
        })

    return {
        "base": base,
        "date": data.get("date", ""),
        "rates": result,
        "all_rates": rates,   # for the converter dropdown
    }


@router.get("/convert")
def fx_convert(
    amount: float = Query(..., gt=0),
    from_: str    = Query(..., alias="from", min_length=3, max_length=3),
    to:    str    = Query(..., min_length=3, max_length=3),
):
    """Convert an amount between two currencies using live rates."""
    from_cur = from_.upper()
    to_cur   = to.upper()

    if from_cur == to_cur:
        return {"from": from_cur, "to": to_cur, "amount": amount, "result": amount, "rate": 1.0}

    data  = _frankfurter_rates(from_cur)
    rates = data.get("rates", {})

    if to_cur not in rates:
        raise HTTPException(404, f"Currency {to_cur} not available")

    rate   = float(rates[to_cur])
    result = round(amount * rate, 6)

    return {
        "from":   from_cur,
        "to":     to_cur,
        "amount": amount,
        "result": result,
        "rate":   round(rate, 6),
        "date":   data.get("date", ""),
    }


@router.get("/history")
def fx_history(
    pair:  str = Query("EURUSD", description="e.g. EURUSD, GBPUSD, USDJPY"),
    range: str = Query("1M",     pattern="^(1W|1M|3M|6M|1Y)$"),
):
    """
    Historical OHLCV data for a forex pair via yfinance.
    Returns unix timestamps + OHLCV arrays for TradingView.
    """
    pair = pair.upper().replace("/", "").replace("-", "")
    yf_ticker = YF_PAIRS.get(pair)
    if not yf_ticker:
        # Try constructing it — e.g. GBPEUR → GBPEUR=X
        yf_ticker = f"{pair}=X"

    cache_key = (pair, range)
    now = time.time()
    with _hist_lock:
        cached = _hist_cache.get(cache_key)
        if cached and (now - cached["ts"]) < _HIST_TTL[range]:
            return cached["data"]

    try:
        import yfinance as yf
        hist = yf.Ticker(yf_ticker).history(
            period=_YF_PERIOD[range],
            interval=_YF_INTERVAL[range],
        )
    except ImportError:
        raise HTTPException(503, "yfinance not installed")

    if hist.empty:
        raise HTTPException(404, f"No data for pair {pair}")

    timestamps = [int(ts.timestamp()) for ts in hist.index]
    result = {
        "pair":  pair,
        "range": range,
        "t": timestamps,
        "o": [round(v, 6) for v in hist["Open"].tolist()],
        "h": [round(v, 6) for v in hist["High"].tolist()],
        "l": [round(v, 6) for v in hist["Low"].tolist()],
        "c": [round(v, 6) for v in hist["Close"].tolist()],
    }

    with _hist_lock:
        _hist_cache[cache_key] = {"data": result, "ts": now}

    return result
