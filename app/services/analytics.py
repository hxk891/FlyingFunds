from typing import Dict, List
import pandas as pd
import numpy as np

# basic analytics for a portfolio — takes a list of holdings and returns totals/weights
def compute_basic_portfolio_analytics(holdings: List[dict]) -> Dict:
    """
    holdings: list of dicts containing symbol, quantity, avg_buy_price
    """
    rows = []
    total_invested = 0.0

    # loop through each holding and calcualte how much money is in it
    for h in holdings:
        value = float(h["quantity"]) * float(h["avg_buy_price"])
        total_invested += value
        rows.append({
            "symbol": h["symbol"],
            "quantity": float(h["quantity"]),
            "avg_buy_price": float(h["avg_buy_price"]),
            "invested_value": value,
        })

    # Avoid division by zero
    if total_invested > 0:
        for r in rows:
            # weight = how much of the total is in this one holding, as a fraction
            r["weight"] = r["invested_value"] / total_invested
    else:
        for r in rows:
            r["weight"] = 0.0

    return {
        "total_invested": total_invested,
        "num_holdings": len(rows),
        "holdings": rows,
        "weights": {r["symbol"]: r["weight"] for r in rows},
    }

# this one does the risk stuff — needs a pandas series of daily returns
def compute_risk_metrics_from_returns(daily_returns: pd.Series, confidence: float = 0.95) -> dict:
    """
    daily_returns: pandas Series of daily returns (e.g. 0.01 for 1%)
    confidence: 0.95 for VaR 95%
    """
    if daily_returns is None or len(daily_returns) < 2:
        return {
            "n_days": int(len(daily_returns) if daily_returns is not None else 0),
            "cumulative_return": 0.0,
            "annualised_return": 0.0,
            "annualised_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "var": 0.0,
            "cvar": 0.0,
        }

    r = daily_returns.dropna().astype(float)
    n = int(len(r))

    # cumulative return = multiply (1 + each daily return) together, then subtract 1
    # basically compounding all the daily gains/losses
    cumulative = float((1 + r).prod() - 1)

    # annualised return — scale the cumulative return to one year
    # formula: (1 + total_return)^(252/n) - 1, using 252 trading days per year
    annualised_return = float((1 + cumulative) ** (252 / n) - 1)

    # annualised volatility = std dev of daily returns * sqrt(252)
    # the sqrt(252) part scales it from daily to yearly — not sure why its square root but it works
    annualised_vol = float(r.std(ddof=1) * np.sqrt(252))

    # sharpe = (return - risk free) / std dev, basically return per unit of risk
    # im using risk free = 0 for now which is a simplification but fine for a student project
    sharpe = float((r.mean() / r.std(ddof=1)) * np.sqrt(252)) if r.std(ddof=1) > 0 else 0.0

    # max drawdown — how far did the portfolio fall from its peak at worst
    # equity curve is cumulative product of (1 + return), peak is running max
    equity = (1 + r).cumprod()
    peak = equity.cummax()
    drawdown = (equity / peak) - 1
    max_dd = float(drawdown.min())

    # VaR = value at risk — the worst return at a given confidence level
    # e.g. 95% VaR means 95% of days were better than this number
    # CVaR = average of returns below VaR (expected shortfall)
    # TODO: clean this up, probably should handle edge cases better
    alpha = 1 - confidence
    var_level = float(r.quantile(alpha))          # e.g. 5th percentile
    cvar_level = float(r[r <= var_level].mean())  # expected shortfall

    return {
        "n_days": n,
        "cumulative_return": cumulative,
        "annualised_return": annualised_return,
        "annualised_volatility": annualised_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "var": var_level,
        "cvar": cvar_level,
        "confidence": confidence
    }
