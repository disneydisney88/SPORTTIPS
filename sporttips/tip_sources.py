# -*- coding: utf-8 -*-
"""Tip source: 星島頭條「馬經」專欄 via their public RSS.

Tipster columns (亨利拆局 / 馬觀微全日心水 / Dickson心水 ...) quote horse
names like 「金勝名駒」. Names are validated against the tianxi pedigree
vocabulary so only real horses count. Every tip keeps tipster + article link.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape

import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (SPORTTIPS free aggregator)"}

STHEADLINE_RSS = "https://www.stheadline.com/rss"

TIPS_COLUMNS = [
    "fetched_at", "race_date", "race_no", "horse_no", "horse_name",
    "source", "tipster", "title", "url", "kind", "note",
]


# ---------------------------------------------------------------- parsing --
def parse_quoted_names(text: str) -> list[str]:
    """HK racing media quote horse names like 「金勝名駒」."""
    out = []
    for m in re.finditer(r"[「『]([^「」『』]{2,10})[」』]", text):
        name = m.group(1).strip()
        if name and name not in out:
            out.append(name)
    return out


# ---------------------------------------------------------------- source --
def fetch_stheadline(max_articles: int = 8, days: int = 4, vocab: set[str] | None = None) -> list[dict]:
    """Latest racing-tipster articles (title + body names + tipster + link)."""
    try:
        r = requests.get(STHEADLINE_RSS, headers=HEADERS, timeout=15)
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
        if published and (now - published) > dt.timedelta(days=days):
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
            ar = requests.get(art["url"], headers=HEADERS, timeout=12)
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
    """Collect tips from 星島頭條 into one tidy dataframe (one row per horse name)."""
    now = dt.datetime.now()
    rows: list[dict] = []

    try:
        from . import data_hub

        vocab = data_hub.horse_vocab()
    except Exception:
        vocab = set()

    for art in fetch_stheadline(days=days + 1, vocab=vocab):
        for nm in art["names"]:
            rows.append(
                {
                    "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "race_date": art["published"] or now.date().isoformat(),
                    "race_no": "",
                    "horse_no": "",
                    "horse_name": nm,
                    "source": art["source"],
                    "tipster": art["tipster"],
                    "title": art["title"],
                    "url": art["url"],
                    "kind": "news",
                    "note": "",
                }
            )
    return pd.DataFrame(rows, columns=TIPS_COLUMNS)
