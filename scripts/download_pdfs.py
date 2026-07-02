# -*- coding: utf-8 -*-
"""把 Open Access 文獻的 PDF 備份到 Google Drive 資料夾。
用法:
  python scripts/download_pdfs.py            # 只抓還沒下載過的（每週增量用）
  python scripts/download_pdfs.py --max 100  # 最多抓 100 篇（測試/分批用）
檔名: {PMID或DOI安全化}.pdf，存到 DEST。
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = Path(r"G:\我的雲端硬碟\EMS文獻庫\PDF")
UA = "ems-literature-bot/1.0 (mailto:sharky83920@gmail.com)"


def safe_name(p):
    base = p.get("pmid") and f"pmid-{p['pmid']}" or re.sub(r"[^a-z0-9.-]+", "_", p.get("doi", ""))
    return (base or "untitled")[:120] + ".pdf"


def pdf_url(p):
    if p.get("pmcid"):
        return f"https://europepmc.org/articles/{p['pmcid']}?pdf=render"
    u = p.get("oa_pdf", "")
    return u if u else None


def main():
    max_n = None
    if "--max" in sys.argv:
        max_n = int(sys.argv[sys.argv.index("--max") + 1])
    db = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))
    DEST.mkdir(parents=True, exist_ok=True)
    todo = []
    for p in db["papers"]:
        if not (p.get("pmcid") or p.get("oa_pdf")):
            continue
        f = DEST / safe_name(p)
        if not f.exists():
            todo.append((p, f))
    if max_n:
        todo = todo[:max_n]
    print(f"待下載 {len(todo)} 篇")
    ok = fail = 0
    for p, f in todo:
        url = pdf_url(p)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if data[:5] == b"%PDF-":
                f.write_bytes(data)
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        time.sleep(1.0)
        if (ok + fail) % 25 == 0:
            print(f"  進度 {ok + fail}/{len(todo)}（成功 {ok}）")
    print(f"[完成] 成功 {ok} 篇，失敗/非OA {fail} 篇，存放於 {DEST}")


if __name__ == "__main__":
    main()
