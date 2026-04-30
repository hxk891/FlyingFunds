from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Portfolio, Holding, User, Price, Trade
from ..security import get_current_user
from ..services.analytics import compute_basic_portfolio_analytics, compute_risk_metrics_from_returns
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

router = APIRouter(prefix="/analytics", tags=["analytics"])


# converts NaN or infinity to None before we send back JSON
# JSON cant serialise NaN so avoids crashes
def _safe(v):
    #Convert NaN / ±Infinity to None so JSON serialisation never blows up
    try:
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


#historical prices from yahoo finance
# not sure if this is the best way but it works
def _yf_prices(symbols: list, days: int = 365) -> pd.DataFrame:
    """
    Fetch historical close prices from Yahoo Finance for list of symbols. and return a data frame with date strings as index and symbols as columns.
    should returns empty data frame if yfinance is unavailable or all fetches fail.
    """
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    period = "1y" if days <= 365 else "5y"
    frames = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period=period, interval="1d")
            if not hist.empty:
                frames[sym] = hist["Close"].rename(sym)
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames.values(), axis=1)
    df.index = [ts.strftime("%Y-%m-%d") for ts in df.index]
    return df.sort_index()


@router.get("/portfolio/{portfolio_id}")
def analytics_for_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    holdings_payload = [
        {"symbol": h.symbol, "quantity": h.quantity, "avg_buy_price": h.avg_buy_price}
        for h in holdings
    ]
    result = compute_basic_portfolio_analytics(holdings_payload)
    return {"portfolio": {"id": portfolio.id, "name": portfolio.name}, **result}


# realistic price data when we dont have real prices
# uses geometric brownian motion - look at notes
# mu = drift (small upward trend), sigma = volatility (how much it bounces around)
def _synthetic_timeseries(holdings, days=365):
    if not holdings:
        return [], []

    dates = pd.date_range(end=datetime.today(), periods=days, freq='B')  # business days
    np.random.seed(sum(int(h.avg_buy_price * 100) for h in holdings) % 999983)

    portfolio_values = np.zeros(len(dates))

    for h in holdings:
        # price path: GBM-like random walk
        mu    = 0.0003          # small daily drift
        sigma = 0.015           # daily volatility ~1.5%
        price = float(h.avg_buy_price)
        qty   = float(h.quantity)

        shocks = np.random.normal(mu, sigma, len(dates))
        prices = price * np.cumprod(1 + shocks)
        portfolio_values += prices * qty

    series = [
        {"date": d.strftime("%Y-%m-%d"), "value": _safe(v)}
        for d, v in zip(dates, portfolio_values)
        if _safe(v) is not None
    ]

    pv = pd.Series(portfolio_values)
    daily_returns_raw = pv.pct_change().dropna()
    daily_returns = [
        {"date": dates[i+1].strftime("%Y-%m-%d"), "return": _safe(r)}
        for i, r in enumerate(daily_returns_raw)
        if _safe(r) is not None
    ]

    return series, daily_returns


