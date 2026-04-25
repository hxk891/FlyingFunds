from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from sqlalchemy.orm import Session
import pandas as pd
import httpx

from ..deps import get_db
from ..models import Price, User
from ..security import get_current_user

router = APIRouter(prefix="/prices", tags=["prices"])



#yahoo finance symbol search [{symbol, name, exchange, type}]
@router.get("/search")
def searchSymbols(q: str = Query(..., min_length=1)):
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {
        "q": q,
        "quotesCount": 8,
        "newsCount": 0,
        "enableFuzzyQuery": "false",
        "enableCb": "false",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        quotes = data.get("quotes", [])
        results = []
        for item in quotes:
            symbol = item.get("symbol", "")
            name   = item.get("longname") or item.get("shortname") or ""
            exch   = item.get("exchDisp") or item.get("exchange") or ""
            qtype  = item.get("quoteType", "")
            if symbol:
                results.append({"symbol": symbol, "name": name, "exchange": exch, "type": qtype})
        return results
    except Exception:
        return []


#  upload a CSV with columns 
@router.post("/upload")
async def upload_prices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = await file.read()

    try:
        df = pd.read_csv(pd.io.common.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {e}")

    # normalise column names
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

    # datasets,
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
