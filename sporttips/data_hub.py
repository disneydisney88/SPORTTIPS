# -*- coding: utf-8 -*-
"""Free HKJC racing data via the public tianxi-database GitHub repo (CSV/JSON on raw.githubusercontent.com)."""
from __future__ import annotations

import datetime as dt
import json
import re
from io import StringIO

import pandas as pd
import requests

TIANXI_BASE = "https://raw.githubusercontent.com/sleepingarhat/tianxi-database/main"
TIANXI_REPO = "https://github.com/sleepingarhat/tianxi-database"
_TIANXI_CREDIT = "tianxi-database (sleepingarhat) — HKJC public data, CC use with attribution"

HEADERS = {"User-Agent": "SPORTTIPS-app/1.0 (free data aggregation)"}


def _get_text(path: str, timeout: int = 20) -> str | None:
    try:
        r = requests.get(f"{TIANXI_BASE}/{path}", headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.text
    except requests.RequestException:
        return None


# -- cached loaders (no streamlit dependency so scripts can reuse these) -----
_results_cache: dict[str, pd.DataFrame | None] = {}


def fixtures() -> pd.DataFrame:
    txt = _get_text("data/fixtures/fixtures.csv")
    if not txt:
        return pd.DataFrame(columns=["date"])
    df = pd.read_csv(StringIO(txt), encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def results(race_day: str) -> pd.DataFrame | None:
    """Results for one race day, e.g. results('2026-09-09'). Cached in-process."""
    key = str(race_day)
    if key in _results_cache:
        return _results_cache[key]
    txt = _get_text(f"data/{key[:4]}/results_{key}.csv")
    df = None
    if txt:
        try:
            df = pd.read_csv(StringIO(txt), encoding="utf-8-sig")
        except Exception:
            df = None
    _results_cache[key] = df
    return df


def dividends(race_day: str) -> pd.DataFrame | None:
    txt = _get_text(f"data/{str(race_day)[:4]}/dividends_{race_day}.csv")
    if not txt:
        return None
    try:
        return pd.read_csv(StringIO(txt), encoding="utf-8-sig")
    except Exception:
        return None


def horse_form(brand_no: str) -> pd.DataFrame | None:
    """Full career form for one horse brand number, e.g. 'A001'."""
    code = str(brand_no).strip().upper()
    txt = _get_text(f"horses/form_records/form_{code}.csv")
    if not txt:
        return None
    try:
        df = pd.read_csv(StringIO(txt), encoding="utf-8-sig")
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True, errors="coerce")
        return df.sort_values("date", ascending=False)
    except Exception:
        return None


def horse_vocab() -> set[str]:
    """All HK horse names (2016-2026) from the pedigree file — used to filter
    quoted names scraped from media so only real horse names count as tips."""
    txt = _get_text("data/pedigree/horse_pedigree.csv")
    if not txt:
        return set()
    try:
        df = pd.read_csv(StringIO(txt), encoding="utf-8-sig")
    except Exception:
        return set()
    vocab: set[str] = set()
    for s in df.get("name", pd.Series(dtype=str)).dropna():
        base = re.sub(r"\s*[（(][A-Z]\d{3}[)）].*$", "", str(s)).strip()
        if base:
            vocab.add(base)
    return vocab


def race_card(race_day: str) -> dict | None:
    """Full meeting card from HKJC SpeedPro data (per race: runners, draw, energy)."""
    for venue in ("ST", "HV"):
        txt = _get_text(f"speedpro/data/{race_day}_{venue}.json")
        if txt:
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                continue
    return None


def next_race_days(after: dt.date, n: int = 3) -> list[dt.date]:
    fx = fixtures()
    if fx.empty:
        return []
    upcoming = fx.loc[fx["date"] >= after, "date"].sort_values().tolist()
    return upcoming[:n]


def recent_race_days(before: dt.date, n: int = 5) -> list[dt.date]:
    fx = fixtures()
    if fx.empty:
        return []
    past = fx.loc[fx["date"] < before, "date"].sort_values(ascending=False).tolist()
    return past[:n]