@router.get("/portfolio/{portfolio_id}/timeseries")
def portfolio_timeseries(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    if not holdings:
        return {
            "portfolio": {"id": portfolio.id, "name": portfolio.name},
            "series": [], "daily_returns": [], "synthetic": False
        }

    symbols  = [h.symbol.upper() for h in holdings]
    qty_map  = {h.symbol.upper(): float(h.quantity) for h in holdings}
    prices   = db.query(Price).filter(Price.symbol.in_(symbols)).all()

    # real price data path via uploaded CSV prices
    if prices:
        df = pd.DataFrame([
            {"date": p.date, "symbol": p.symbol, "close": p.close}
            for p in prices
        ])
        pivot = df.pivot_table(
            index="date", columns="symbol", values="close", aggfunc="last"
        ).sort_index()

        # multiply each symbol's price by how many shares we hold
        for sym in symbols:
            if sym in pivot.columns:
                pivot[sym] = pivot[sym] * qty_map.get(sym, 0.0)

        portfolio_value = pivot.sum(axis=1, skipna=True)
        series = [{"date": d, "value": _safe(v)} for d, v in portfolio_value.items()
                  if _safe(v) is not None]
        daily_returns_raw = portfolio_value.pct_change().dropna()
        daily_returns = [
            {"date": d, "return": _safe(r)}
            for d, r in daily_returns_raw.items()
            if _safe(r) is not None
        ]
        return {
            "portfolio": {"id": portfolio.id, "name": portfolio.name},
            "series": series,
            "daily_returns": daily_returns,
            "synthetic": False,
        }

    # yfinance as a backup before going fully synthetic
    yf_pivot = _yf_prices(symbols)
    if not yf_pivot.empty:
        for sym in symbols:
            if sym in yf_pivot.columns:
                yf_pivot[sym] = yf_pivot[sym] * qty_map.get(sym, 0.0)
        portfolio_value = yf_pivot.sum(axis=1, skipna=True)
        series = [{"date": d, "value": _safe(v)} for d, v in portfolio_value.items()
                  if _safe(v) is not None]
        daily_returns_raw = portfolio_value.pct_change().dropna()
        daily_returns = [
            {"date": d, "return": _safe(r)}
            for d, r in daily_returns_raw.items()
            if _safe(r) is not None
        ]
        return {
            "portfolio": {"id": portfolio.id, "name": portfolio.name},
            "series": series,
            "daily_returns": daily_returns,
            "synthetic": False,
        }

    # synthetic data so the chart isnt empty and looks real!
    series, daily_returns = _synthetic_timeseries(holdings, days=365)
    return {
        "portfolio": {"id": portfolio.id, "name": portfolio.name},
        "series": series,
        "daily_returns": daily_returns,
        "synthetic": True,
    }


#Shadow Portfolio!!!!!!!!!!!!
# For every SELL trade, work out what that position would be worth TODAY
# if the user had never sold it, difference should be "cost of selling it"
# Positive cost  = selling bad (stock went up after you sold)
# Negative cost  = selling good (stock went down)

@router.get("/portfolio/{portfolio_id}/shadow")
def shadow_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # get all sell trades for this portfolio
    sells = (
        db.query(Trade)
        .filter(Trade.portfolio_id == portfolio_id, Trade.side.ilike("sell"))
        .order_by(Trade.ts)
        .all()
    )

    if not sells:
        return {
            "portfolio": {"id": portfolio.id, "name": portfolio.name},
            "shadow_positions": [],
            "total_missed": 0.0,
            "total_good_calls": 0.0,
            "net_cost": 0.0,
        }

    # sells by symbol aggregate quantity and weighted avg sell price
    from collections import defaultdict
    grouped = defaultdict(lambda: {"quantity": 0.0, "total_proceeds": 0.0, "trades": []})
    for t in sells:
        sym = t.symbol.upper()
        grouped[sym]["quantity"]       += t.quantity
        grouped[sym]["total_proceeds"] += t.quantity * t.price
        grouped[sym]["trades"].append({
            "ts":       t.ts.isoformat() if t.ts else None,
            "quantity": t.quantity,
            "price":    t.price,
        })

    symbols = list(grouped.keys())

    # gets price returns yfinance first, then DB price table as fallback
    current_prices = {}
    try:
        import yfinance as yf
        for sym in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="2d")
                if not hist.empty:
                    current_prices[sym] = float(hist["Close"].iloc[-1])
            except Exception:
                pass
    except ImportError:
        pass

    # fallback: latest price from our prices table
    for sym in symbols:
        if sym not in current_prices:
            row = (
                db.query(Price)
                .filter(Price.symbol == sym)
                .order_by(Price.date.desc())
                .first()
            )
            if row:
                current_prices[sym] = row.close

    # build shadow positions
    shadow_positions = []
    total_missed     = 0.0   # sum where holding would have been better
    total_good_calls = 0.0   # sum where selling was actually smart

    for sym, data in grouped.items():
        qty        = data["quantity"]
        proceeds   = data["total_proceeds"]   # what they actually received
        avg_sell   = proceeds / qty if qty > 0 else 0.0
        cur_price  = current_prices.get(sym)

        if cur_price is None:
            # cant calculate without a current price include but mark unknown
            shadow_positions.append({
                "symbol":        sym,
                "quantity":      qty,
                "avg_sell_price": _safe(avg_sell),
                "sale_proceeds": _safe(proceeds),
                "current_price": None,
                "current_value": None,
                "cost":          None,   # None = unknown
                "trades":        data["trades"],
            })
            continue

        current_value = qty * cur_price
        cost          = current_value - proceeds  # positive = you'd be richer if you'd held

        if cost > 0:
            total_missed += cost
        else:
            total_good_calls += abs(cost)

        shadow_positions.append({
            "symbol":         sym,
            "quantity":       qty,
            "avg_sell_price": _safe(avg_sell),
            "sale_proceeds":  _safe(proceeds),
            "current_price":  _safe(cur_price),
            "current_value":  _safe(current_value),
            "cost":           _safe(cost),
            "trades":         data["trades"],
        })

    # sort biggest regrets first
    shadow_positions.sort(key=lambda x: -(x["cost"] or 0))

    return {
        "portfolio":       {"id": portfolio.id, "name": portfolio.name},
        "shadow_positions": shadow_positions,
        "total_missed":    _safe(total_missed),
        "total_good_calls": _safe(total_good_calls),
        "net_cost":        _safe(total_missed - total_good_calls),
    }


