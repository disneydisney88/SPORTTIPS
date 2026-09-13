# -*- coding: utf-8 -*-
"""CSV storage for tips (news + manual). Pure Python so GitHub Actions can reuse it."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .tip_sources import TIPS_COLUMNS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TIPS_FILE = DATA_DIR / "tips.csv"
MANUAL_FILE = DATA_DIR / "manual_tips.csv"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=TIPS_COLUMNS)
    try:
        df = pd.read_csv(path, dtype={"race_no": "str", "horse_no": "str"}, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame(columns=TIPS_COLUMNS)
    for col in TIPS_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[TIPS_COLUMNS]


def load_tips(include_manual: bool = True) -> pd.DataFrame:
    frames = [_read(TIPS_FILE)]
    if include_manual:
        frames.append(_read(MANUAL_FILE))
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return df
    return df.drop_duplicates(subset=["url", "race_date", "race_no", "horse_no", "source", "tipster", "kind"], keep="last")


def save_tips(new_rows: pd.DataFrame, manual: bool = False) -> int:
    """Merge new tip rows into the store. Returns number of genuinely new rows."""
    path = MANUAL_FILE if manual else TIPS_FILE
    new_rows = new_rows.reindex(columns=TIPS_COLUMNS)
    existing = _read(path)
    combined = pd.concat([existing, new_rows], ignore_index=True)
    before = len(existing)
    combined = combined.drop_duplicates(
        subset=["url", "race_date", "race_no", "horse_no", "horse_name", "source", "tipster", "kind"],
        keep="last",
    )
    combined.to_csv(path, index=False, encoding="utf-8-sig")
    return max(len(combined) - before, 0)
