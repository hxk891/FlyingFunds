from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Portfolio, Holding, User, Price
from ..security import get_current_user
from ..services.analytics import compute_basic_portfolio_analytics, compute_risk_metrics_from_returns
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _yf_prices(symbols: list, days: int = 365) -> pd.DataFrame:
    """
    Fetch historical close prices from Yahoo Finance for a list of symbols.
    Returns a DataFrame with date strings as index and symbols as columns.
    Returns empty DataFrame if yfinance is unavailable or all fetches fail.
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


def _synthetic_timeseries(holdings, days=365):
    """
    Generate a realistic synthetic portfolio value timeseries using a
    correlated random walk seeded from each holding's avg_buy_price.
    Used as a fallback when no price CSV has been uploaded.
    """
    if not holdings:
        return [], []

    dates = pd.date_range(end=datetime.today(), periods=days, freq='B')  # business days
    np.random.seed(sum(int(h.avg_buy_price * 100) for h in holdings) % 999983)

    portfolio_values = np.zeros(len(dates))

    for h in holdings:
        # Simulate price path: GBM-like random walk
        mu    = 0.0003          # small daily drift
        sigma = 0.015           # daily volatility ~1.5%
        price = float(h.avg_buy_price)
        qty   = float(h.quantity)

        shocks = np.random.normal(mu, sigma, len(dates))
        prices = price * np.cumprod(1 + shocks)
        portfolio_values += prices * qty

    series = [
        {"date": d.strftime("%Y-%m-%d"), "value": float(v)}
        for d, v in zip(dates, portfolio_values)
    ]

    pv = pd.Series(portfolio_values)
    daily_returns_raw = pv.pct_change().dropna()
    daily_returns = [
        {"date": dates[i+1].strftime("%Y-%m-%d"), "return": float(r)}
        for i, r in enumerate(daily_returns_raw)
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

    # ── Real price data path ──────────────────────────────────────────────
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
        series = [{"date": d, "value": float(v)} for d, v in portfolio_value.items()]
        daily_returns_raw = portfolio_value.pct_change().dropna()
        daily_returns = [
            {"date": d, "return": float(r)}
            for d, r in daily_returns_raw.items()
        ]
        return {
            "portfolio": {"id": portfolio.id, "name": portfolio.name},
            "series": series,
            "daily_returns": daily_returns,
            "synthetic": False,
        }

    # ── yfinance fallback ─────────────────────────────────────────────────
    yf_pivot = _yf_prices(symbols)
    if not yf_pivot.empty:
        for sym in symbols:
            if sym in yf_pivot.columns:
                yf_pivot[sym] = yf_pivot[sym] * qty_map.get(sym, 0.0)
        portfolio_value = yf_pivot.sum(axis=1, skipna=True)
        series = [{"date": d, "value": float(v)} for d, v in portfolio_value.items()]
        daily_returns_raw = portfolio_value.pct_change().dropna()
        daily_returns = [
            {"date": d, "return": float(r)}
            for d, r in daily_returns_raw.items()
        ]
        return {
            "portfolio": {"id": portfolio.id, "name": portfolio.name},
            "series": series,
            "daily_returns": daily_returns,
            "synthetic": False,
        }

    # ── Synthetic last resort ─────────────────────────────────────────────
    series, daily_returns = _synthetic_timeseries(holdings, days=365)
    return {
        "portfolio": {"id": portfolio.id, "name": portfolio.name},
        "series": series,
        "daily_returns": daily_returns,
        "synthetic": True,
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

    metrics = compute_risk_metrics_from_returns(daily_returns, confidence=0.95)
    return {
        "portfolio": {"id": portfolio.id, "name": portfolio.name},
        "metrics": metrics,
        "synthetic": used_synthetic,
    }


@router.get("/portfolio/{portfolio_id}/frontier")
def efficient_frontier(
    portfolio_id: int,
    n_portfolios: int = 3000,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Monte Carlo efficient frontier.
    Returns simulated portfolios (return, volatility, sharpe, weights)
    plus the current portfolio point.
    """
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

    # ── Build per-asset daily returns from price data ─────────────────────────
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

        # Keep only symbols with price data
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
        # Try yfinance before going fully synthetic
        yf_pivot = _yf_prices(symbols)
        available_yf = [s for s in symbols if s in yf_pivot.columns] if not yf_pivot.empty else []

        if len(available_yf) >= 2:
            returns_df = yf_pivot[available_yf].pct_change().dropna()
            symbols    = available_yf
            n          = len(symbols)
            synthetic  = False
        else:
            # Synthetic: generate per-asset GBM returns using avg_buy_price as seed
            np.random.seed(sum(int(cost_map[s] * 100) for s in symbols) % 999983)
            days = 252
            returns_data = {}
            for sym in symbols:
                mu    = np.random.uniform(0.04, 0.18)
                sigma = np.random.uniform(0.12, 0.35)
                daily_r = np.random.normal(mu / 252, sigma / np.sqrt(252), days)
                returns_data[sym] = daily_r
            returns_df = pd.DataFrame(returns_data)

    # ── Annual stats ──────────────────────────────────────────────────────────
    mean_returns = returns_df.mean() * 252            # annualised
    cov_matrix   = returns_df.cov()   * 252            # annualised covariance

    # ── Current portfolio weights (by cost basis) ─────────────────────────────
    costs = {s: cost_map[s] * qty_map.get(s, 1.0) for s in symbols}
    total_cost = sum(costs.values())
    current_weights = np.array([costs[s] / total_cost for s in symbols])

    def portfolio_stats(w):
        ret = float(np.dot(w, mean_returns))
        vol = float(np.sqrt(np.dot(w, np.dot(cov_matrix.values, w))))
        sharpe = ret / vol if vol > 0 else 0.0
        return ret, vol, sharpe

    # ── Monte Carlo simulation ─────────────────────────────────────────────────
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

    # ── Min-vol and max-Sharpe portfolios ─────────────────────────────────────
    min_vol  = min(results, key=lambda x: x["vol"])
    max_shar = max(results, key=lambda x: x["sharpe"])

    # ── Current portfolio point ───────────────────────────────────────────────
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