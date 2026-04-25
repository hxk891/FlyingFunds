from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Portfolio, Holding, User
from ..security import get_current_user

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str


class HoldingCreate(BaseModel):
    symbol: str
    quantity: float
    avg_buy_price: float


@router.post("/", status_code=201)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = Portfolio(name=payload.name, user_id=current_user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name}


@router.get("/")
def list_portfolios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == current_user.id).all()
    return [{"id": p.id, "name": p.name} for p in portfolios]


@router.post("/{portfolio_id}/holdings", status_code=201)
def add_holding(
    portfolio_id: int,
    payload: HoldingCreate,
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

    h = Holding(
        portfolio_id=portfolio.id,
        symbol=payload.symbol.upper(),
        quantity=payload.quantity,
        avg_buy_price=payload.avg_buy_price,
    )
    db.add(h)
    db.commit()
    db.refresh(h)

    return {
        "id": h.id,
        "symbol": h.symbol,
        "quantity": h.quantity,
        "avg_buy_price": h.avg_buy_price,
    }


@router.get("/{portfolio_id}")
def get_portfolio(
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

    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "holdings": [
            {
                "id": h.id,
                "symbol": h.symbol,
                "quantity": h.quantity,
                "avg_buy_price": h.avg_buy_price,
            }
            for h in holdings
        ],
    }
