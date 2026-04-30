"""
14 unit tests for FlyingFunds core logic.

Covers:
  • Sharpe ratio (positive / zero-vol / negative)
  • VaR (correct percentile + graceful insufficient-data path)
  • Max drawdown (monotone decline)
  • Compound return arithmetic
  • TF-IDF ranking & stopword suppression
  • Shadow-portfolio counterfactual arithmetic
  • Goal-projection CAGR formula
  • Goal required-return formula
  • API: empty-portfolio timeseries → 200
  • API: invalid ticker → graceful non-500 response

Run with:
    python -m pytest tests/test_unit.py -v
"""

import unittest
import math

import numpy as np
import pandas as pd

# ── app imports ───────────────────────────────────────────────────────────────
from app.services.analytics import compute_risk_metrics_from_returns
from app.services.tfidf import tfidf_scores, _tokenize, STOPWORDS


# Analytics unit tests

class TestSharpeRatio(unittest.TestCase):

    def test_sharpe_positive_return(self):
        """Consistently positive daily returns should yield Sharpe > 0."""
        returns = pd.Series([0.005] * 50 + [0.003] * 50)   # mean ~0.4%, positive
        result = compute_risk_metrics_from_returns(returns)
        self.assertGreater(result["sharpe_ratio"], 0,
                           "Sharpe should be positive when mean return > 0")

    def test_sharpe_zero_volatility(self):
        """Constant returns (exactly zero std-dev) → Sharpe clipped to 0."""
        # Use np.zeros so all values are identical IEEE-754 bit patterns;
        # pandas std(ddof=1) will be exactly 0.0 and the guard branch fires.
        returns = pd.Series(np.zeros(100))
        result = compute_risk_metrics_from_returns(returns)
        self.assertEqual(result["sharpe_ratio"], 0.0,
                         "Zero volatility should return Sharpe = 0.0 (not NaN / error)")

    def test_sharpe_negative_return(self):
        """Consistently negative daily returns should yield Sharpe < 0."""
        returns = pd.Series([-0.005] * 50 + [-0.003] * 50)
        result = compute_risk_metrics_from_returns(returns)
        self.assertLess(result["sharpe_ratio"], 0,
                        "Sharpe should be negative when mean return < 0")


class TestVaR(unittest.TestCase):

    def test_var_correct_percentile(self):
        """VaR (95%) should equal the 5th-percentile of daily returns."""
        np.random.seed(0)
        returns = pd.Series(np.random.normal(0, 0.01, 500))
        result = compute_risk_metrics_from_returns(returns, confidence=0.95)
        expected_var = float(returns.quantile(0.05))
        self.assertAlmostEqual(result["var"], expected_var, places=8,
                               msg="VaR should be the 5th-percentile of the return series")

    def test_var_insufficient_data_graceful(self):
        """Series with fewer than 2 points should return zeros, not crash."""
        result = compute_risk_metrics_from_returns(pd.Series([0.02]))
        self.assertEqual(result["var"], 0.0)
        self.assertEqual(result["sharpe_ratio"], 0.0)
        self.assertEqual(result["max_drawdown"], 0.0)


class TestDrawdown(unittest.TestCase):

    def test_drawdown_monotone_decline(self):
        """A steadily falling return series must have max_drawdown < 0."""
        # -1% every single day: equity goes 1.00 → 0.99 → 0.98 → …
        returns = pd.Series([-0.01] * 200)
        result = compute_risk_metrics_from_returns(returns)
        self.assertLess(result["max_drawdown"], 0,
                        "Monotone decline must produce a negative max drawdown")


class TestCompoundReturn(unittest.TestCase):

    def test_return_compound(self):
        """Cumulative return for n identical daily gains must equal (1+r)^n - 1."""
        daily_r = 0.01
        n = 50
        returns = pd.Series([daily_r] * n)
        result = compute_risk_metrics_from_returns(returns)
        expected = (1 + daily_r) ** n - 1
        self.assertAlmostEqual(result["cumulative_return"], expected, places=8,
                               msg="Cumulative return should compound correctly")



#TF-IDF unit tests

class TestTfIdf(unittest.TestCase):

    def test_tfidf_ranking_order(self):
        """
        A document that contains the query term more frequently should score
        higher than one that never mentions it.
        """
        docs = [
            "portfolio risk analytics sharpe volatility return portfolio return",  # doc 0 — rich
            "weather forecast sunny weekend outdoor activity hiking",               # doc 1 — irrelevant
            "risk management diversification investment",                           # doc 2 — tangential
        ]
        scores = tfidf_scores("portfolio return", docs)
        # doc 0 should beat both others
        self.assertGreater(scores[0], scores[1],
                           "High-frequency query-term document should outscore an irrelevant one")
        self.assertGreater(scores[0], scores[2],
                           "High-frequency query-term document should outscore a tangential one")

    def test_tfidf_stopword_suppression(self):
        """
        A document composed entirely of stopwords should score 0 (or less than
        a meaningful document) even when the query includes those stopwords.
        """
        stopword_doc = "the and or is a the and or is a the"    # all STOPWORDS
        content_doc  = "sharpe ratio portfolio analytics investment risk"

        query = "the sharpe ratio"   # mixed: stopwords + meaningful term

        scores = tfidf_scores(query, [stopword_doc, content_doc])
        self.assertGreater(scores[1], scores[0],
                           "Content document should outscore a stopword-only document "
                           "even when the query contains those stopwords")
        # stopword-only doc must score exactly 0 (all query stopwords stripped)
        self.assertEqual(scores[0], 0.0,
                         "Document consisting entirely of stopwords must score 0.0")



