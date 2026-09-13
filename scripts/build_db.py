# -*- coding: utf-8 -*-
"""Build the pre-installed SQLite database (data/sporttips.db).

Tables:
  results(date, venue, race_no, race_name, race_class, distance_m, going,
          course, place, horse_no, horse_name, horse_code, jockey, trainer,
          draw, win_odds)  -- HKJC results via tianxi-database CSVs
  fixtures(date)
  horse_names(name)          -- every HK horse name (vocab for tip filtering)

Full build:  --full   (fetch every results file since SEASON_FROM)
Incremental: default (only race days newer than the newest row in the DB)

Run by GitHub Actions daily; committed back to the repo so the deployed
Streamlit app reads a local DB instead of making hundreds of requests.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sporttips.data_hub import (  # noqa: E402
    HEADERS,
    TIANXI_BASE,
    fixtures,
    horse_vocab,
)

DB_PATH = ROOT / "data" / "sporttips.db"
SEASON_FROM = "2022-07-01"  # keep the last ~4 seasons to stay small

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    date TEXT, venue TEXT, race_no INTEGER, race_name TEXT, race_class TEXT,
    distance_m INTEGER, going TEXT, course TEXT, place INTEGER,
    horse_no INTEGER, horse_name TEXT, horse_code TEXT,
    jockey TEXT, trainer TEXT, draw INTEGER, win_odds REAL
);
CREATE INDEX IF NOT EXISTS idx_results_date ON results(date);
CREATE INDEX IF NOT EXISTS idx_results_horse ON results(horse_code);
CREATE TABLE IF NOT EXISTS fixtures (date TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS horse_names (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def _get(path: str, tries: int = 2) -> str | None:
    for _ in range(tries):
        try:
            r = requests.get(f"{TIANXI_BASE}/{path}", headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            time.sleep(1)
    return None


def parse_results(txt: str) -> pd.DataFrame:
    df = pd.read_csv(__import__("io").StringIO(txt), encoding="utf-8-sig")
    if df.empty:
        return pd.DataFrame()
    def code_of(name: str) -> str:
        m = re.search(r"[（(]([A-Z]\d{3})[)）]", str(name))
        return m.group(1) if m else ""
    out = pd.DataFrame(
        {
            "date": df["date"].astype(str),
            "venue": df.get("venue", ""),
            "race_no": pd.to_numeric(df.get("race_no"), errors="coerce"),
            "race_name": df.get("race_name", ""),
            "race_class": df.get("race_class", ""),
            "distance_m": pd.to_numeric(df.get("distance_m"), errors="coerce"),
            "going": df.get("going", ""),
            "course": df.get("course", ""),
            "place": pd.to_numeric(df.get("place"), errors="coerce"),
            "horse_no": pd.to_numeric(df.get("horse_no"), errors="coerce"),
            "horse_name": df.get("horse_name", "").astype(str).str.replace(r"\s*[（(][A-Z]\d{3}[)）]\s*", "", regex=True),
            "horse_code": df.get("horse_name", "").map(code_of),
            "jockey": df.get("jockey", ""),
            "trainer": df.get("trainer", ""),
            "draw": pd.to_numeric(df.get("draw"), errors="coerce"),
            "win_odds": pd.to_numeric(df.get("win_odds"), errors="coerce"),
        }
    )
    return out


def fetch_day(day: str) -> pd.DataFrame | None:
    year = day[:4]
    txt = _get(f"data/{year}/results_{day}.csv")
    if not txt:
        return None
    try:
        df = parse_results(txt)
        return df if not df.empty else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="ignore existing DB and rebuild")
    args = ap.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    if args.full and DB_PATH.exists():
        con.execute("DELETE FROM results")
        con.execute("DELETE FROM fixtures")
        con.execute("DELETE FROM horse_names")
        con.commit()

    row = con.execute("SELECT MAX(date) FROM results").fetchone()
    newest = row[0] if row and row[0] else None
    cutoff = newest or SEASON_FROM
    print(f"build_db: existing newest result date = {newest}")

    fx = fixtures()
    if fx.empty:
        print("build_db: fixtures unavailable, abort")
        return 1
    con.executemany(
        "INSERT OR IGNORE INTO fixtures(date) VALUES (?)",
        [(str(d),) for d in sorted(fx["date"].tolist())],
    )
    con.commit()

    days = [str(d) for d in sorted(fx["date"].unique()) if str(d) >= cutoff]
    if not args.full and newest:
        days = [d for d in days if d > newest]
    print(f"build_db: fetching {len(days)} candidate race days ...")

    def work(day: str):
        return day, fetch_day(day)

    added = 0
    with ThreadPoolExecutor(8) as ex:
        for day, df in ex.map(work, days):
            if df is not None:
                df.to_sql("results", con, if_exists="append", index=False)
                added += len(df)
    con.commit()
    print(f"build_db: added {added} result rows")

    # refresh horse-name vocab
    con.execute("DELETE FROM horse_names")
    names = sorted(horse_vocab())
    con.executemany("INSERT OR IGNORE INTO horse_names(name) VALUES (?)", [(n,) for n in names])
    con.commit()
    print(f"build_db: horse_names = {len(names)}")

    con.execute(
        "INSERT OR REPLACE INTO meta(k, v) VALUES ('built_at', datetime('now'))"
    )
    con.commit()
    size_mb = DB_PATH.stat().st_size / 1e6
    print(f"build_db: {DB_PATH} = {size_mb:.1f} MB")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
