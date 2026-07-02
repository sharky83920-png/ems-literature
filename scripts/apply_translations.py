# -*- coding: utf-8 -*-
"""把翻譯結果（translations.json，pmid -> {title_zh, abstract_zh}）回填進 papers.json。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
db = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))
tr = json.loads((ROOT / "_translations.json").read_text(encoding="utf-8"))
by_pmid = {p.get("pmid"): p for p in db["papers"] if p.get("pmid")}
n = 0
for pmid, t in tr.items():
    p = by_pmid.get(pmid)
    if p:
        if t.get("title_zh"):
            p["title_zh"] = t["title_zh"]
        if t.get("abstract_zh"):
            p["abstract_zh"] = t["abstract_zh"]
        n += 1
db["papers"].sort(key=lambda p: p.get("date") or "", reverse=True)
(ROOT / "data" / "papers.json").write_text(
    json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"回填 {n} 篇翻譯，資料庫仍待翻譯 {sum(1 for p in db['papers'] if not p.get('title_zh'))} 篇")
