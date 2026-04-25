from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

from ..deps import get_db
from ..models import Price, User
from ..security import get_current_user

router = APIRouter(prefix="/prices", tags=["prices"])


@router.post("/upload")
async def upload_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a CSV with columns: date,symbol,close
    date should be parseable (e.g. 2024-01-05)
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()

    try:
        df = pd.read_csv(pd.io.common.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {e}")

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    required = {"date", "symbol", "close"}
    if not required.issubset(set(df.columns)):
        raise HTTPException(
            status_code=400,
            detail="CSV must contain columns: date, symbol, close",
        )

    # Clean
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = df.dropna(subset=["date", "symbol", "close"])

    inserted = 0
    updated = 0
    skipped = 0

    # For small FYP datasets, row-by-row is fine and easy to understand
    for _, row in df.iterrows():
        symbol = row["symbol"]
        date = row["date"]
        close = float(row["close"])

        existing = (
            db.query(Price)
            .filter(Price.symbol == symbol, Price.date == date)
            .first()
        )

        if existing:
            # update close
            existing.close = close
            updated += 1
        else:
            db.add(Price(symbol=symbol, date=date, close=close))
            inserted += 1

    db.commit()

    return {
        "filename": file.filename,
        "rows_processed": int(len(df)),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped
    }
