from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["pages"])

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@router.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@router.get("/contact", response_class=HTMLResponse)
def contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/dashboard/{portfolio_id}", response_class=HTMLResponse)
def dashboard_portfolio(request: Request, portfolio_id: int):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/portfolios-ui", response_class=HTMLResponse)
def portfolios_ui(request: Request):
    return templates.TemplateResponse("portfolios.html", {"request": request})

@router.get("/market", response_class=HTMLResponse)
def market_page(request: Request):
    return templates.TemplateResponse("market.html", {"request": request})

@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request):
    return templates.TemplateResponse("watchlist.html", {"request": request})

@router.get("/invest", response_class=HTMLResponse)
def invest_page(request: Request):
    return templates.TemplateResponse("invest.html", {"request": request})

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@router.get("/diary", response_class=HTMLResponse)
def diary_page(request: Request):
    return templates.TemplateResponse("diary.html", {"request": request})

@router.get("/learn", response_class=HTMLResponse)
def learn_page(request: Request):
    return templates.TemplateResponse("learn.html", {"request": request})

@router.get("/frontier", response_class=HTMLResponse)
def frontier_page(request: Request):
    return templates.TemplateResponse("frontier.html", {"request": request})

@router.get("/fx", response_class=HTMLResponse)
def fx_page(request: Request):
    return templates.TemplateResponse("fx.html", {"request": request})
 