import io
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import os

from app.database import get_db
from app import models

router = APIRouter(prefix="/export", tags=["export"])

SECRET_KEY = os.getenv("SECRET_KEY", "flyingfunds-dev-secret-change-me")
ALGORITHM  = "HS256"

#Validate a raw JWT and return the User, or raise 401 Error
def user_frm_token(token: str, db: Session):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user:
        raise HTTPException(401, "User not found")
    return user

def _get_export_user(request: Request, token: str = Query(None), db: Session = Depends(get_db)):
    """Accept token from ?token= query param OR Authorization header."""
    raw = token
    if not raw:
        auth = request.headers.get("Authorization", "")
        raw = auth.strip() or None
    # get rid off "Bearer " prefix however it arrived
    if raw:
        raw = raw.removeprefix("Bearer ").strip()
    if not raw:
        raise HTTPException(401, "Not authenticated")
    return user_frm_token(raw, db)

def owned(db: Session, user_id: int, portfolio_id: int):
    p = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id, models.Portfolio.user_id == user_id).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    return p

@router.get("/portfolio/{portfolio_id}.csv")
def export_csv(portfolio_id: int, db: Session = Depends(get_db), user=Depends(_get_export_user)):
    p = owned(db, user.id, portfolio_id)
    holdings = db.query(models.Holding).filter(models.Holding.portfolio_id == portfolio_id).all()

    out = io.StringIO()
    out.write("portfolio_id,portfolio_name,symbol,quantity,avg_buy_price\n")
    for h in holdings:
      out.write(f"{p.id},{p.name},{h.symbol},{h.quantity},{h.avg_buy_price}\n")

    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="portfolio_{portfolio_id}.csv"'}
    )

@router.get("/portfolio/{portfolio_id}.pdf")
def export_pdf(portfolio_id: int, db: Session = Depends(get_db), user=Depends(_get_export_user)):
    # Minimal PDF
    # If reportlab is installed you can use it. Otherwise, keep CSV only.
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        raise HTTPException(500, "PDF export not configured (install reportlab)")

    p = owned(db, user.id, portfolio_id)
    holdings = db.query(models.Holding).filter(models.Holding.portfolio_id == portfolio_id).all()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, f"FlyingFunds: Portfolio Export")
    y -= 25
    c.setFont("Helvetica", 12)
    c.drawString(60, y, f"Portfolio: {p.name} (ID {p.id})")
    y -= 30

    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "Symbol")
    c.drawString(150, y, "Qty")
    c.drawString(240, y, "Avg Buy")
    y -= 15
    c.setFont("Helvetica", 10)

    for h in holdings:
        if y < 60:
            c.showPage()
            y = height - 60
        c.drawString(60, y, h.symbol)
        c.drawString(150, y, f"{h.quantity:.4f}")
        c.drawString(240, y, f"{h.avg_buy_price:.2f}")
        y -= 14

    c.showPage()
    c.save()
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="portfolio_{portfolio_id}.pdf"'}
    )