# -*- coding: utf-8 -*-
"""SPORTTIPS — free HK racing tips platform (繁中/English).

Tips come from 星島頭條「馬經」tipster columns, always attributed.
Race cards (per race, per runner) come from free HKJC SpeedPro data.
Data refreshes automatically when the page opens; GitHub Actions keeps
the repo store fresh daily.
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd
import plotly.express as px
import streamlit as st

from sporttips import analysis, data_hub, storage, tip_sources
from sporttips.analysis import norm_name
from sporttips.i18n import t

st.set_page_config(page_title="SPORTTIPS", page_icon="🏇", layout="wide")

if "lang" not in st.session_state:
    st.session_state.lang = "zh"

PAGES = ["nav_today", "nav_search", "nav_consensus", "nav_analysis", "nav_past", "nav_data", "nav_about"]


@st.cache_data(ttl=3600, show_spinner=False)
def _fixtures() -> pd.DataFrame:
    return data_hub.fixtures()


@st.cache_data(ttl=3600, show_spinner=False)
def _results(day: str) -> pd.DataFrame | None:
    return data_hub.results(day)


@st.cache_data(ttl=3600, show_spinner=False)
def _horse_form(code: str) -> pd.DataFrame | None:
    return data_hub.horse_form(code)


@st.cache_data(ttl=1800, show_spinner=False)
def _race_card(day: str) -> dict | None:
    return data_hub.race_card(day)


def _L(key: str) -> str:
    return t(key, st.session_state.lang)


def _auto_update() -> None:
    """Refresh tips silently when the page opens (throttled to once per 45 min)."""
    now = time.time()
    if now - st.session_state.get("_last_auto", 0) < 45 * 60:
        return
    st.session_state["_last_auto"] = now
    try:
        n = storage.save_tips(tip_sources.collect_news_tips(days=3))
    except Exception:
        return
    if n:
        st.toast(_L("updated_ok").format(n=n), icon="✅")


_auto_update()
tips_all = storage.load_tips()

# ------------------------------------------------------------------ sidebar --
with st.sidebar:
    st.title("🏇 SPORTTIPS")
    st.caption(_L("app_caption"))
    choice = st.radio(
        "語言 Language",
        ["繁中", "English"],
        index=0 if st.session_state.lang == "zh" else 1,
        horizontal=True,
        label_visibility="collapsed",
        key="lang_radio",
    )
    st.session_state.lang = "zh" if choice == "繁中" else "en"

    st.divider()
    page = st.radio(
        "PAGE",
        PAGES,
        format_func=lambda k: _L(k),
        label_visibility="collapsed",
        key="page",
    )

    st.divider()
    if st.button(_L("btn_update"), width="stretch", type="primary"):
        with st.spinner("..."):
            n = storage.save_tips(tip_sources.collect_news_tips(days=3))
        if n:
            st.toast(_L("updated_ok").format(n=n), icon="✅")
        else:
            st.toast(_L("updated_none"), icon="ℹ️")
    if not tips_all.empty:
        st.caption(f"{_L('col_date')}: {tips_all['fetched_at'].max()} · {len(tips_all)} rows")


def _tips_by_name(day_keys: set[str]) -> dict[str, list[str]]:
    """Map normalised horse name -> tipsters, from tips in the given race dates."""
    if tips_all.empty:
        return {}
    recent = tips_all[tips_all["race_date"].isin(day_keys)]
    out: dict[str, list[str]] = {}
    for _, r in recent.iterrows():
        nm = norm_name(r.get("horse_name", ""))
        if not nm:
            continue
        who = str(r.get("tipster") or r.get("source") or "").strip()
        bucket = out.setdefault(nm, [])
        if who and who not in bucket:
            bucket.append(who)
    return out


def _card_dates() -> list[str]:
    """Candidate dates that may have a SpeedPro card: today, next fixtures, last ones."""
    today = dt.date.today()
    dates = [today]
    dates += data_hub.next_race_days(today, 3)
    dates += data_hub.recent_race_days(today, 2)
    seen, out = set(), []
    for d in dates:
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if iso not in seen:
            seen.add(iso)
            out.append(iso)
    return out


# ------------------------------------------------------------------- pages --
if page == "nav_today":
    st.header(_L("nav_today"))
    today = dt.date.today()
    fx = _fixtures()
    is_race_day = today in set(fx["date"]) if not fx.empty else False
    if is_race_day:
        st.success(_L("today_race_day"))
    else:
        nxt = data_hub.next_race_days(today, 3)
        st.info(f"{_L('today_no_race')} — {_L('today_next').format(d=', '.join(map(str, nxt)))}")

    # --- race card (per race), from today or nearest available day -----------
    card = None
    card_day = ""
    for d in _card_dates():
        card = _race_card(d)
        if card and card.get("races"):
            card_day = d
            break

    if not card:
        st.warning(_L("card_none"))
    else:
        title = _L("card_title") if card_day == today.isoformat() else _L("card_of").format(d=card_day)
        st.subheader(f"🏇 {title} · {card.get('venue','')}")
        d0 = dt.date.fromisoformat(card_day)
        day_keys = {
            (d0 - dt.timedelta(days=1)).isoformat(),
            d0.isoformat(),
            (d0 + dt.timedelta(days=1)).isoformat(),
        }
        tips_map = _tips_by_name(day_keys)

        for race in card["races"]:
            info = race.get("raceinfo_chi") or race.get("raceinfo_eng") or {}
            en = st.session_state.lang == "en"
            rname = (race.get("raceinfo_eng") or info).get("RaceName", "") if en else info.get("RaceName", "")
            label = _L("race_x").format(
                n=race.get("raceno", "?"),
                name=rname,
                dist=info.get("Distance", ""),
                cls=info.get("RaceClass", ""),
                time=info.get("PostTime", ""),
            )
            runners = [r for r in race.get("energy", []) if not r.get("scratched")]
            rows = []
            for r in runners:
                nm_chi = str(r.get("name_chi") or "").strip()
                nm_en = str(r.get("name_eng") or r.get("name") or "").strip()
                who = tips_map.get(norm_name(nm_chi), []) or tips_map.get(norm_name(nm_en.upper()), [])
                if st.session_state.lang == "zh":
                    display = f"⭐ {nm_chi}" if who else nm_chi
                else:
                    display = f"⭐ {nm_en}" if who else nm_en
                try:
                    energy = int(str(r.get("speedproenergy") or "0").strip() or 0)
                except ValueError:
                    energy = 0
                rows.append(
                    {
                        _L("col_runner"): r.get("runnernumber"),
                        _L("col_horse2"): display,
                        _L("col_draw"): r.get("draw"),
                        _L("col_energy"): energy,
                        _L("col_diff"): r.get("speedproenergydifference"),
                        _L("col_fitness"): r.get("fitnessrating"),
                        _L("col_tips"): "、".join(who),
                    }
                )
            has_tips = any(row[_L("col_tips")] for row in rows)
            with st.expander(label, expanded=has_tips):
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        _L("col_energy"): st.column_config.ProgressColumn(
                            _L("col_energy"), min_value=0, max_value=120,
                        ),
                    },
                )

    # --- latest results (collapsed) ------------------------------------------
    recent = data_hub.recent_race_days(dt.date.today(), 1)
    if recent:
        last_day = str(recent[0])
        res = _results(last_day)
        if res is not None and not res.empty:
            with st.expander(f"📋 {_L('today_recent').format(d=last_day)}"):
                show = res[["race_no", "race_name", "place", "horse_no", "horse_name", "jockey", "win_odds"]]
                st.dataframe(show.head(80), width="stretch", hide_index=True)

elif page == "nav_search":
    st.header(_L("nav_search"))
    days = st.slider(_L("search_days"), 1, 7, 3)
    if "search_df" not in st.session_state:
        st.session_state.search_df = pd.DataFrame()

    if st.button(_L("btn_fetch"), type="primary"):
        with st.spinner("星島頭條 ..."):
            st.session_state.search_df = tip_sources.collect_news_tips(days=days)

    df = st.session_state.search_df
    if df.empty:
        st.caption(_L("no_tips"))
    else:
        arts = df.drop_duplicates(subset=["url"])
        st.markdown(f"**{len(arts)}** 篇文章 · **{len(df)}** {_L('col_mentions')}")
        st.dataframe(
            arts[["race_date", "tipster", "title", "source", "url"]],
            column_config={
                "title": st.column_config.TextColumn(_L("col_title"), width="large"),
                "tipster": st.column_config.TextColumn("Tipster"),
                "source": st.column_config.TextColumn(_L("col_source")),
                "url": st.column_config.LinkColumn(_L("col_link"), display_text="🔗"),
            },
            width="stretch",
            hide_index=True,
        )
        if st.button(_L("btn_save")):
            n = storage.save_tips(df)
            st.success(_L("manual_saved").format(n=n) if n else _L("updated_none"))

elif page == "nav_consensus":
    st.header(_L("nav_consensus"))
    st.caption(_L("consensus_desc"))
    if tips_all.empty:
        st.info(_L("no_tips"))
        st.stop()
    dates = sorted(tips_all["race_date"].dropna().unique(), reverse=True)
    pick = st.selectbox(_L("pick_by_date"), [_L("all_dates")] + list(dates))
    cons = analysis.consensus(tips_all, race_date=None if pick == _L("all_dates") else pick)
    if cons.empty:
        st.info(_L("no_tips"))
        st.stop()
    st.dataframe(
        cons[["race_date", "pick", "mentions", "n_sources", "tipsters"]],
        width="stretch",
        hide_index=True,
    )
    fig = px.bar(
        cons.head(20),
        x="pick",
        y="mentions",
        color="n_sources",
        hover_data=["tipsters", "race_date"],
        title="Top 20",
    )
    st.plotly_chart(fig, width="stretch")

elif page == "nav_analysis":
    st.header(_L("nav_analysis"))
    st.subheader(_L("analysis_source_title"))
    ss = analysis.source_stats(tips_all)
    if ss.empty:
        st.info(_L("no_tips"))
    else:
        st.dataframe(ss, width="stretch", hide_index=True)
        fig = px.bar(ss.head(15), x="source", y="tips", color="kind")
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader(_L("analysis_horse_title"))
    code = st.text_input(_L("horse_input"), value="A001", max_chars=8).strip().upper()
    if code:
        hf = _horse_form(code)
        if hf is None or hf.empty:
            st.warning(_L("horse_not_found"))
        else:
            placed = pd.to_numeric(hf["place"], errors="coerce")
            runs = placed.notna().sum()
            c1, c2, c3 = st.columns(3)
            c1.metric(_L("horse_runs_n"), int(runs))
            c2.metric(_L("horse_winrate"), f"{(placed == 1).sum() / max(runs, 1):.1%}")
            c3.metric(_L("horse_placerate"), f"{placed.between(1, 3).sum() / max(runs, 1):.1%}")
            st.dataframe(
                hf.head(12)[["date", "racecourse", "distance_m", "place", "jockey", "trainer", "rating", "draw"]],
                width="stretch",
                hide_index=True,
            )

elif page == "nav_past":
    st.header(_L("nav_past"))
    st.caption(_L("past_desc"))
    today = dt.date.today()
    days = data_hub.recent_race_days(today, 12)
    if not days:
        st.warning("fixtures unavailable")
        st.stop()
    day = st.selectbox(_L("past_pick_day"), [str(d) for d in days])
    res = _results(day)
    day_tips = tips_all[tips_all["race_date"] == day] if not tips_all.empty else pd.DataFrame()
    if res is None or res.empty or day_tips.empty:
        st.info(_L("past_no_tips"))
        st.stop()

    ev = analysis.evaluate(day_tips, res)
    if ev.empty:
        st.info(_L("past_no_tips"))
        st.stop()
    st.subheader(_L("past_overall"))
    st.dataframe(analysis.performance_table(ev, by=None), width="stretch")
    st.subheader(_L("past_by_source"))
    st.dataframe(analysis.performance_table(ev, by="source"), width="stretch", hide_index=True)
    st.subheader(_L("data_view"))
    show = ev[["race_no", "horse_no", "horse_name", "matched_horse", "source", "tipster", "place", "win_odds", "is_win"]]
    st.dataframe(show, width="stretch", hide_index=True)

elif page == "nav_data":
    st.header(_L("nav_data"))
    st.subheader(_L("data_view"))
    if tips_all.empty:
        st.info(_L("no_tips"))
    else:
        st.dataframe(tips_all, width="stretch", hide_index=True)
        st.download_button(
            _L("data_download_tips"),
            data=tips_all.to_csv(index=False).encode("utf-8-sig"),
            file_name="sporttips_tips.csv",
            mime="text/csv",
        )

    st.divider()
    st.subheader(_L("data_upload"))
    up = st.file_uploader(_L("data_upload"), type=["csv"])
    if up is not None:
        try:
            imp = pd.read_csv(up, dtype=str)
        except Exception:
            imp = pd.DataFrame()
        if not {"race_date", "horse_no"}.issubset(set(imp.columns)) and not {
            "race_date",
            "horse_name",
        }.issubset(set(imp.columns)):
            st.error(_L("upload_bad"))
        else:
            for col in tip_sources.TIPS_COLUMNS:
                if col not in imp.columns:
                    imp[col] = ""
            imp["kind"] = "import"
            imp["fetched_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            n = storage.save_tips(imp, manual=True)
            st.success(_L("uploaded_ok").format(n=n))

    st.divider()
    st.subheader(_L("data_manual"))
    st.caption(_L("manual_hint"))
    with st.form("manual_form"):
        c1, c2, c3 = st.columns(3)
        mdate = c1.date_input(_L("col_date"), value=dt.date.today())
        mrace = c2.number_input(_L("col_race"), 1, 12, 1)
        mpick = c3.text_input(_L("col_horse"), value="", help="e.g. 5 or 金勝名駒")
        c4, c5 = st.columns(2)
        msource = c4.text_input(_L("col_source"), value="Manual")
        mtipster = c5.text_input("Tipster", value="")
        mnote = st.text_input("Note", value="")
        submitted = st.form_submit_button(_L("btn_save"), type="primary")
    if submitted:
        if not mpick.strip():
            st.warning(_L("col_horse") + "?")
        else:
            pick = mpick.strip()
            is_num = pick.isdigit()
            row = pd.DataFrame(
                [
                    {
                        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "race_date": mdate.isoformat(),
                        "race_no": int(mrace),
                        "horse_no": int(pick) if is_num else "",
                        "horse_name": "" if is_num else pick,
                        "source": msource or "Manual",
                        "tipster": mtipster,
                        "title": "",
                        "url": "",
                        "kind": "manual",
                        "note": mnote,
                    }
                ]
            )
            n = storage.save_tips(row, manual=True)
            st.success(_L("manual_saved").format(n=n))

else:  # nav_about
    st.header(_L("nav_about"))
    st.subheader(_L("about_sources"))
    st.markdown(
        """
- **[星島頭條 · 馬經](https://www.stheadline.com/racing/馬經)** — 貼士專欄（亨利拆局、馬觀微、Dickson心水…），每條貼士都註明 tipster 同文章連結
- **[tianxi-database](https://github.com/sleepingarhat/tianxi-database)** — HKJC 排位(SpeedPro)、賽果、馬匹/騎練統計、賽期（公開 CSV/JSON，每日自動更新）
- **[HKJC 香港賽馬會](https://racing.hkjc.com)** — 官方數據版權持有人
        """
    )
