# EMS 文獻庫

緊急醫療救護（EMS）文獻自動搜索資料庫。每週自動搜尋 PubMed、Europe PMC、Semantic Scholar，
以中英雙語網站呈現：https://sharky83920-png.github.io/ems-literature/

## 架構

```
關鍵字（keywords.json，網頁可管理）
  → GitHub Actions 每週一 06:00（台灣時間）自動搜索
  → data/papers.json（書目資料庫）
  → GitHub Pages 網站（中英即搜、標籤篩選）
```

- `scripts/search.py` — 搜索引擎（純標準函式庫，`python scripts/search.py --backfill` 回溯建庫）
- `keywords.json` — 搜尋關鍵字設定
- `data/papers.json` — 文獻資料庫；`data/inbox.json` — 手動收錄待處理清單
- `translations/` — 全文中文翻譯網頁
- `index.html` + `app.js` — 網站

## 翻譯流程（由 Claude 對話執行，不用 API）

- **每週補翻**：對 Claude 說「幫我翻譯文獻庫的新文章」→ 補 `title_zh`、`abstract_zh`
- **全文翻譯**：網站卡片按「申請全文翻譯」→ 複製指令貼給 Claude → 產出 `translations/pmid-XXXX.html`，
  並把該篇的 `translation` 欄位填上路徑。圖表保留原圖＋中文圖說，AI 解讀需標示。

維護細節見 vault：`工具欄/EMS文獻庫維護手冊.md`