@router.get("/portfolio/{portfolio_id}/risk")
def portfolio_risk(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    if not holdings:
        return {"portfolio": {"id": portfolio.id, "name": portfolio.name}, "metrics": {}}

    symbols = [h.symbol.upper() for h in holdings]
    qty_map = {h.symbol.upper(): float(h.quantity) for h in holdings}
    prices  = db.query(Price).filter(Price.symbol.in_(symbols)).all()

    if prices:
        df = pd.DataFrame([
            {"date": p.date, "symbol": p.symbol, "close": p.close}
            for p in prices
        ])
        pivot = df.pivot_table(
            index="date", columns="symbol", values="close", aggfunc="last"
        ).sort_index()
        for sym in symbols:
            if sym in pivot.columns:
                pivot[sym] = pivot[sym] * qty_map.get(sym, 0.0)
        portfolio_value = pivot.sum(axis=1, skipna=True)
        daily_returns   = portfolio_value.pct_change().dropna()
        used_synthetic  = False
    else:
        yf_pivot = _yf_prices(symbols)
        if not yf_pivot.empty:
            for sym in symbols:
                if sym in yf_pivot.columns:
                    yf_pivot[sym] = yf_pivot[sym] * qty_map.get(sym, 0.0)
            portfolio_value = yf_pivot.sum(axis=1, skipna=True)
            daily_returns   = portfolio_value.pct_change().dropna()
            used_synthetic  = False
        else:
            series, returns_list = _synthetic_timeseries(holdings, days=365)
            daily_returns  = pd.Series([r["return"] for r in returns_list])
            used_synthetic = True

    metrics_raw = compute_risk_metrics_from_returns(daily_returns, confidence=0.95)
    # sanitise every float in metrics so NaN/inf never breaks JSON serialisation
    metrics = {k: _safe(v) if isinstance(v, (int, float)) else v
               for k, v in metrics_raw.items()}
    return {
        "portfolio": {"id": portfolio.id, "name": portfolio.name},
        "metrics": metrics,
        "synthetic": used_synthetic,
    }


# Goal Projection ──────────────
# Answers "is my portfolio on track to hit this goal by this date?"
# 1. Compute current portfolio value from holdings × latest known prices
# 2. Estimate annualised return from 1 price history
# 3. forward to target_date...projected_value
# 4. Compare to target_amount on_track / close / off_track
@router.get("/portfolio/{portfolio_id}/goal-projection")
def goal_projection(
    portfolio_id: int,
    target_amount: float,
    target_date: str,          # YYYY-MM-DD
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(404, "Portfolio not found")

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio_id).all()

    #current portfolio value
    current_value = 0.0
    for h in holdings:
        latest = (
            db.query(Price)
            .filter(Price.symbol == h.symbol)
            .order_by(Price.date.desc())
            .first()
        )
        current_value += h.quantity * (latest.close if latest else h.avg_buy_price)

    # estimate annualreturn from 1yr price history
    ann_return   = None
    is_estimated = False
    from datetime import date as _date

    cutoff = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    symbol_returns = []

    for h in holdings:
        prices_rows = (
            db.query(Price)
            .filter(Price.symbol == h.symbol, Price.date >= cutoff)
            .order_by(Price.date)
            .all()
        )
        if len(prices_rows) >= 20:
            closes = [p.close for p in prices_rows]
            daily  = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
            if daily:
                mean_d = sum(daily) / len(daily)
                symbol_returns.append((1 + mean_d) ** 252 - 1)

    if symbol_returns:
        ann_return = sum(symbol_returns) / len(symbol_returns)
    else:
        # risk-profile fallback beginner 5%, intermediate 8%, advanced 12%
        fallback = {"beginner": 0.05, "intermediate": 0.08, "advanced": 0.12}
        ann_return   = fallback.get(current_user.level or "intermediate", 0.08)
        is_estimated = True

    # ── time remaining ───
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "target_date must be YYYY-MM-DD")

    today          = _date.today()
    days_remaining = (target_dt - today).days
    years_rem      = max(0.0, days_remaining / 365.25)

    # ── projections ───
    projected_value = current_value * ((1 + ann_return) ** years_rem) if years_rem > 0 else current_value

    required_return = None
    if years_rem > 0 and current_value > 0 and target_amount > 0:
        required_return = (target_amount / current_value) ** (1.0 / years_rem) - 1

    pct_of_target = (projected_value / target_amount * 100) if target_amount > 0 else 0.0

    if pct_of_target >= 95:
        status = "on_track"
    elif pct_of_target >= 70:
        status = "close"
    else:
        status = "off_track"

    return {
        "portfolio_id":    portfolio_id,
        "portfolio_name":  portfolio.name,
        "current_value":   _safe(current_value),
        "projected_value": _safe(projected_value),
        "target_amount":   _safe(target_amount),
        "ann_return":      _safe(ann_return),
        "is_estimated":    is_estimated,
        "required_return": _safe(required_return),
        "days_remaining":  days_remaining,
        "pct_of_target":   _safe(pct_of_target),
        "status":          status,
    }


