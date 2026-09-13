# -*- coding: utf-8 -*-
"""SPORTTIPS — free aggregated HK racing tips platform.

Bilingual (繁中/English), auto-updated tips from public news sources with
attribution, consensus statistics, horse stats, and past-performance analysis.
All data is free: HKJC public data via the open tianxi-database repo +
Google News RSS + DuckDuckGo. No API keys required.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st

from sporttips import analysis, data_hub, storage, tip_sources
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


def _L(key: str) -> str:
    return t(key, st.session_state.lang)


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
            new_tips = tip_sources.collect_news_tips(days=3)
            n = storage.save_tips(new_tips)
        if n:
            st.toast(_L("updated_ok").format(n=n), icon="✅")
        else:
            st.toast(_L("updated_none"), icon="ℹ️")
    tips_all = storage.load_tips()
    if not tips_all.empty:
        st.caption(f"{_L('col_date')}: {tips_all['fetched_at'].max()} · {len(tips_all)} rows")

# ------------------------------------------------------------------- pages --
if page == "nav_today":
    st.header(_L("nav_today"))
    today = dt.date.today()
    fx = _fixtures()
    if fx.empty:
        st.warning("fixtures data unavailable")
        st.stop()
    is_race_day = today in set(fx["date"])
    if is_race_day:
        st.success(_L("today_race_day"))
    else:
        nxt = data_hub.next_race_days(today, 3)
        st.info(f"{_L('today_no_race')} — {_L('today_next').format(d=', '.join(map(str, nxt)))}")

    st.subheader(_L("nav_search"))
    recent = data_hub.recent_race_days(today, 1)
    if recent:
        last_day = str(recent[0])
        res = _results(last_day)
        if res is not None and not res.empty:
            st.caption(f"{_L('today_recent').format(d=last_day)}")
            show = res[["race_no", "race_name", "place", "horse_no", "horse_name", "jockey", "win_odds"]]
            st.dataframe(show.head(60), width="stretch", hide_index=True)
        else:
            st.caption(_L("today_recent").format(d=last_day))

    st.subheader(_L("news_tips"))
    t_today = tips_all[tips_all["race_date"] == today.isoformat()] if not tips_all.empty else pd.DataFrame()
    if t_today.empty:
        st.caption(_L("no_tips"))
    else:
        cons = analysis.consensus(tips_all, race_date=today.isoformat())
        st.dataframe(
            cons[["pick", "mentions", "n_sources", "sources"]],
            width="stretch",
            hide_index=True,
        )

elif page == "nav_search":
    st.header(_L("nav_search"))
    c1, c2 = st.columns([1, 3])
    days = c1.slider(_L("search_days"), 1, 7, 3)
    scopes = c2.multiselect(_L("search_scope"), [_L("scope_news"), _L("scope_web")], default=[_L("scope_news")])

    if "search_df" not in st.session_state:
        st.session_state.search_df = pd.DataFrame()
    if "web_df" not in st.session_state:
        st.session_state.web_df = pd.DataFrame()

    if st.button(_L("btn_fetch"), type="primary"):
        if _L("scope_news") in scopes:
            with st.spinner("Google News ..."):
                st.session_state.search_df = tip_sources.collect_news_tips(days=days)
        if _L("scope_web") in scopes:
            with st.spinner("DuckDuckGo ..."):
                st.session_state.web_df = tip_sources.collect_web_results()

    if st.session_state.search_df.empty and st.session_state.web_df.empty:
        st.caption(_L("no_tips"))
    else:
        if not st.session_state.search_df.empty:
            news = st.session_state.search_df.drop_duplicates(subset=["url"])
            st.markdown(f"**Google News — {len(news)} items**")
            st.dataframe(
                news[["title", "source", "url"]],
                column_config={
                    "title": st.column_config.TextColumn(_L("col_title"), width="large"),
                    "source": st.column_config.TextColumn(_L("col_source")),
                    "url": st.column_config.LinkColumn(_L("col_link"), display_text="🔗"),
                },
                width="stretch",
                hide_index=True,
            )
            parsed = st.session_state.search_df
            st.markdown(f"**{len(parsed)}** × {_L('col_horse')}")
            if st.button(_L("btn_save")):
                n = storage.save_tips(parsed)
                st.success(_L("manual_saved").format(n=n) if n else _L("updated_none"))
        if not st.session_state.web_df.empty:
            st.markdown(f"**DuckDuckGo — {len(st.session_state.web_df)} items**")
            st.dataframe(
                st.session_state.web_df[["title", "source", "url"]],
                column_config={
                    "title": st.column_config.TextColumn(_L("col_title"), width="large"),
                    "url": st.column_config.LinkColumn(_L("col_link"), display_text="🔗"),
                },
                width="stretch",
                hide_index=True,
            )

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
        cons[["race_date", "pick", "mentions", "n_sources", "sources", "tipsters"]],
        width="stretch",
        hide_index=True,
    )
    fig = px.bar(
        cons.head(20),
        x="pick",
        y="mentions",
        color="n_sources",
        hover_data=["sources", "race_date"],
        title="Top 20 consensus picks",
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
    if res is None or res.empty:
        st.warning(_L("past_no_tips"))
        st.stop()
    if day_tips.empty:
        st.info(_L("past_no_tips"))
        st.stop()

    ev = analysis.evaluate(day_tips, res)
    if ev.empty:
        st.info(_L("past_no_tips"))
        st.stop()
    st.subheader(_L("past_overall"))
    st.dataframe(analysis.performance_table(ev, by=None), width="stretch")
    st.subheader(_L("past_by_source"))
    st.dataframe(analysis.performance_table(ev, by="source"), width="stretch")
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
        f"""
- **[tianxi-database](https://github.com/sleepingarhat/tianxi-database)** — {_L("footer_src")}: HKJC 賽果/馬匹/騎練統計 CSV（免費公開，每日自動更新）
- **Google News RSS** — 新聞貼士搜尋（免費，註明來源）
- **DuckDuckGo** — 網頁搜尋（免費）
- **HKJC** — [racing.hkjc.com](https://racing.hkjc.com) 官方數據
        """
    )
    st.subheader(_L("about_auto"))
    st.markdown(_L("about_auto_body"))
    st.code(
        """.github/workflows/daily_update.yml
cron: 00:30 UTC (08:30 HK) + 11:00 UTC (19:00 HK)
python scripts/auto_fetch.py → commit data/tips.csv""",
        language="yaml",
    )
    st.warning(_L("about_disclaimer"))
