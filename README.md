# FlyingFunds

A full-stack paper trading and portfolio analytics web app. Users get a virtual £10,000 to simulate buying and selling stocks, track portfolio performance, and learn about risk metrics (Sharpe ratio, VaR, CVaR, max drawdown) through an adaptive educational interface.

---

## Requirements

- Python 3.9 or higher
- pip

---

## Setup

### 1. Open Terminal and go to the project folder

```bash
cd ~/flyingfunds
```

Adjust the path if your folder is somewhere else (e.g. `cd ~/Desktop/flyingfunds`).

---

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` appear at the start of your terminal prompt.

---

### 3. Install dependencies

Only needed once per environment:

```bash
pip install -r requirements.txt
```

---

### 4. Create a `.env` file

Create a file called `.env` in the root of the project folder and add:

```
SECRET_KEY=any-long-random-string-here
```

You can optionally add a Finnhub API key for live candle chart data it is Free. The app falls back to Yahoo Finance if this is not set:

```
FINNHUB_API_KEY=your-key-here
```

---

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

Expected output:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Leave this terminal open while using the app.

---

### 6. Open the app in your browser

**Visual UI (main app):**
```
http://127.0.0.1:8000
```

**Interactive API docs (Swagger):**
```
http://127.0.0.1:8000/docs
```

---

## First-Time Setup (fresh database)

The database is created automatically on first run. Follow these steps to create your first user and portfolio via the Swagger docs at `/docs`:

### A) Register a user

`POST /users/register`

```json
{
  "email": "test@example.com",
  "password": "Password123!"
}
```

### B) Log in

`POST /users/login`

Copy the `access_token` from the response.

### C) Authorise in Swagger

Click the **Authorize** button at the top of the `/docs` page and paste:

```
Bearer <your_access_token>
```

### D) Create a portfolio

`POST /portfolios`

```json
{
  "name": "My First Portfolio"
}
```

### E) Place a trade

`POST /trading/buy`

```json
{
  "portfolio_id": 1,
  "symbol": "AAPL",
  "quantity": 10,
  "price": 180.00
}
```

---


## Resetting the Database (development only)

This deletes all data and starts fresh:

```bash
rm flyingfunds.db
uvicorn app.main:app --reload
```

---

## Pages

| URL | Description |
|---|---|
| `/` | Home / landing page |
| `/signup` | Register a new account |
| `/login` | Log in |
| `/dashboard` | Portfolio overview |
| `/portfolios` | Manage portfolios |
| `/invest` | Stock chart and buy/sell |
| `/market` | Market data |
| `/watchlist` | Watchlist |
| `/news` | Financial news feed |
| `/learn` | Educational content |
| `/fx` | Currency converter |
| `/diary` | Investment diary |
| `/frontier` | Efficient frontier chart |
| `/settings` | Account settings |

---

## Database Schema

The app uses SQLite with 8 tables. The database file (`flyingfunds.db`) is created automatically — no SQL setup needed.

---

### `users`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `email` | TEXT | Unique login email |
| `hashed_password` | TEXT | bcrypt hashed password |
| `username` | TEXT | Display name |
| `avatar` | TEXT | Emoji avatar |
| `level` | TEXT | `beginner` / `intermediate` / `advanced` |
| `cash_balance` | REAL | Virtual cash (default £10,000) |
| `totp_secret` | TEXT | 2FA secret key |
| `totp_enabled` | TEXT | Whether 2FA is on |
| `reset_token` | TEXT | Password reset token |
| `reset_token_expiry` | DATETIME | Token expiry |
| `read_topics` | TEXT | JSON array of completed learn topics |
| `created_at` | DATETIME | Registration date |

---

### `portfolios`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `user_id` | INTEGER | FK → users.id |
| `name` | TEXT | Portfolio name |
| `category` | TEXT | User-defined category |
| `sort_order` | INTEGER | Display order |
| `created_at` | DATETIME | Creation date |

---

### `holdings`
Current open positions — updated automatically when trades are placed.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `portfolio_id` | INTEGER | FK → portfolios.id |
| `symbol` | TEXT | Ticker (e.g. `AAPL`) |
| `quantity` | REAL | Shares held |
| `avg_buy_price` | REAL | Volume-weighted average purchase price |
| `created_at` | DATETIME | First purchase date |

---

### `trades`
Immutable log of every buy and sell order.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `portfolio_id` | INTEGER | FK → portfolios.id |
| `symbol` | TEXT | Ticker |
| `side` | TEXT | `"buy"` or `"sell"` |
| `quantity` | REAL | Shares traded |
| `price` | REAL | Price per share at execution |
| `ts` | DATETIME | Trade timestamp |

---

### `prices`
User-uploaded historical close prices for offline analytics.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `symbol` | TEXT | Ticker |
| `date` | TEXT | Date string (`YYYY-MM-DD`) |
| `close` | REAL | Closing price |

Unique constraint on `(symbol, date)`.

---

### `watchlist`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `user_id` | INTEGER | FK → users.id |
| `symbol` | TEXT | Ticker being watched |
| `notes` | TEXT | Optional notes |
| `target_price` | REAL | Optional price alert |
| `added_at` | DATETIME | Date added |

Unique constraint on `(user_id, symbol)`.

---

### `market_ticks`
Cached real-time price ticks.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `symbol` | TEXT | Ticker |
| `price` | REAL | Tick price |
| `ts` | BIGINT | Unix timestamp (ms) |
| `created_at` | DATETIME | Row insert time |

---

### `dividends`
| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `portfolio_id` | INTEGER | FK → portfolios.id |
| `symbol` | TEXT | Ticker that paid the dividend |
| `amount` | REAL | Dividend amount (£) |
| `ts` | DATETIME | Payment date |

---

## Project Structure

```
flyingfunds/
├── app/
│   ├── main.py          # App entry point, router registration
│   ├── database.py      # Database connection
│   ├── models.py        # All 8 database table definitions
│   ├── security.py      # JWT auth, password hashing
│   ├── deps.py          # Shared dependencies (get_db)
│   ├── routes/          # All API and page routes
│   └── services/        # Analytics and TF-IDF logic
├── tests/
│   └── test_unit.py     # 14 unit and integration tests
├── requirements.txt
├── .env                 # Create this yourself (see step 4)
└── flyingfunds.db       # Auto-created SQLite database
```
