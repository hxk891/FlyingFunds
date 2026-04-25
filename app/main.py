from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .database import Base, engine
from . import models
from dotenv import load_dotenv
load_dotenv() 
from .routes.users import router as users_router
from .routes.portfolios import router as portfolios_router
from .routes.analytics import router as analytics_router
from .routes.pages import router as pages_router
from .routes.prices import router as prices_router
from .routes.news import router as news_router
from .routes.market import router as market_router
from .routes.trading import router as trading_router
from .routes.watchlist import router as watchlist_router
from .routes.chat import router as chat_router
from .routes.fx import router as fx_router
from .routes.export import router as export_router
from .routes.learn import router as learn_router

import sqlite3


def run_migrations():
    USER_COLUMNS = [
        ("username",            "TEXT"),
        ("avatar",              "TEXT DEFAULT '👤'"),
        ("user_type",           "TEXT"),
        ("level",               "TEXT"),
        ("markets",             "TEXT DEFAULT '[]'"),
        ("totp_secret",         "TEXT"),
        ("totp_enabled",        "INTEGER DEFAULT 0"),
        ("reset_token",         "TEXT"),
        ("reset_token_expiry",  "TEXT"),
        ("cash_balance",        "REAL DEFAULT 10000.0"),
        ("read_topics",         "TEXT DEFAULT '[]'"),
    ]

    PORTFOLIO_COLUMNS = [
        ("category",   "TEXT DEFAULT 'General'"),
        ("sort_order", "INTEGER DEFAULT 0"),
    ]

    db_path = engine.url.database

    try:
        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()

        cur.execute("PRAGMA table_info(users)")
        existing_users = {row[1] for row in cur.fetchall()}
        for col, typ in USER_COLUMNS:
            if col not in existing_users:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
                print(f"[migration] users: added column: {col}")

        cur.execute("PRAGMA table_info(portfolios)")
        existing_portfolios = {row[1] for row in cur.fetchall()}
        for col, typ in PORTFOLIO_COLUMNS:
            if col not in existing_portfolios:
                cur.execute(f"ALTER TABLE portfolios ADD COLUMN {col} {typ}")
                print(f"[migration] portfolios: added column: {col}")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[migration] warning: {e}")


Base.metadata.create_all(bind=engine)
run_migrations()  # TODO: move this at some point

app = FastAPI(
    title="FlyingFunds",
    version="0.1.0",
    description="Investment portfolio management backend."
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(users_router)
app.include_router(portfolios_router)
app.include_router(analytics_router)
app.include_router(pages_router)
app.include_router(prices_router)
app.include_router(news_router)
app.include_router(market_router)
app.include_router(trading_router)
app.include_router(watchlist_router)
app.include_router(chat_router)
app.include_router(fx_router)
app.include_router(export_router)
app.include_router(learn_router)


@app.get("/", operation_id="api_root")
def api_root():
    return {"app": "FlyingFunds", "status": "running"}

@app.get("/health")
def health_check():
    return {"ok": True}