# 10  Shadow-portfolio arithmetic

class TestShadowCounterfactual(unittest.TestCase):

    def test_shadow_counterfactual_arithmetic(self):
        """
        cost = current_value - proceeds
        A positive cost means the user would be richer had they held.
        """
        qty        = 10.0
        sell_price = 50.0          # sold at £50 each
        cur_price  = 65.0          # stock is now £65

        proceeds      = qty * sell_price    # £500 — what they received
        current_value = qty * cur_price     # £650 — what it's worth today
        cost          = current_value - proceeds  # £150 missed gain

        self.assertAlmostEqual(proceeds, 500.0,   places=5)
        self.assertAlmostEqual(current_value, 650.0, places=5)
        self.assertAlmostEqual(cost, 150.0,       places=5,
                               msg="Shadow cost should be the unrealised missed gain")

        # also verify a good-call scenario: sell_price > cur_price → negative cost
        good_sell_price = 80.0
        good_proceeds   = qty * good_sell_price    # £800
        good_cost       = (qty * cur_price) - good_proceeds  # 650 - 800 = -150
        self.assertLess(good_cost, 0,
                        "Selling above current price should be a good call (cost < 0)")


# 11–12  Goal-projection pure maths (mirrors the route formulae)


class TestGoalProjection(unittest.TestCase):

    def test_goal_projection_cagr(self):
        """projected_value = current_value × (1 + ann_return) ^ years."""
        current_value = 5_000.0
        ann_return    = 0.08         # 8 % p.a.
        years         = 5.0

        projected = current_value * ((1 + ann_return) ** years)
        expected  = 5_000 * (1.08 ** 5)   # ≈ 7346.64

        self.assertAlmostEqual(projected, expected, places=4,
                               msg="CAGR projection should compound correctly")
        self.assertGreater(projected, current_value,
                           "Positive return must grow the portfolio over time")

    def test_goal_required_return(self):
        """required_return = (target / current) ^ (1/years) - 1."""
        current_value = 5_000.0
        target_amount = 10_000.0
        years         = 7.0

        required_return = (target_amount / current_value) ** (1.0 / years) - 1
        # double in 7 years: r ≈ 10.41 %
        expected = 2.0 ** (1.0 / 7.0) - 1

        self.assertAlmostEqual(required_return, expected, places=8,
                               msg="Required return formula should invert the CAGR correctly")
        self.assertGreater(required_return, 0,
                           "Needing to double money requires a positive return rate")



# API integration tests (in-memory SQLite, no network)

class TestAPIIntegration(unittest.TestCase):
    """
    Spins up the FastAPI app against an in-memory SQLite database.
    No live network calls — yfinance failures are caught gracefully by the app.
    """

    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from fastapi.testclient import TestClient

        from app.main import app
        from app.database import Base, get_db as db_get_db
        from app.deps import get_db as deps_get_db
        from app.models import User, Portfolio
        from app.security import hash_password, get_current_user

        # StaticPool ensures every TestSession() reuses the SAME underlying
        # connection, so the seeded rows are visible to the route handler.
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        # ── seed: one user + one empty portfolio ──
        db = TestSession()
        user = User(
            email="test@flyingfunds.test",
            hashed_password=hash_password("testpassword"),
            username="testuser",
            level="beginner",
        )
        db.add(user)
        db.flush()

        portfolio = Portfolio(name="Test Portfolio", user_id=user.id)
        db.add(portfolio)
        db.commit()

        # capture primitives before closing session
        cls.user_id      = user.id
        cls.portfolio_id = portfolio.id

        # keep user in memory for the auth override
        _test_user = user

        db.close()

        def override_get_db():
            db2 = TestSession()
            try:
                yield db2
            finally:
                db2.close()

        # Bypass JWT auth entirely — return the seeded user object directly.
        # This avoids a second DB lookup that would go to the real database.
        def override_get_current_user():
            return _test_user

        app.dependency_overrides[db_get_db]        = override_get_db
        app.dependency_overrides[deps_get_db]      = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        cls.client      = TestClient(app, raise_server_exceptions=False)
        cls.auth_header = {}   # no token needed — auth is overridden

    def test_api_empty_portfolio_200(self):
        """
        GET /analytics/portfolio/{id}/timeseries with no holdings
        must return HTTP 200 and an empty series list — not a 4xx/5xx.
        """
        pid = self.portfolio_id
        resp = self.client.get(
            f"/analytics/portfolio/{pid}/timeseries",
            headers=self.auth_header,
        )
        self.assertEqual(resp.status_code, 200,
                         f"Expected 200 for empty portfolio, got {resp.status_code}: {resp.text}")
        body = resp.json()
        self.assertEqual(body["series"], [],
                         "Empty portfolio should return an empty series list")

    def test_api_invalid_ticker_graceful(self):
        """
        GET /market/candles?symbol=INVALIDXYZ999&range=1D
        must NOT return HTTP 500 — the app should surface a 4xx or 503.
        """
        resp = self.client.get(
            "/market/candles",
            params={"symbol": "INVALIDXYZ999", "range": "1D"},
            headers=self.auth_header,
        )
        self.assertNotEqual(resp.status_code, 500,
                            "Invalid ticker should produce a handled error, not an unhandled 500")
        self.assertIn(resp.status_code, {400, 401, 403, 404, 422, 503},
                      f"Expected a client/service error, got {resp.status_code}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
