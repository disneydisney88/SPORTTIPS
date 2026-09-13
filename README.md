# 🏇 SPORTTIPS — 香港賽馬貼士綜合平台 / HK Racing Tips Aggregator

免費 · 開源 · 全自動 · 繁中/English 雙語
Free · Open source · Fully automated · Bilingual (繁中/English)

## 功能 / Features

| | 繁中 | English |
|---|---|---|
| 🧲 搵貼士 | 自動搜尋各大新聞／網站貼士，**註明來源**同連結 | Auto-search tips from news/web, **with source links** |
| 🧮 綜合貼士 | 統計所有來源提及每匹馬次數（熱門共識） | Consensus = mention counts across sources |
| 📊 分析 | 來源統計＋馬匹統計（勝率/上名率/近期出賽） | Source stats + horse stats (win/place rate, form) |
| 🕑 過去分析 | 儲存嘅貼士 vs 官方賽果：命中率＋ROI | Stored tips vs official results: hit rate + ROI |
| 💾 資料庫 | 所有貼士存 CSV，可匯入/匯出/手動輸入 | Tips stored in CSV; import/export/manual entry |
| ⚙️ 自動化 | GitHub Actions 每日自動搜尋＋更新 repo 數據 | GitHub Actions updates the repo data daily |

**全部免費**：HKJC 公開數據（[tianxi-database](https://github.com/sleepingarhat/tianxi-database) 提供 CSV）＋ Google News RSS ＋ DuckDuckGo，唔需要任何 API key。

## 部署到 Streamlit Cloud（免費）/ Deploy

1. [share.streamlit.io](https://share.streamlit.io) → **Deploy an app**
2. Repository: `disneydisney88/SPORTTIPS` · Branch: `master` · Main file: `streamlit_app.py`
3. 按 **Deploy** — 完成，網址會係 `https://<your-sub>.streamlit.app`

## 本機運行 / Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 自動更新 / Automation

- `.github/workflows/daily_update.yml`
  - 每日 08:30（香港時間）＋ 賽馬日（三/六/日）19:00 自動跑 `scripts/auto_fetch.py`
  - 搜尋 Google News 貼士 → 合併入 `data/tips.csv` → 自動 commit 返 repo
  - Streamlit Cloud 讀 repo 數據，所以雲端版都係最新

## 資料來源 / Data sources（鳴謝）

- [tianxi-database](https://github.com/sleepingarhat/tianxi-database) — HKJC 賽果、馬匹出賽紀錄、騎練統計、賽期表（公開 CSV）
- [Google News RSS](https://news.google.com/rss) — 新聞貼士搜尋
- [DuckDuckGo](https://duckduckgo.com) — 網頁搜尋
- [HKJC 香港賽馬會](https://racing.hkjc.com) — 官方數據版權持有人

## 免責聲明 / Disclaimer

⚠️ 所有貼士由公開來源自動收集並**註明來源**，只供研究參考，唔構成投注建議。請理性投注。
All tips are auto-collected from public sources with attribution, for research only — not betting advice. Bet responsibly.
