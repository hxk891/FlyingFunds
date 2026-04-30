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

_cache: dict = {"articles": [], "ts": 0}
_cache_lock = Lock()
CACHE_TTL = 15 * 60  # 15 mins


@router.get("/api/news")
def api_news():
    now = time.time()
    with _cache_lock:
        if _cache["articles"] and (now - _cache["ts"]) < CACHE_TTL:
            return {"articles": _cache["articles"], "cached": True}

    articles = _fetch_all_feeds()

    with _cache_lock:
        _cache["articles"] = articles
        _cache["ts"] = now

    return {"articles": articles, "cached": False}


FEEDS = [
    {"name": "Yahoo Finance",  "url": "https://finance.yahoo.com/rss/topstories",                        "category": "markets"},
    {"name": "CNBC Markets",   "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",            "category": "markets"},
    {"name": "CNBC Economy",   "url": "https://www.cnbc.com/id/20910361/device/rss/rss.html",            "category": "economy"},
    {"name": "CNBC Invest",    "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",            "category": "investing"},
    {"name": "MarketW",        "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines","category": "markets"},
    {"name": "Investopedia",   "url": "https://www.investopedia.com/feeds/news.aspx",                    "category": "investing"},
]


def _fetch_all_feeds() -> list:
    all_articles = []
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as ex:
        futures = {ex.submit(_parse_feed, f): f for f in FEEDS}
        for fut in as_completed(futures):
            all_articles.extend(fut.result())

    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] and a["url"] not in seen and a["title"]:
            seen.add(a["url"])
            unique.append(a)

    unique.sort(key=lambda x: x["published_ts"], reverse=True)
    return unique[:40]


@router.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    return templates.TemplateResponse("news.html", {"request": request})


def _parse_feed(feed_meta: dict) -> list:
    try:
        parsed = feedparser.parse(feed_meta["url"])
        articles = []
        for entry in parsed.entries[:8]:
            pub_ts = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_ts = time.mktime(entry.published_parsed)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                pub_ts = time.mktime(entry.updated_parsed)

            pub_str = (
                datetime.fromtimestamp(pub_ts, tz=timezone.utc).strftime("%d %b %Y")
                if pub_ts else ""
            )

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

            desc = ""
            if hasattr(entry, "summary"):
                import re
                desc = re.sub(r"<[^>]+>", "", entry.summary or "").strip()
                if len(desc) > 180:
                    desc = desc[:177] + "…"

            articles.append({
                "source":       feed_meta["name"],
                "category":     feed_meta["category"],
                "title":        entry.get("title", "").strip(),
                "description":  desc,
                "url":          entry.get("link", ""),
                "image":        image,
                "published":    pub_str,
                "published_ts": pub_ts or 0,
            })
        return articles
    except Exception:
        return []
