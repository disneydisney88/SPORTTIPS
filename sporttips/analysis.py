# -*- coding: utf-8 -*-
"""Consensus statistics and past-performance evaluation.

Tips are matched to official results two ways:
- by horse number (exact race_date + race_no + horse_no)
- by horse name (race_date + normalised name, since a name is unique per meeting)
"""
from __future__ import annotations

import re

import pandas as pd


def norm_name(s: str) -> str:
    """Normalise a horse name: strip 「」 quotes, spaces and HKJC '(J218)' suffixes."""
    s = str(s or "")
    s = re.sub(r"[「」『』\s]", "", s)
    s = re.sub(r"[（(][A-Z]\d{3}[)）]\s*$", "", s)
    return s


def _pick_key(df: pd.DataFrame) -> pd.Series:
    """Display key per tip row: horse name when available, otherwise #number."""
    name = df["horse_name"].fillna("").astype(str).str.strip()
    num = df["horse_no"].fillna("").astype(str).str.strip()
    return name.where(name != "", "#" + num.replace("", pd.NA).fillna(""))


def consensus(tips: pd.DataFrame, race_date: str | None = None) -> pd.DataFrame:
    """Aggregate mentions per pick across all sources."""
    if tips.empty:
        return pd.DataFrame()
    df = tips.copy()
    if race_date:
        df = df[df["race_date"] == str(race_date)]
    if df.empty:
        return df
    df["pick"] = _pick_key(df)
    grp = (
        df.groupby(["race_date", "pick"], dropna=False)
        .agg(
            mentions=("source", "count"),
            n_sources=("source", "nunique"),
            sources=("source", lambda s: "、".join(sorted(set(str(x) for x in s)))),
            tipsters=("tipster", lambda s: "、".join(sorted(set(str(x) for x in s if str(x) and x != 'nan')))),
            titles=("title", lambda s: list(s)[:5]),
            urls=("url", lambda s: list(dict.fromkeys(str(x) for x in s if str(x) and x != 'nan'))[:5]),
        )
        .reset_index()
        .sort_values(["race_date", "mentions"], ascending=[True, False])
    )
    return grp


def source_stats(tips: pd.DataFrame) -> pd.DataFrame:
    if tips.empty:
        return pd.DataFrame()
    grp = (
        tips.groupby("source")
        .agg(tips=("url", "count"), days=("race_date", "nunique"), kind=("kind", "first"))
        .reset_index()
        .sort_values("tips", ascending=False)
    )
    return grp


def evaluate(tips: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Attach official results (place, win_odds) to stored tips."""
    if tips.empty or results is None or results.empty:
        return pd.DataFrame()
    r = results.copy()
    r = r.rename(columns={"date": "race_date"})
    r["race_date"] = r["race_date"].astype(str)
    r["race_no_s"] = r["race_no"].astype(str).str.strip()
    r["horse_no_s"] = r["horse_no"].astype(str).str.strip()
    r["name_norm"] = r["horse_name"].map(norm_name)

    t = tips.copy()
    t["race_no_s"] = (
        t["race_no"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    )
    t["horse_no_s"] = (
        t["horse_no"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    )
    t["name_norm"] = t["horse_name"].map(norm_name)
    t["_tip_id"] = range(len(t))

    r_name = r[["race_date", "name_norm", "place", "win_odds", "horse_name"]].rename(
        columns={"horse_name": "matched_horse"}
    )
    r_num = r[["race_date", "race_no_s", "horse_no_s", "place", "win_odds", "horse_name"]].rename(
        columns={"horse_name": "matched_horse"}
    )
    by_name = t[t["name_norm"] != ""].merge(
        r_name,
        on=["race_date", "name_norm"], how="left",
    )
    by_num = t[(t["name_norm"] == "") & (t["horse_no_s"] != "")].merge(
        r_num,
        on=["race_date", "race_no_s", "horse_no_s"], how="left",
    )
    out = pd.concat([by_name, by_num], ignore_index=True).sort_values("_tip_id")
    out["place"] = pd.to_numeric(out["place"], errors="coerce")
    out["win_odds"] = pd.to_numeric(out["win_odds"], errors="coerce")
    out["is_win"] = out["place"] == 1
    out["is_place"] = out["place"].between(1, 3)
    return out


def performance_table(evaluated: pd.DataFrame, by: str | None = "source") -> pd.DataFrame:
    """Hit rate + ROI table overall or grouped by a column (e.g. source)."""
    if evaluated is None or evaluated.empty:
        return pd.DataFrame()
    evaluated = evaluated.dropna(subset=["place"])
    if evaluated.empty:
        return pd.DataFrame()

    def _agg(g: pd.DataFrame) -> pd.Series:
        wins = int(g["is_win"].sum())
        places = int(g["is_place"].sum())
        stake = len(g)
        ret = float(g.loc[g["is_win"], "win_odds"].fillna(0).sum())
        return pd.Series(
            {
                "picks": stake,
                "wins": wins,
                "places": places,
                "win_rate": wins / stake,
                "place_rate": places / stake,
                "roi": (ret - stake) / stake,
            }
        )

    if by:
        out = evaluated.groupby(by).apply(_agg, include_groups=False).reset_index()
        return out.sort_values("roi", ascending=False)
    return _agg(evaluated).to_frame().T