# XIRR handles arbitrary dates
# try: treat each buy/sell as a cash flow (buys are negative, sells/current value positive)
#  express each date as years since first transaction
#  find the annualised rate r where NPV(r) = 0 using newton r
def _compute_xirr(cash_flows):
    if len(cash_flows) < 2:
        return None

    # strip timezone info so subtraction works cleanly
    t0 = cash_flows[0][0].replace(tzinfo=None)
    try:
        dates_y = [(cf[0].replace(tzinfo=None) - t0).days / 365.0 for cf in cash_flows]
        amounts = [float(cf[1]) for cf in cash_flows]
    except Exception:
        return None

    # NPV sum of each cash flow discounted back to t0
    # NPV(r) = sum(CF_i / (1+r)^t_i)
    def npv(r):
        if r <= -1:
            return None
        try:
            return sum(a / (1.0 + r) ** t for a, t in zip(amounts, dates_y))
        except (OverflowError, ZeroDivisionError):
            return None

    # derivative of NPVfor Newton-Raphson update step r = r - f(r)/f'(r)
    def dnpv(r):
        if r <= -1:
            return None
        try:
            return sum(-t * a / (1.0 + r) ** (t + 1) for a, t in zip(amounts, dates_y) if t > 0)
        except (OverflowError, ZeroDivisionError):
            return None

    # start at 10% and iterate
    # clamp rate so in iterations are fine
    rate = 0.1
    for _ in range(200):
        v  = npv(rate)
        dv = dnpv(rate)
        if v is None or dv is None or abs(dv) < 1e-12:
            break
        rate -= v / dv
        rate  = max(-0.9999, min(rate, 100.0))
        if v is not None and abs(v) < 1e-8:
            break

    # if we get  (>5000% pa) something went wrong
    return rate if -0.9999 < rate < 50.0 else None


# XIRR internal rate of return based on actual trades made by user
    #XIRR, current value, cost basis, and P&L a portfolio.
