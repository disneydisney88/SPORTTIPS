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

ONCC_BASE = "https://racing.on.cc"
ONCC_FILES = [
    # (path, label) — Big5 static fragments on 東網馬經
    ("/racing/fav/current/rjfavg0001x0.html", "名家推介"),
    ("/racing/fav/current/rjfavf0101x0.html", "西門獨貼士"),
    ("/racing/fav/current/rjfavf0201x0.html", "西門獨／諸葛數貼士"),
    ("/racing/fav/current/rjfavf0301x0.html", "東網馬經"),
    ("/racing/fav/current/rjfavi0101x0.html", "兆文專欄"),
]

TIPS_COLUMNS = [
    "fetched_at", "race_date", "race_no", "horse_no", "horse_name",
    "source", "tipster", "title", "url", "kind", "note",
]


def _clean_html(t: str) -> str:
    t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


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
def _oncc_iso_date(m: re.Match) -> str:
    d, mo, y = m.group(1), m.group(2), m.group(3)
    return f"{y}-{mo}-{d}"


def fetch_oncc(vocab: set[str] | None = None) -> list[dict]:
    """東網馬經 (racing.on.cc) tip fragments — Big5 static HTML with
    structured picks: tipster + 第X場 + horse numbers + horse names."""
    articles: list[dict] = []
    for path, label in ONCC_FILES:
        try:
            r = requests.get(ONCC_BASE + path, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            text = _clean_html(r.content.decode("big5", "ignore"))
        except requests.RequestException:
            continue

        rows: list[dict] = []
        if label == "名家推介":
            # date + tipster segments: 卡洛斯 連贏及單Ｔ過關 第5場 11天天更好 2肯佩斯 ...
            dm = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
            race_date = _oncc_iso_date(dm) if dm else ""
            for seg in re.finditer(
                r"([\u4e00-\u9fff]{2,4})\s*連贏及單Ｔ過關(.*?)(?=[\u4e00-\u9fff]{2,4}\s*連贏及單Ｔ過關|$)",
                text,
            ):
                tipster = seg.group(1)
                for rm in re.finditer(r"第(\d{1,2})場\s*((?:\d{1,2}[\u4e00-\u9fff?？]{2,6}\s*)+)", seg.group(2)):
                    race_no = int(rm.group(1))
                    for hm in re.finditer(r"(\d{1,2})([\u4e00-\u9fff?？]{2,6})", rm.group(2)):
                        rows.append((race_no, int(hm.group(1)), hm.group(2).replace("？", "").replace("?", ""), tipster))
        elif label in ("西門獨貼士", "西門獨／諸葛數貼士", "東網馬經"):
            dm = re.search(r"賽事日期：\s*(\d{2})/(\d{2})/(\d{4})", text)
            race_date = _oncc_iso_date(dm) if dm else ""
            # optional tipster sections: XX貼士 ... (f0301 has none)
            sections = re.split(r"([\u4e00-\u9fff]{2,4})貼士", text)
            # sections alternates: [pre, name1, body1, name2, body2, ...]
            if len(sections) > 1:
                bodies = [(sections[i], sections[i + 1]) for i in range(1, len(sections) - 1, 2)]
            else:
                bodies = [("", text)]
            for tipster, body in bodies:
                for rm in re.finditer(
                    r"第(\d{1,2})場\s*((?:\d{1,2}\s*[\u4e00-\u9fff?？]{2,6}\s*)+)",
                    body,
                ):
                    race_no = int(rm.group(1))
                    for hm in re.finditer(r"(\d{1,2})\s*([\u4e00-\u9fff?？]{2,6})", rm.group(2)):
                        rows.append((race_no, int(hm.group(1)), hm.group(2).replace("？", "").replace("?", ""), tipster or "東網馬經"))
        else:  # 兆文專欄 — editorial: 第X場「馬名」
            dm = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
            race_date = _oncc_iso_date(dm) if dm else ""
            tm = re.search(r"([\u4e00-\u9fff]{2,3})\s*\d{2}/\d{2}/\d{4}", text)
            tipster = tm.group(1) if tm else "兆文"
            parts = re.split(r"第(\d{1,2})場", text)
            # parts: [pre, raceno1, body1, raceno2, body2, ...]
            for i in range(1, len(parts) - 1, 2):
                race_no = int(parts[i])
                for nm in parse_quoted_names(parts[i + 1]):
                    rows.append((race_no, None, nm, tipster))
        if not rows:
            continue

        if rows and vocab:
            cleaned = []
            for race_no, horse_no, name, tipster in rows:
                if not name or norm_for_vocab(name) in vocab:
                    cleaned.append((race_no, horse_no, name, tipster))
                elif horse_no is not None:
                    # number is authoritative even when encoding mangles the name
                    cleaned.append((race_no, horse_no, "", tipster))
            rows = cleaned
        articles.append(
            {
                "label": label,
                "race_date": race_date,
                "url": ONCC_BASE + path,
                "rows": rows,
            }
        )
    return articles


def norm_for_vocab(name: str) -> str:
    return re.sub(r"[?？\s]", "", name)


def collect_news_tips(days: int = 3, year: int | None = None) -> pd.DataFrame:
    """Collect tips from 東網馬經 + 星島頭條 into one tidy dataframe."""
    now = dt.datetime.now()
    rows: list[dict] = []

    try:
        from . import data_hub

        vocab = data_hub.horse_vocab()
    except Exception:
        vocab = set()

    def _row(**kw):
        base = {c: "" for c in TIPS_COLUMNS}
        base.update(kw)
        base["fetched_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        base["kind"] = "news"
        rows.append(base)

    # 東網馬經 — structured picks with race_no + horse_no
    for art in fetch_oncc(vocab=vocab):
        if art["race_date"]:
            try:
                age = (now.date() - dt.date.fromisoformat(art["race_date"])).days
            except ValueError:
                age = 0
            if age > days + 1:
                continue
        for race_no, horse_no, name, tipster in art["rows"]:
            _row(
                race_date=art["race_date"] or now.date().isoformat(),
                race_no=race_no or "",
                horse_no=horse_no if horse_no is not None else "",
                horse_name=name or "",
                source="東網馬經",
                tipster=tipster or art["label"],
                title=art["label"],
                url=art["url"],
                note="oncc",
            )

    # 星島頭條 — quoted horse names from tipster columns
    for art in fetch_stheadline(days=days + 1, vocab=vocab):
        for nm in art["names"]:
            _row(
                race_date=art["published"] or now.date().isoformat(),
                horse_name=nm,
                source=art["source"],
                tipster=art["tipster"],
                title=art["title"],
                url=art["url"],
            )
    return pd.DataFrame(rows, columns=TIPS_COLUMNS)
