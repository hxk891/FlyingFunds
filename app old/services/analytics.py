from typing import Dict, List
import pandas as pd
import numpy as np

def compute_basic_portfolio_analytics(holdings: List[dict]) -> Dict:
    """
    holdings: list of dicts containing symbol, quantity, avg_buy_price
    """
    rows = []
    total_invested = 0.0

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

    # Cumulative return
    cumulative = float((1 + r).prod() - 1)

    # Annualised return (geometric)
    annualised_return = float((1 + cumulative) ** (252 / n) - 1)

    # Annualised volatility
    annualised_vol = float(r.std(ddof=1) * np.sqrt(252))

    # Sharpe (risk-free = 0 for now)
    sharpe = float((r.mean() / r.std(ddof=1)) * np.sqrt(252)) if r.std(ddof=1) > 0 else 0.0

    # Max drawdown from equity curve
    equity = (1 + r).cumprod()
    peak = equity.cummax()
    drawdown = (equity / peak) - 1
    max_dd = float(drawdown.min())

    # Historical VaR / CVaR (losses are negative returns)
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

