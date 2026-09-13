# -*- coding: utf-8 -*-
"""SPORTTIPS — free HK racing tips platform (繁中/English).

Tips: 東網馬經 (structured picks w/ race+horse numbers) + 星島頭條 tipster
columns — always attributed. Race cards: free HKJC SpeedPro data. Past
records & jockey-horse combos: tianxi-database form records. Data refreshes
when the page opens; GitHub Actions keeps the repo store fresh daily.
"""
from __future__ import annotations

import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor

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


@st.cache_data(ttl=3600, show_spinner=False)
def _jockey_profiles() -> pd.DataFrame:
    return data_hub.jockey_profiles()


@st.cache_data(ttl=1800, show_spinner=False)
def _race_card(day: str) -> dict | None:
    return data_hub.race_card(day)


@st.cache_data(ttl=900, show_spinner=False)
def _remote_tips() -> pd.DataFrame:
    return data_hub.remote_tips()


@st.cache_data(ttl=21600, show_spinner=False)
def _form_summaries(day: str, brandnos: tuple[str, ...]) -> dict:
    """Per-horse career summary + jockey combo, fetched in parallel."""
    def one(b: str):
        s = data_hub.horse_form_summary(b)
        combo = data_hub.jockey_combo(b, s.get("last_jockey", "")) if s else {}
        return b, {"sum": s, "combo": combo}

    with ThreadPoolExecutor(16) as ex:
        return dict(ex.map(one, brandnos))


def _L(key: str) -> str:
    return t(key, st.session_state.lang)


def _auto_update() -> None:
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
remote = _remote_tips()
if not remote.empty:
    tips_all = (
        pd.concat([tips_all, remote], ignore_index=True)
        .drop_duplicates(
            subset=["url", "race_date", "race_no", "horse_no", "horse_name", "source", "tipster", "kind"],
            keep="last",
        )
    )

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
    page = st.radio("PAGE", PAGES, format_func=lambda k: _L(k), label_visibility="collapsed", key="page")

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


def _tip_maps(day_iso: str) -> tuple[dict, dict]:
    """(number_map, name_map) for tips within ±1 day of the card date."""
    d0 = dt.date.fromisoformat(day_iso)
    keys = {(d0 - dt.timedelta(days=1)).isoformat(), d0.isoformat(), (d0 + dt.timedelta(days=1)).isoformat()}
    num_map: dict[tuple[str, str], list[str]] = {}
    name_map: dict[str, list[str]] = {}
    if tips_all.empty:
        return num_map, name_map
    for _, r in tips_all[tips_all["race_date"].isin(keys)].iterrows():
        who = str(r.get("tipster") or r.get("source") or "").strip()
        if not who:
            continue
        rn = str(r.get("race_no") or "").strip().replace(".0", "")
        hn = str(r.get("horse_no") or "").strip().replace(".0", "")
        nm = norm_name(r.get("horse_name", ""))
        if rn and hn:
            num_map.setdefault((rn, hn), [])
            if who not in num_map[(rn, hn)]:
                num_map[(rn, hn)].append(who)
        if nm:
            name_map.setdefault(nm, [])
            if who not in name_map[nm]:
                name_map[nm].append(who)
    return num_map, name_map


def _card_dates() -> list[str]:
    today = dt.date.today()
    dates = [today] + data_hub.next_race_days(today, 3) + data_hub.recent_race_days(today, 2)
    seen, out = set(), []
    for d in dates:
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if iso not in seen:
            seen.add(iso)
            out.append(iso)
    return out


