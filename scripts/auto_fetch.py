# -*- coding: utf-8 -*-
"""Standalone daily fetch used by GitHub Actions (no streamlit dependency).

Searches free news sources for tips and merges them into data/tips.csv.
The workflow commits any changes back to the repo, which keeps the
Streamlit Cloud app supplied with fresh data for free.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from sporttips import storage, tip_sources  # noqa: E402


def main() -> int:
    df = tip_sources.collect_news_tips(days=3)
    if df.empty:
        print("auto_fetch: no tips found today")
        n = 0
    else:
        n = storage.save_tips(df)
        print(f"auto_fetch: {len(df)} parsed rows, {n} new rows saved")
    (storage.DATA_DIR / "last_run.txt").write_text(
        dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f" new_rows={n}\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