@router.get("/portfolio/{portfolio_id}/irr")
def portfolio_irr(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    empty_resp = {
        "portfolio": {"id": portfolio.id, "name": portfolio.name},
        "xirr": None, "current_value": None, "cost_basis": None,
        "total_pl": None, "total_pl_pct": None, "trade_count": 0,
    }
    if not holdings:
        return empty_resp

    trades = (
        db.query(Trade)
        .filter(Trade.portfolio_id == portfolio.id)
        .order_by(Trade.ts)
        .all()
    )

    # portfolio is current worth
    symbols = [h.symbol.upper() for h in holdings]
    qty_map = {h.symbol.upper(): float(h.quantity) for h in holdings}
    prices  = db.query(Price).filter(Price.symbol.in_(symbols)).all()

    current_value = 0.0
    if prices:
        # most recent price we have for each symbol
        latest = {}
        for p in prices:
            if p.symbol not in latest or p.date > latest[p.symbol].date:
                latest[p.symbol] = p
        for h in holdings:
            sym = h.symbol.upper()
            pv  = latest[sym].close if sym in latest else h.avg_buy_price
            current_value += pv * qty_map[sym]
    else:
        yf_pivot = _yf_prices(symbols, days=5)
        for h in holdings:
            sym = h.symbol.upper()
            if not yf_pivot.empty and sym in yf_pivot.columns:
                col = yf_pivot[sym].dropna()
                pv  = float(col.iloc[-1]) if len(col) else h.avg_buy_price
            else:
                pv = h.avg_buy_price
            current_value += pv * qty_map[sym]

    # build cash flows: buys are negative (money out), sells are positive (money in)
    # add current portfolio value as final positive cash flow (like liquidating today)
    now = datetime.utcnow()
    if trades:
        cash_flows = []
        for t in trades:
            amt = float(t.quantity) * float(t.price)
            side = (t.side or "buy").lower()
            cash_flows.append((t.ts, -amt if side in ("buy", "b", "long") else +amt))
        cash_flows.append((now, current_value))
        cost_basis = sum(-cf[1] for cf in cash_flows if cf[1] < 0)
    else:
        # No trade history treat portfolio.created_at as single buy at cost basis
        cost_basis = sum(h.avg_buy_price * h.quantity for h in holdings)
        created = portfolio.created_at or now
        cash_flows = [(created, -cost_basis), (now, current_value)]

    xirr_rate   = _compute_xirr(cash_flows)
    total_pl    = current_value - cost_basis
    # total P&L as a percentage of what we originally put in
    total_pl_pct = (total_pl / cost_basis * 100) if cost_basis > 0 else 0.0

    return {
        "portfolio":     {"id": portfolio.id, "name": portfolio.name},
        "xirr":          _safe(xirr_rate),
        "current_value": _safe(current_value),
        "cost_basis":    _safe(cost_basis),
        "total_pl":      _safe(total_pl),
        "total_pl_pct":  _safe(total_pl_pct),
        "trade_count":   len(trades),
    }


# efficient frontier using monte carlo simulation
# randomly generate thousands of portfoloi weight combinations and plot to find the best risk/return tradeoffs
@router.get("/portfolio/{portfolio_id}/frontier")
def efficient_frontier(
    portfolio_id: int,
    n_portfolios: int = 3000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    #Monte Carlo efficient frontier showing simulated portfolios (return, volatility, sharpe, weights)
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.user_id == current_user.id)
        .first()
    )
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    holdings = db.query(Holding).filter(Holding.portfolio_id == portfolio.id).all()
    if not holdings:
        raise HTTPException(status_code=400, detail="No holdings in this portfolio.")

    symbols  = [h.symbol.upper() for h in holdings]
    qty_map  = {h.symbol.upper(): float(h.quantity)       for h in holdings}
    cost_map = {h.symbol.upper(): float(h.avg_buy_price)  for h in holdings}
    n        = len(symbols)

    # per-asset daily returns from price data
    prices = db.query(Price).filter(Price.symbol.in_(symbols)).all()
    synthetic = not bool(prices)

    if prices:
        df = pd.DataFrame([
            {"date": p.date, "symbol": p.symbol, "close": p.close}
            for p in prices
        ])
        pivot = df.pivot_table(
            index="date", columns="symbol", values="close", aggfunc="last"
        ).sort_index().ffill().dropna()

        # only symbols with price data
        available = [s for s in symbols if s in pivot.columns]
        if len(available) < 2:
            raise HTTPException(
                status_code=400,
                detail="Need price data for at least 2 holdings. Upload a CSV with more symbols."
            )
        pivot = pivot[available]
        symbols = available
        n = len(symbols)
        returns_df = pivot.pct_change().dropna()

    else:
        # tries yfinance before going fully synthetic
        yf_pivot = _yf_prices(symbols)
        available_yf = [s for s in symbols if s in yf_pivot.columns] if not yf_pivot.empty else []

        if len(available_yf) >= 2:
            returns_df = yf_pivot[available_yf].pct_change().dropna()
            symbols    = available_yf
            n          = len(symbols)
            synthetic  = False
        else:
            # generates per-asset GBM returns using avg_buy_price as seed
            np.random.seed(sum(int(cost_map[s] * 100) for s in symbols) % 999983)
            days = 252
            returns_data = {}
            for sym in symbols:
                mu    = np.random.uniform(0.04, 0.18)
                sigma = np.random.uniform(0.12, 0.35)
                daily_r = np.random.normal(mu / 252, sigma / np.sqrt(252), days)
                returns_data[sym] = daily_r
            returns_df = pd.DataFrame(returns_data)

    # annualise returns and covariance matrix, multiply by 252 trading days
    mean_returns = returns_df.mean() * 252
    cov_matrix   = returns_df.cov()   * 252

    # current portfolio weights by cost basis (what we actually paid)
    costs = {s: cost_map[s] * qty_map.get(s, 1.0) for s in symbols}
    total_cost = sum(costs.values())
    current_weights = np.array([costs[s] / total_cost for s in symbols])

    def portfolio_stats(w):
        # portfolio return = weighted average of individual returns
        ret = float(np.dot(w, mean_returns))
        # portfolio volatility = sqrt(w^T * cov * w) for correlations between assets
        vol = float(np.sqrt(np.dot(w, np.dot(cov_matrix.values, w))))
        # sharpe = return / volatility simplified
        sharpe = ret / vol if vol > 0 else 0.0
        return ret, vol, sharpe

    # run the monte carlo 3000 random weight combinations and score
    # TODO: could use with scipy.optimize...reasearch
    np.random.seed(42)
    results = []
    for _ in range(n_portfolios):
        w = np.random.dirichlet(np.ones(n))   # random weights summing to 1
        ret, vol, sharpe = portfolio_stats(w)
        results.append({
            "return":   round(ret,    4),
            "vol":      round(vol,    4),
            "sharpe":   round(sharpe, 4),
            "weights":  {s: round(float(w[i]), 4) for i, s in enumerate(symbols)},
        })

    # find the best portfolios from the simulations
    min_vol  = min(results, key=lambda x: x["vol"])
    max_shar = max(results, key=lambda x: x["sharpe"])

    c_ret, c_vol, c_shar = portfolio_stats(current_weights)

    return {
        "portfolio":   {"id": portfolio.id, "name": portfolio.name},
        "symbols":     symbols,
        "simulations": results,
        "current": {
            "return":  round(c_ret,  4),
            "vol":     round(c_vol,  4),
            "sharpe":  round(c_shar, 4),
            "weights": {s: round(float(current_weights[i]), 4)
                        for i, s in enumerate(symbols)},
        },
        "optimal": {
            "min_vol":   min_vol,
            "max_sharpe": max_shar,
        },
        "synthetic": synthetic,
    }


@router.get("/benchmark/timeseries")
def benchmark_timeseries(
    symbol: str = "SPY",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return daily close prices for a benchmark (default SPY = S&P 500)."""
    yf_pivot = _yf_prices([symbol], days=365)
    if yf_pivot.empty or symbol not in yf_pivot.columns:
        return {"series": [], "symbol": symbol, "name": symbol}
    series = [
        {"date": d, "value": _safe(v)}
        for d, v in yf_pivot[symbol].items()
        if _safe(v) is not None
    ]
    name_map = {"SPY": "S&P 500", "QQQ": "NASDAQ 100", "IWM": "Russell 2000", "DIA": "Dow Jones"}
    return {"series": series, "symbol": symbol, "name": name_map.get(symbol, symbol)}
