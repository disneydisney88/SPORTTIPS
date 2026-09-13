# 🏇 SPORTTIPS — 香港賽馬貼士綜合平台 / HK Racing Tips Aggregator

免費 · 開源 · 全自動 · 繁中/English 雙語
Free · Open source · Fully automated · Bilingual (繁中/English)

## 功能 / Features

| | 繁中 | English |
|---|---|---|
| 🏠 今日賽事 | 今日排位**逐場**顯示：每匹馬馬號/馬名/檔位/SpeedPro能量＋貼士標記⭐ | Today's card race-by-race: runner no./name/draw/energy + tips⭐ |
| 🧲 搵貼士 | 星島頭條馬經專欄貼士，**註明 tipster 同來源連結** | ST Headline tipster columns, **with tipster + source links** |
| 🧮 綜合貼士 | 統計所有來源提及每匹馬次數（熱門共識） | Consensus = mention counts across sources |
| 📊 分析 | 來源統計＋馬匹統計（勝率/上名率/近期出賽） | Source stats + horse stats (win/place rate, form) |
| 🕑 過去分析 | 儲存嘅貼士 vs 官方賽果：命中率＋ROI | Stored tips vs official results: hit rate + ROI |
| 💾 資料庫 | 所有貼士存 CSV，可匯入/匯出/手動輸入 | Tips stored in CSV; import/export/manual entry |

**全部免費**：HKJC 公開數據（[tianxi-database](https://github.com/sleepingarhat/tianxi-database) 提供 SpeedPro 排位/賽果/馬匹 CSV）＋ [星島頭條馬經](https://www.stheadline.com/racing/馬經) RSS，唔需要任何 API key。

**真自動**：開網頁就自動更新貼士（45 分鐘節流）；GitHub Actions 每日再 commit 資料入 repo，Streamlit Cloud 永遠有最新數據。

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

- **開網頁自動更新**：每次開 app 自動抓最新星島貼士（45 分鐘節流，靜默執行）
- `.github/workflows/daily_update.yml`：每日 08:30（香港時間）＋賽馬日（三/六/日）19:00 自動跑 `scripts/auto_fetch.py` → commit `data/tips.csv`

## 資料來源 / Data sources（鳴謝）

- [tianxi-database](https://github.com/sleepingarhat/tianxi-database) — HKJC SpeedPro 排位、賽果、馬匹出賽紀錄、騎練統計、賽期表
- [星島頭條 · 馬經](https://www.stheadline.com/racing/馬經) — 貼士專欄（公開 RSS）
- [HKJC 香港賽馬會](https://racing.hkjc.com) — 官方數據版權持有人

## 免責聲明 / Disclaimer

⚠️ 所有貼士由公開來源自動收集並**註明來源**，只供研究參考，唔構成投注建議。請理性投注。
All tips are auto-collected from public sources with attribution, for research only — not betting advice. Bet responsibly.