def _fmt_record(s: dict) -> str:
    if not s:
        return "—"
    last5 = "-".join(str(p) for p in s.get("last5", []))
    base = f"{s['runs']}{_L('runs_unit')} {s['wins']}{_L('win_unit')}{s['places'] - s['wins']}{_L('place_unit')}"
    return f"{base}\n{last5} · {s.get('best_dist','')}"


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

    card, card_day = None, ""
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
        num_map, name_map = _tip_maps(card_day)
        day_tips = tips_all[tips_all["race_date"].isin(
            {(dt.date.fromisoformat(card_day) - dt.timedelta(days=1)).isoformat(), card_day,
             (dt.date.fromisoformat(card_day) + dt.timedelta(days=1)).isoformat()}
        )] if not tips_all.empty else pd.DataFrame()

        c1, c2, c3 = st.columns(3)
        c1.metric(_L("metric_races"), len(card["races"]))
        c2.metric(_L("metric_tips"), len(day_tips))
        c3.metric(_L("metric_tipsters"), day_tips["tipster"].nunique() if not day_tips.empty else 0)

        brandnos = tuple(
            str(r.get("brandno") or "").strip().upper()
            for race in card["races"] for r in race.get("energy", [])
            if str(r.get("brandno") or "").strip()
        )
        summaries = _form_summaries(card_day, tuple(sorted(set(brandnos))))

        for race in card["races"]:
            info = race.get("raceinfo_chi") or race.get("raceinfo_eng") or {}
            en = st.session_state.lang == "en"
            rname = (race.get("raceinfo_eng") or info).get("RaceName", "") if en else info.get("RaceName", "")
            raceno = str(race.get("raceno", "?"))
            label = _L("race_x").format(
                n=race.get("raceno", "?"),
                name=rname, dist=info.get("Distance", ""), cls=info.get("RaceClass", ""),
                time=info.get("PostTime", ""),
            )
            runners = [r for r in race.get("energy", []) if not r.get("scratched")]

            # per-tipster picks line for this race (from numbered tips)
            tip_lines = []
            race_tips = day_tips[day_tips["race_no"].astype(str).str.replace(".0", "", regex=False) == raceno] if not day_tips.empty else pd.DataFrame()
            if not race_tips.empty:
                for tipster, g in race_tips.groupby("tipster"):
                    picks = []
                    for _, rr in g.iterrows():
                        hn = rr.get("horse_no")
                        if pd.notna(hn) and str(hn).strip():
                            nm = str(rr.get("horse_name") or "").strip()
                            picks.append(f"{int(float(hn))} {nm}".strip())
                    if picks:
                        tip_lines.append(f"**{tipster}**: " + "、".join(picks))

            rows = []
            for r in runners:
                brand = str(r.get("brandno") or "").strip().upper()
                nm_chi = str(r.get("name_chi") or "").strip()
                nm_en = str(r.get("name_eng") or r.get("name") or "").strip()
                display_name = nm_en if en else nm_chi
                who = list(num_map.get((raceno, str(r.get("runnernumber")).strip()), []))
                who += [w for w in name_map.get(norm_name(nm_chi), []) if w not in who]
                if not en and who:
                    display_name = f"⭐ {display_name}"

                fs = summaries.get(brand, {}).get("sum", {})
                combo = summaries.get(brand, {}).get("combo", {})
                if fs:
                    record = _fmt_record(fs)
                    last_jockey = fs.get("last_jockey", "")
                    combo_txt = (
                        f"{combo['runs']}{_L('runs_unit')}{combo['wins']}{_L('win_unit')}{combo['places'] - combo['wins']}{_L('place_unit')}"
                        if combo else "—"
                    )
                else:
                    record, last_jockey, combo_txt = "—", "—", "—"
                try:
                    energy = int(str(r.get("speedproenergy") or "0").strip() or 0)
                except ValueError:
                    energy = 0
                rows.append({
                    _L("col_runner"): r.get("runnernumber"),
                    _L("col_horse2"): display_name,
                    _L("col_draw"): r.get("draw"),
                    _L("col_energy"): energy,
                    _L("col_diff"): r.get("speedproenergydifference"),
                    _L("col_fitness"): r.get("fitnessrating"),
                    _L("col_record"): record,
                    _L("col_last_jockey"): last_jockey,
                    _L("col_combo"): combo_txt,
                    _L("col_tips"): "、".join(who),
                })

            has_tips = bool(tip_lines)
            with st.expander(label, expanded=has_tips):
                if tip_lines:
                    st.markdown(("🎯 " + "　|　".join(tip_lines)))
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
        with st.spinner("東網馬經 · 星島頭條 ..."):
            st.session_state.search_df = tip_sources.collect_news_tips(days=days)

    df = st.session_state.search_df
    if df.empty:
        st.info(_L("search_fallback"))
        if not tips_all.empty:
            arts = tips_all.drop_duplicates(subset=["url"])
            st.dataframe(
                arts[["race_date", "tipster", "title", "source", "url"]].head(50),
                column_config={
                    "title": st.column_config.TextColumn(_L("col_title"), width="large"),
                    "tipster": st.column_config.TextColumn("Tipster"),
                    "source": st.column_config.TextColumn(_L("col_source")),
                    "url": st.column_config.LinkColumn(_L("col_link"), display_text="🔗"),
                },
                width="stretch",
                hide_index=True,
            )
    else:
        arts = df.drop_duplicates(subset=["url"])
        st.markdown(f"**{len(arts)}** 篇 · **{len(df)}** {_L('col_mentions')}")
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
    fig = px.bar(cons.head(20), x="pick", y="mentions", color="n_sources",
                 hover_data=["tipsters", "race_date"], title="Top 20")
    st.plotly_chart(fig, width="stretch")

elif page == "nav_analysis":
    st.header(_L("nav_analysis"))

    st.subheader(_L("tipster_title"))
    if tips_all.empty:
        st.info(_L("no_tips"))
    else:
        ts = (
            tips_all.groupby("tipster")
            .agg(source=("source", "first"), tips=("url", "count"), days=("race_date", "nunique"))
            .reset_index()
            .sort_values("tips", ascending=False)
        )
        st.dataframe(ts, width="stretch", hide_index=True)

    st.divider()
    st.subheader(_L("jockey_title"))
    jp = _jockey_profiles()
    if not jp.empty:
        show = jp.head(20)[["jockey", "rides", "win_cnt", "win_pct", "place_pct"]].copy()
        show.columns = [_L("col_jockey"), _L("col_rides"), _L("col_wins"), _L("col_winpct"), _L("col_placepct")]
        st.dataframe(show, width="stretch", hide_index=True)

    st.divider()
    st.subheader(_L("analysis_source_title"))
    ss = analysis.source_stats(tips_all)
    if not ss.empty:
        st.dataframe(ss, width="stretch", hide_index=True)

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
    st.subheader(_L("past_by_tipster"))
    st.dataframe(analysis.performance_table(ev, by="tipster"), width="stretch", hide_index=True)
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
            "race_date", "horse_name",
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
            row = pd.DataFrame([{
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
            }])
            n = storage.save_tips(row, manual=True)
            st.success(_L("manual_saved").format(n=n))

else:  # nav_about
    st.header(_L("nav_about"))
    st.subheader(_L("about_sources"))
    st.markdown(
        """
- **[東網馬經 racing.on.cc](https://racing.on.cc/)** — 名家推介／西門獨／諸葛數／兆文 等貼士（有場次＋馬號）
- **[星島頭條 · 馬經](https://www.stheadline.com/racing/馬經)** — 亨利拆局、馬觀微、Dickson心水 等專欄
- **[tianxi-database](https://github.com/sleepingarhat/tianxi-database)** — HKJC SpeedPro 排位、賽果、馬匹出賽紀錄、騎師統計、賽期
- **[HKJC 香港賽馬會](https://racing.hkjc.com)** — 官方數據版權持有人
        """
    )
