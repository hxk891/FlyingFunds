from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, UniqueConstraint, BigInteger, Boolean
from sqlalchemy.orm import relationship

from datetime import datetime

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    username = Column(String, unique=True, nullable=True)
    avatar = Column(String, nullable=True)
    user_type = Column(String, nullable=True)
    level = Column(String, nullable=True)
    markets = Column(String, nullable=True)

    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(String, default="false")

    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)

    cash_balance = Column(Float, default=10000.0)

    # Learn progress — JSON array of topic IDs e.g. '["mpt","capm"]'
    read_topics = Column(String, default="[]", nullable=True)

    portfolios = relationship("Portfolio", back_populates="owner", cascade="all, delete-orphan")
    watchlist = relationship("WatchlistItem", back_populates="owner", cascade="all, delete-orphan")


class Dividend(Base):
    __tablename__ = "dividends"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)

    symbol = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow)


class MarketTick(Base):
    __tablename__ = "market_ticks"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    price = Column(Float, nullable=False)
    ts = Column(BigInteger, index=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tick_symbol_ts", "symbol", "ts"),
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)

    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    category   = Column(String, default="General", nullable=True)
    sort_order = Column(Integer, default=0, nullable=True)

    owner = relationship("User", back_populates="portfolios")
    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol       = Column(String, nullable=False)
    notes        = Column(String, nullable=True)
    target_price = Column(Float, nullable=True)
    added_at     = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="watchlist")

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),
    )


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)

    symbol = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    avg_buy_price = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="holdings")


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    date = Column(String, index=True, nullable=False)
    close = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_symbol_date"),
    )
