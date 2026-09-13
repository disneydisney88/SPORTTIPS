# -*- coding: utf-8 -*-
"""Free tip sources: Google News RSS + DuckDuckGo HTML search.

Every tip row keeps its source (publisher) and link so attribution is always shown.
No API keys, no paid services.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlencode

import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (SPORTTIPS free aggregator)"}

NEWS_QUERIES = [
    "賽馬 貼士",
    "香港賽馬 心水",
    "馬會 貼士",
    "沙田 貼士",
    "跑馬地 貼士",
    "Hong Kong horse racing tips",
]
WEB_QUERIES = [
    "香港賽馬 貼士 今日",
    "HKJC racing tips today",
]

TIPS_COLUMNS = [
    "fetched_at", "race_date", "race_no", "horse_no", "horse_name",
    "source", "tipster", "title", "url", "kind", "note",
]


# ---------------------------------------------------------------- parsing --
def parse_race_no(title: str) -> int | None:
    m = re.search(r"第\s*(\d{1,2})\s*場", title)
    if m:
        v = int(m.group(1))
        return v if 1 <= v <= 12 else None
    m = re.search(r"(?<!\d)(\d{1,2})\s*場", title)
    if m:
        v = int(m.group(1))
        return v if 1 <= v <= 12 else None
    return None


def parse_horses(title: str) -> list[int]:
    """Extract horse saddlecloth numbers (1-14) mentioned in a title.

    Heuristic: standalone 1-2 digit numbers, after stripping dates
    (12/9), race numbers (第4場 / 3場 / Race 5), times and percentages.
    """
    cleaned = re.sub(r"第\s*\d{1,2}\s*場", " ", title)
    cleaned = re.sub(r"(?<!\d)\d{1,2}\s*場", " ", cleaned)
    cleaned = re.sub(r"(?i)\brace\s*no?\.?\s*\d{1,2}", " ", cleaned)
    cleaned = re.sub(r"(?<!\d)\d{1,2}\s*/\s*\d{1,2}(?!\d)", " ", cleaned)
    out: list[int] = []
    for m in re.finditer(r"(?<![\d.])(\d{1,2})(?![\d場月日時分秒歲%％/:.．])", cleaned):
        v = int(m.group(1))
        if 1 <= v <= 14:
            out.append(v)
    # de-dup, keep order
    return list(dict.fromkeys(out))


def parse_day_month(title: str, year: int) -> dt.date | None:
    m = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", title)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        try:
            return dt.date(year, mo, d)
        except ValueError:
            return None
    return None


def parse_quoted_names(text: str) -> list[str]:
    """HK racing media quote horse names like 「金勝名駒」."""
    out = []
    for m in re.finditer(r"[「『]([^「」『』]{2,10})[」』]", text):
        name = m.group(1).strip()
        if name and name not in out:
            out.append(name)
    return out


# ---------------------------------------------------------------- sources --
def fetch_google_news(query: str, days: int = 3, hl: str = "zh-HK") -> list[dict]:
    params = {
        "q": query,
        "hl": hl,
        "gl": "HK",
        "ceid": "HK:zh-Hant" if hl.startswith("zh") else "HK:en",
    }
    url = f"https://news.google.com/rss/search?{urlencode(params)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return []

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    items: list[dict] = []
    for item in root.iterfind(".//item"):
        title = unescape(item.findtext("title") or "")
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        src_el = item.find("source")
        source = unescape(src_el.text) if src_el is not None and src_el.text else "Google News"
        try:
            published = parsedate_to_datetime(pub).replace(tzinfo=None) if pub else None
        except (TypeError, ValueError):
            published = None
        items.append({"title": title, "url": link, "source": source, "published": published})
    # filter by age
    kept = []
    for it in items:
        if it["published"] and it["published"] < cutoff.replace(tzinfo=None):
            continue
        kept.append(it)
    return kept


def fetch_ddg(query: str, n: int = 10) -> list[dict]:
    """DuckDuckGo HTML results (best effort)."""
    try:
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=20,
        )
        if r.status_code != 200:
            return []
        html = r.text
    except requests.RequestException:
        return []
    out: list[dict] = []
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S
    ):
        url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        out.append({"title": unescape(title).strip(), "url": url, "source": "DuckDuckGo", "published": None})
        if len(out) >= n:
            break
    return out


def fetch_stheadline(max_articles: int = 10, vocab: set[str] | None = None) -> list[dict]:
    """星島頭條「馬經」專欄 via their public RSS (tipster columns like 亨利拆局/Dickson心水)."""
    try:
        r = requests.get("https://www.stheadline.com/rss", headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return []

    now = dt.datetime.now()
    kw = ("貼士", "心水", "拆局", "拆解", "馬經", "評馬", "賽馬", "馬匹", "騎師", "練馬師")
    articles = []
    for item in root.iterfind(".//item"):
        title = unescape(item.findtext("title") or "").strip()
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        if "/racing-tips/" not in link and not any(k in title for k in kw):
            continue
        try:
            published = parsedate_to_datetime(pub).replace(tzinfo=None) if pub else None
        except (TypeError, ValueError):
            published = None
        if published and (now - published) > dt.timedelta(days=5):
            continue
        tipster = title.split("│")[0].split("|")[0].strip()[:20] if title else ""
        articles.append(
            {"title": title, "url": link, "source": "星島頭條", "tipster": tipster,
             "published": (published.date().isoformat() if published else ""), "names": parse_quoted_names(title)}
        )
        if len(articles) >= max_articles:
            break

    # best-effort: pull more horse names from article bodies
    for art in articles:
        if not art["url"].startswith("https://www.stheadline.com/"):
            continue
        try:
            ar = requests.get(art["url"], headers=HEADERS, timeout=15)
            if ar.status_code == 200:
                for n in parse_quoted_names(ar.text):
                    if n not in art["names"]:
                        art["names"].append(n)
        except requests.RequestException:
            continue

    if vocab:
        for art in articles:
            art["names"] = [n for n in art["names"] if n in vocab]
    return articles


# ------------------------------------------------------------- aggregation --
def collect_news_tips(days: int = 3, year: int | None = None) -> pd.DataFrame:
    """Search all free sources and build one tidy tips dataframe.

    One row per pick: either a horse number (news headlines) or a horse
    name (quoted names from tipster columns).
    """
    now = dt.datetime.now()
    year = year or now.year
    rows: list[dict] = []
    seen_items: set[str] = set()

    try:
        from . import data_hub

        vocab = data_hub.horse_vocab()
    except Exception:
        vocab = set()

    def _row(**kw):
        base = {c: "" for c in TIPS_COLUMNS}
        base.update(kw)
        base["fetched_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        base["kind"] = base.get("kind") or "news"
        rows.append(base)

    # Google News headlines -> horse numbers
    for q in NEWS_QUERIES:
        for it in fetch_google_news(q, days=days):
            if it["url"] in seen_items or not it["title"]:
                continue
            seen_items.add(it["url"])
            race_no = parse_race_no(it["title"])
            horses = parse_horses(it["title"])
            names = parse_quoted_names(it["title"])
            race_date = parse_day_month(it["title"], year) or now.date()
            for h in horses:
                _row(race_date=race_date.isoformat(), race_no=race_no or "", horse_no=h,
                     source=it["source"], title=it["title"], url=it["url"], note=f"query={q}")
            for nm in names:
                if vocab and nm not in vocab:
                    continue
                _row(race_date=race_date.isoformat(), horse_name=nm,
                     source=it["source"], title=it["title"], url=it["url"], note=f"query={q}")

    # 星島頭條馬經專欄 -> quoted horse names + tipster
    for art in fetch_stheadline(vocab=vocab):
        if art["url"] in seen_items:
            continue
        seen_items.add(art["url"])
        for nm in art["names"]:
            _row(race_date=art["published"] or now.date().isoformat(), horse_name=nm,
                 source=art["source"], tipster=art["tipster"], title=art["title"], url=art["url"])

    return pd.DataFrame(rows, columns=TIPS_COLUMNS)


def collect_web_results(queries: list[str] | None = None) -> pd.DataFrame:
    """Web search results as reference links (not parsed into picks)."""
    queries = queries or WEB_QUERIES
    rows = []
    seen: set[str] = set()
    for q in queries:
        for it in fetch_ddg(q):
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            rows.append({"query": q, "source": it["source"], "title": it["title"], "url": it["url"]})
    return pd.DataFrame(rows, columns=["query", "source", "title", "url"])
