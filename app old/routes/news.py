# app/routes/news.py
"""
News feed aggregator using free RSS sources — no API key required.
Multiple feeds fetched in parallel, deduplicated, cached 15 minutes.
"""
import time
import feedparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["news"])

# ── RSS feed sources (all free, no key needed) ─────────────────────────────────
FEEDS = [
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/rss/topstories",
        "category": "markets",
    },
    {
        "name": "CNBC Markets",
        "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "category": "markets",
    },
    {
        "name": "CNBC Economy",
        "url": "https://www.cnbc.com/id/20910361/device/rss/rss.html",
        "category": "economy",
    },
    {
        "name": "CNBC Investing",
        "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
        "category": "investing",
    },
    {
        "name": "MarketWatch",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
        "category": "markets",
    },
    {
        "name": "Investopedia",
        "url": "https://www.investopedia.com/feeds/news.aspx",
        "category": "investing",
    },
]

# ── Server-side cache (15 min TTL) ─────────────────────────────────────────────
_cache: dict = {"articles": [], "ts": 0}
_cache_lock = Lock()
CACHE_TTL = 15 * 60


def _parse_feed(feed_meta: dict) -> list:
    """Parse a single RSS feed, return list of article dicts."""
    try:
        parsed = feedparser.parse(feed_meta["url"])
        articles = []
        for entry in parsed.entries[:8]:
            # Published timestamp
            pub_ts = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_ts = time.mktime(entry.published_parsed)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_ts = time.mktime(entry.updated_parsed)

            pub_str = (
                datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime("%d %b %Y")
                if pub_ts else ""
            )

            # Image: try media_thumbnail, media_content, enclosures
            image = None
            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                image = entry.media_thumbnail[0].get("url")
            elif hasattr(entry, "media_content") and entry.media_content:
                image = entry.media_content[0].get("url")
            elif hasattr(entry, "enclosures") and entry.enclosures:
                for enc in entry.enclosures:
                    if enc.get("type", "").startswith("image"):
                        image = enc.get("url")
                        break

            # Description — strip HTML tags simply
            desc = ""
            if hasattr(entry, "summary"):
                import re
                desc = re.sub(r"<[^>]+>", "", entry.summary or "").strip()
                if len(desc) > 180:
                    desc = desc[:177] + "…"

            articles.append({
                "source": feed_meta["name"],
                "category": feed_meta["category"],
                "title": entry.get("title", "").strip(),
                "description": desc,
                "url": entry.get("link", ""),
                "image": image,
                "published": pub_str,
                "published_ts": pub_ts or 0,
            })
        return articles
    except Exception:
        return []


def _fetch_all_feeds() -> list:
    """Fetch all feeds in parallel, deduplicate by URL, sort by recency."""
    all_articles = []
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as ex:
        futures = {ex.submit(_parse_feed, f): f for f in FEEDS}
        for fut in as_completed(futures):
            all_articles.extend(fut.result())

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] and a["url"] not in seen and a["title"]:
            seen.add(a["url"])
            unique.append(a)

    # Sort newest first
    unique.sort(key=lambda x: x["published_ts"], reverse=True)
    return unique[:40]  # cap at 40 articles


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    """Serve the news shell — articles are loaded client-side via /api/news."""
    return templates.TemplateResponse("news.html", {"request": request})


@router.get("/api/news")
def api_news():
    """
    JSON endpoint — returns aggregated articles from all RSS feeds.
    Cached 15 min server-side.
    """
    now = time.time()
    with _cache_lock:
        if _cache["articles"] and (now - _cache["ts"]) < CACHE_TTL:
            return {"articles": _cache["articles"], "cached": True}

    articles = _fetch_all_feeds()

    with _cache_lock:
        _cache["articles"] = articles
        _cache["ts"] = now

    return {"articles": articles, "cached": False}
