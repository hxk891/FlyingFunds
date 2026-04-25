import time
import requests
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fx", tags=["fx"])

FRANKFURTER = "https://api.frankfurter.app" #providing the live rates

# major currency pairs shown in the UI
MAJOR_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "CNY", "HKD", "SGD", "NOK", "SEK"]

# yfinance ticker format for forex pairs
YF_PAIRS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "USDCNY": "USDCNY=X", "USDHKD": "USDHKD=X",
    "USDSGD": "USDSGD=X",
}

# caches
_rates_cache: dict = {}
_rates_lock  = Lock()
RATES_TTL    = 5 * 60   # 5 minutes

_currencies_cache: dict = {}
_currencies_lock  = Lock()
CURRENCIES_TTL    = 60 * 60  # 1 hour 

_hist_cache: dict = {}
_hist_lock  = Lock()
HIST_TTL = {"1W": 15*60, "1M": 60*60, "3M": 4*60*60, "6M": 4*60*60, "1Y": 24*60*60}

YF_PERIOD = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
YFINTERVAL = {"1W": "30m", "1M": "1d", "3M": "1d", "6M": "1d", "1Y": "1wk"}


# get lateste rates from frankfuter with caching. 
def frankfurter_rates(base: str = "USD") -> dict:
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


# endpoints: return full currencies list cached for 1 hr

@router.get("/currencies")
def fx_currencies():
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

# Live exchange rates for all major currencies (GET /api/fx/rates?base=GBP)
@router.get("/rates")
def fx_rates(base: str = Query("USD", min_length=3, max_length=3)):
    base = base.upper()
    data = frankfurter_rates(base)
    rates = data.get("rates", {})

    # Build list with only relevant currencies
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
def fxConvert(
    amount: float = Query(..., gt=0),
    from_: str    = Query(..., alias="from", min_length=3, max_length=3),
    to:    str    = Query(..., min_length=3, max_length=3),
):
    #Convert an amount between two currencies using live rates
    from_cur = from_.upper()
    to_cur   = to.upper()

    if from_cur == to_cur:
        return {"from": from_cur, "to": to_cur, "amount": amount, "result": amount, "rate": 1.0}

    data  = frankfurter_rates(from_cur)
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

# Historical OHLCV data from  yfinance gives unix timestamps& OHLCV arrays
@router.get("/history")
def fx_history(
    pair:  str = Query("EURUSD", description="e.g. EURUSD, GBPUSD, USDJPY"),
    range: str = Query("1M",     pattern="^(1W|1M|3M|6M|1Y)$"),
):

    pair = pair.upper().replace("/", "").replace("-", "")
    yfTicker = YF_PAIRS.get(pair)
    if not yfTicker:
        # e.g. GBPEUR → GBPEUR=X
        yfTicker = f"{pair}=X"

    cache_key = (pair, range)
    now = time.time()
    with _hist_lock:
        cached = _hist_cache.get(cache_key)
        if cached and (now - cached["ts"]) < HIST_TTL[range]:
            return cached["data"]

    try:
        import yfinance as yf
        hist = yf.Ticker(yfTicker).history(
            period=YF_PERIOD[range],
            interval=YFINTERVAL[range],
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
