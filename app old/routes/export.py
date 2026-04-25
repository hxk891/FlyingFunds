import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app import models

router = APIRouter(prefix="/export", tags=["export"])

def _owned(db: Session, user_id: int, portfolio_id: int):
    p = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id, models.Portfolio.user_id == user_id).first()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    return p

@router.get("/portfolio/{portfolio_id}.csv")
def export_csv(portfolio_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = _owned(db, user.id, portfolio_id)
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
def export_pdf(portfolio_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Minimal PDF without adding new deps.
    # If reportlab is installed server-side, you can use it. Otherwise, keep CSV only.
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        raise HTTPException(500, "PDF export not configured (install reportlab)")

    p = _owned(db, user.id, portfolio_id)
    holdings = db.query(models.Holding).filter(models.Holding.portfolio_id == portfolio_id).all()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, f"FlyingFunds — Portfolio Export")
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