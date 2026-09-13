# -*- coding: utf-8 -*-
"""Free HKJC racing data:
- tianxi-database GitHub repo (SpeedPro cards, results, form, pedigree, fixtures)
- HKJC official GraphQL gateway (whitelisted queries used by bet.hkjc.com)
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

TIANXI_BASE = "https://raw.githubusercontent.com/sleepingarhat/tianxi-database/main"
TIANXI_REPO = "https://github.com/sleepingarhat/tianxi-database"
_TIANXI_CREDIT = "tianxi-database (sleepingarhat) — HKJC public data, CC use with attribution"

# This app's own repo — the durable tips store committed by GitHub Actions
SELF_TIPS_URL = "https://raw.githubusercontent.com/disneydisney88/SPORTTIPS/master/data/tips.csv"

HEADERS = {"User-Agent": "SPORTTIPS-app/1.0 (free data aggregation)"}


def _get_text(path: str, timeout: int = 20) -> str | None:
    try:
        r = requests.get(f"{TIANXI_BASE}/{path}", headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.text
    except requests.RequestException:
        return None


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "sporttips.db"


def db_query(sql: str, params: tuple = ()) -> pd.DataFrame | None:
    """Read from the pre-installed SQLite DB (data/sporttips.db); None if absent."""
    if not DB_PATH.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            return pd.read_sql_query(sql, con, params=params)
        finally:
            con.close()
    except (sqlite3.Error, pd.errors.DatabaseError):
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
    """Results for one race day — pre-installed DB first, remote CSV fallback."""
    day = str(race_day)
    db = db_query("SELECT * FROM results WHERE date = ?", (day,))
    if db is not None:
        if not db.empty:
            return db
        return None
    txt = _get_text(f"data/{day[:4]}/results_{day}.csv")
    df = None
    if txt:
        try:
            df = pd.read_csv(StringIO(txt), encoding="utf-8-sig")
        except Exception:
            df = None
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
    """All HK horse names — pre-installed DB first, remote pedigree fallback."""
    db = db_query("SELECT name FROM horse_names")
    if db is not None and not db.empty:
        return set(db["name"].astype(str))
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


def remote_tips() -> pd.DataFrame:
    """Tips committed to this repo by GitHub Actions — the durable fallback
    when a live fetch from the app host is blocked or times out."""
    txt = _get_text(SELF_TIPS_URL)
    if not txt:
        return pd.DataFrame()
    try:
        return pd.read_csv(StringIO(txt), dtype=str, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


def jockey_profiles() -> pd.DataFrame:
    """Current-season jockey statistics (parsed from the tianxi profiles CSV)."""
    txt = _get_text("jockeys/jockey_profiles.csv")
    if not txt:
        return pd.DataFrame()
    try:
        raw = pd.read_csv(StringIO(txt), encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()

    def _num(cell, pattern: str) -> float:
        m = re.search(pattern, str(cell or ""))
        return float(m.group(1)) if m else float("nan")

    out = pd.DataFrame(
        {
            "jockey": raw.get("jockey_name", "").astype(str).str.strip(),
            "rides": pd.to_numeric(raw.get("current_總出賽次數"), errors="coerce"),
            "win_pct": pd.to_numeric(
                raw.get("current_勝出率").astype(str).str.rstrip("%"), errors="coerce"
            ),
            "win_cnt": raw.get("current_國籍").map(lambda c: _num(c, r"冠\s*:\s*(\d+)")),
            "place2_cnt": raw.get("current_所贏獎金").map(lambda c: _num(c, r"亞\s*:\s*(\d+)")),
            "place3_cnt": raw.get("current_過去10個賽馬日\n獲勝次數").map(lambda c: _num(c, r"季\s*:\s*(\d+)")),
        }
    )
    out["place_pct"] = (out["place2_cnt"] + out["place3_cnt"]) / out["rides"] * 100
    return out.dropna(subset=["rides"]).sort_values("win_pct", ascending=False)


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


HKJC_GRAPHQL = "https://info.cld.hkjc.com/graphql/base/"


def hkjc_meeting(race_day: str) -> dict | None:
    """Official HKJC meeting via the public whitelisted GraphQL query.

    Returns per-race runners with today's jockey/trainer, draw, weight,
    rating, last-6 form and live win odds. None if unreachable.
    """
    qpath = Path(__file__).resolve().parent / "hkjc_query.txt"
    try:
        query = qpath.read_text(encoding="utf-8")
    except OSError:
        return None
    for venue in ("ST", "HV"):
        try:
            r = requests.post(
                HKJC_GRAPHQL,
                json={"query": query, "variables": {"date": race_day, "venueCode": venue}},
                headers={"Content-Type": "application/json", **HEADERS},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            md = (r.json().get("data") or {}).get("raceMeetings") or []
            if md and md[0].get("races"):
                return md[0]
        except (requests.RequestException, json.JSONDecodeError, ValueError):
            continue
    return None


def horse_stats(brand_no: str, jockey_today: str = "") -> dict:
    """Career summary + jockey-horse combo — pre-installed DB first, CSV fallback."""
    code = str(brand_no).strip().upper()
    df = db_query(
        "SELECT date, place, jockey, distance_m FROM results WHERE horse_code = ? "
        "ORDER BY date DESC, race_no DESC",
        (code,),
    )
    if df is None:
        df = horse_form(code)
    if df is None or df.empty:
        return {}
    placed = pd.to_numeric(df["place"], errors="coerce")
    valid = placed.dropna()
    runs = int(valid.shape[0])
    if not runs:
        return {}
    wins = int((valid == 1).sum())
    places = int(valid.between(1, 3).sum())
    last_date = pd.to_datetime(df["date"], errors="coerce", dayfirst=False).dropna().max()
    last_jockey = str(df.iloc[0].get("jockey", "") or "").strip()

    target = jockey_today.strip() or last_jockey
    combo_rides = df[df["jockey"].astype(str).str.strip() == target] if target else df.iloc[0:0]
    cplaced = pd.to_numeric(combo_rides["place"], errors="coerce").dropna()

    return {
        "runs": runs,
        "wins": wins,
        "places": places,
        "last5": [int(p) for p in valid.head(5).tolist()],
        "last_date": last_date.strftime("%d/%m") if pd.notna(last_date) else "",
        "days_since": (dt.date.today() - last_date.date()).days if pd.notna(last_date) else "",
        "last_jockey": last_jockey,
        "best_dist": _best_distance(df, placed),
        "combo": {
            "jockey": target,
            "runs": int(cplaced.shape[0]),
            "wins": int((cplaced == 1).sum()),
            "places": int(cplaced.between(1, 3).sum()),
        },
    }


def _best_distance(df: pd.DataFrame, placed: pd.Series) -> str:
    """Distance (m) with the best average finish for this horse."""
    d = df.assign(p=placed).dropna(subset=["p", "distance_m"])
    if d.empty:
        return ""
    agg = d.groupby("distance_m")["p"].agg(["mean", "count"])
    agg = agg[agg["count"] >= 2]
    if agg.empty:
        return ""
    return f"{int(agg['mean'].idxmin())}m"


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
