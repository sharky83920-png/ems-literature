# -*- coding: utf-8 -*-
"""EMS 文獻自動搜索引擎
讀 keywords.json -> 搜 PubMed / Europe PMC / Semantic Scholar -> 去重合併進 data/papers.json
用法:
  python scripts/search.py            # 增量模式(從上次執行日往前推14天)
  python scripts/search.py --backfill # 回溯模式(依 settings.backfill_years)
只用標準函式庫，本機與 GitHub Actions 都能直接跑。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONTACT = "sharky83920@gmail.com"
UA = f"ems-literature-bot/1.0 (mailto:{CONTACT})"


def http_json(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == retries - 1:
                print(f"  [warn] {url[:120]} -> {e}")
                return None
            time.sleep(2 * (i + 1))


def http_text(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            if i == retries - 1:
                print(f"  [warn] {url[:120]} -> {e}")
                return None
            time.sleep(2 * (i + 1))


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())[:120]


def norm_doi(d):
    if not d:
        return ""
    d = d.strip().lower()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d)
    return d


def load_db():
    f = DATA / "papers.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {"updated": "", "papers": []}


def save_db(db):
    DATA.mkdir(exist_ok=True)
    db["updated"] = date.today().isoformat()
    db["papers"].sort(key=lambda p: p.get("date") or "", reverse=True)
    (DATA / "papers.json").write_text(
        json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")


def build_indexes(papers):
    by_pmid, by_doi, by_title = {}, {}, {}
    for p in papers:
        if p.get("pmid"):
            by_pmid[p["pmid"]] = p
        if p.get("doi"):
            by_doi[norm_doi(p["doi"])] = p
        tkey = norm_title(p.get("title"))
        if len(tkey) > 15:
            by_title[tkey] = p
    return by_pmid, by_doi, by_title


def merge_paper(db_idx, papers, new):
    """去重合併：已存在就補欄位，不存在就新增。回傳是否為新文獻。"""
    by_pmid, by_doi, by_title = db_idx
    old = None
    tkey = norm_title(new.get("title"))
    if new.get("pmid") and new["pmid"] in by_pmid:
        old = by_pmid[new["pmid"]]
    elif new.get("doi") and norm_doi(new["doi"]) in by_doi:
        old = by_doi[norm_doi(new["doi"])]
    elif len(tkey) > 15 and tkey in by_title:
        old = by_title[tkey]
    if old:
        for k in ("pmid", "doi", "pmcid", "abstract", "journal", "date",
                  "authors", "oa_pdf", "url"):
            if new.get(k) and not old.get(k):
                old[k] = new[k]
        for t in new.get("tags", []):
            if t not in old.setdefault("tags", []):
                old["tags"].append(t)
        for s in new.get("sources", []):
            if s not in old.setdefault("sources", []):
                old["sources"].append(s)
        return False
    papers.append(new)
    if new.get("pmid"):
        by_pmid[new["pmid"]] = new
    if new.get("doi"):
        by_doi[norm_doi(new["doi"])] = new
    if len(tkey) > 15:
        by_title[tkey] = new
    return True


def new_record(tag, source):
    return {
        "pmid": "", "doi": "", "pmcid": "",
        "title": "", "title_zh": "",
        "abstract": "", "abstract_zh": "",
        "journal": "", "date": "", "authors": "",
        "tags": [tag] if tag else [],
        "sources": [source],
        "oa_pdf": "", "url": "",
        "translation": "",
        "added": date.today().isoformat(),
    }


def clip(text, n=1800):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:n] + ("…" if len(text) > n else "")


# ---------------- 院前救護情境詞（用於精準過濾，避免撈到獸醫/院內等不相干文獻）----------------
CONTEXT_TERMS = ["prehospital", "pre-hospital", "out-of-hospital", "out of hospital",
                 "emergency medical services", "emergency medical service",
                 "paramedic", "paramedics", "ambulance", "emergency medical technician",
                 "first responder", "emergency medical dispatch"]
CONTEXT_RE = re.compile("|".join(re.escape(t) for t in CONTEXT_TERMS), re.I)


def is_relevant(r):
    """守門：標題＋摘要必須出現院前救護情境詞，否則剔除（獸醫、院內、基礎科學等）。"""
    return bool(CONTEXT_RE.search((r.get("title", "") + " " + r.get("abstract", ""))))


# ---------------- PubMed ----------------
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def pubmed_search(query, date_from, cap):
    topic = f'"{query}"[Title/Abstract]' if " " in query else f'{query}[Title/Abstract]'
    term = (f"({topic}) AND ({CTX_PM}) AND (english[Language])"
            f" AND (\"{date_from}\"[Date - Publication] : \"3000\"[Date - Publication])")
    url = (f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&sort=pub_date"
           f"&retmax={cap}&term={urllib.parse.quote(term)}")
    j = http_json(url)
    if not j:
        return [], 0
    res = j.get("esearchresult", {})
    total = int(res.get("count", 0))
    return res.get("idlist", []), total


def pubmed_fetch(pmids):
    """efetch 批次抓詳細資料，回傳 record dict list（不含 tag）"""
    out = []
    for i in range(0, len(pmids), 100):
        chunk = pmids[i:i + 100]
        url = f"{EUTILS}/efetch.fcgi?db=pubmed&retmode=xml&id={','.join(chunk)}"
        xml_text = http_text(url)
        time.sleep(0.4)
        if not xml_text:
            continue
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            continue
        for art in root.findall(".//PubmedArticle"):
            r = new_record(None, "pubmed")
            r["pmid"] = (art.findtext(".//PMID") or "").strip()
            r["title"] = clip("".join((art.find(".//ArticleTitle") is not None and
                                       ET.tostring(art.find(".//ArticleTitle"), encoding="unicode", method="text")) or ""), 500)
            abst = [ET.tostring(a, encoding="unicode", method="text")
                    for a in art.findall(".//Abstract/AbstractText")]
            r["abstract"] = clip(" ".join(abst))
            r["journal"] = (art.findtext(".//Journal/ISOAbbreviation")
                            or art.findtext(".//Journal/Title") or "").strip()
            y = art.findtext(".//ArticleDate/Year") or art.findtext(".//JournalIssue/PubDate/Year") or ""
            m = art.findtext(".//ArticleDate/Month") or art.findtext(".//JournalIssue/PubDate/Month") or "01"
            d = art.findtext(".//ArticleDate/Day") or "01"
            months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                      "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
            m = months.get(m[:3].lower(), m if m.isdigit() else "01")
            if y:
                r["date"] = f"{y}-{int(m):02d}-{int(d):02d}"
            for aid in art.findall(".//ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    r["doi"] = norm_doi(aid.text)
                if aid.get("IdType") == "pmc":
                    r["pmcid"] = (aid.text or "").strip()
            first = art.find(".//AuthorList/Author")
            if first is not None:
                ln = first.findtext("LastName") or first.findtext("CollectiveName") or ""
                ini = first.findtext("Initials") or ""
                n_auth = len(art.findall(".//AuthorList/Author"))
                r["authors"] = f"{ln} {ini}".strip() + (" 等" if n_auth > 1 else "")
            r["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/"
            if r["pmcid"]:
                r["oa_pdf"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{r['pmcid']}/"
            out.append(r)
    return out


# ---------------- Europe PMC ----------------
def europepmc_search(query, date_from, cap, tag):
    topic = f'(TITLE:"{query}" OR ABSTRACT:"{query}")'
    q = f"{topic} AND ({CTX_EU}) AND LANG:eng AND FIRST_PDATE:[{date_from} TO 3000-12-31]"
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
           f"query={urllib.parse.quote(q)}&format=json&resultType=core"
           f"&sort={urllib.parse.quote('P_PDATE_D desc')}&pageSize={min(cap, 1000)}")
    j = http_json(url)
    out, total = [], 0
    if not j:
        return out, total
    total = j.get("hitCount", 0)
    for it in j.get("resultList", {}).get("result", [])[:cap]:
        r = new_record(tag, "europepmc")
        r["pmid"] = str(it.get("pmid", "") or "")
        r["doi"] = norm_doi(it.get("doi", ""))
        r["pmcid"] = it.get("pmcid", "") or ""
        r["title"] = clip(it.get("title", ""), 500)
        r["abstract"] = clip(it.get("abstractText", ""))
        r["journal"] = (it.get("journalInfo", {}).get("journal", {}).get("isoabbreviation")
                        or it.get("journalTitle", "") or "")
        r["date"] = it.get("firstPublicationDate", "") or ""
        a = it.get("authorString", "")
        r["authors"] = (a.split(",")[0] + (" 等" if "," in a else "")) if a else ""
        if r["pmid"]:
            r["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/"
        elif r["doi"]:
            r["url"] = f"https://doi.org/{r['doi']}"
        if it.get("isOpenAccess") == "Y" and r["pmcid"]:
            r["oa_pdf"] = f"https://europepmc.org/articles/{r['pmcid']}"
        out.append(r)
    return out, total


# ---------------- Semantic Scholar (盡力而為，掛了不影響主流程) ----------------
def s2_search(query, year_from, cap, tag):
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?"
           f"query={urllib.parse.quote(query + ' prehospital emergency medical services')}"
           f"&year={year_from}-&limit={min(cap, 100)}"
           "&fields=title,abstract,externalIds,venue,publicationDate,authors,openAccessPdf")
    j = http_json(url, retries=1)
    time.sleep(1.2)
    out = []
    if not j:
        return out
    for it in j.get("data", []) or []:
        ext = it.get("externalIds") or {}
        r = new_record(tag, "semanticscholar")
        r["pmid"] = str(ext.get("PubMed", "") or "")
        r["doi"] = norm_doi(ext.get("DOI", ""))
        r["title"] = clip(it.get("title", ""), 500)
        r["abstract"] = clip(it.get("abstract", ""))
        r["journal"] = it.get("venue", "") or ""
        r["date"] = it.get("publicationDate") or ""
        auths = it.get("authors") or []
        if auths:
            r["authors"] = auths[0].get("name", "") + (" 等" if len(auths) > 1 else "")
        oa = it.get("openAccessPdf") or {}
        r["oa_pdf"] = oa.get("url", "") or ""
        if r["pmid"]:
            r["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/"
        elif r["doi"]:
            r["url"] = f"https://doi.org/{r['doi']}"
        out.append(r)
    return out


# ---------------- 手動收錄 inbox ----------------
def resolve_inbox_item(value):
    value = value.strip()
    m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", value)
    if m:
        value = m.group(1)
    if re.fullmatch(r"\d{6,9}", value):
        recs = pubmed_fetch([value])
        return recs[0] if recs else None
    doi = norm_doi(value)
    if doi.startswith("10."):
        ids, _ = pubmed_search_raw(f"\"{doi}\"[DOI]")
        if ids:
            recs = pubmed_fetch(ids[:1])
            if recs:
                return recs[0]
        j = http_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")
        if j and j.get("message"):
            msg = j["message"]
            r = new_record(None, "crossref")
            r["doi"] = doi
            r["title"] = clip(" ".join(msg.get("title", [])), 500)
            r["abstract"] = clip(re.sub(r"<[^>]+>", " ", msg.get("abstract", "")))
            r["journal"] = " ".join(msg.get("container-title", [])[:1])
            parts = (msg.get("issued", {}).get("date-parts") or [[None]])[0]
            if parts and parts[0]:
                r["date"] = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts))
            au = msg.get("author") or []
            if au:
                r["authors"] = f"{au[0].get('family','')} {au[0].get('given','')[:1]}".strip() + (" 等" if len(au) > 1 else "")
            r["url"] = f"https://doi.org/{doi}"
            return r
    return None


def pubmed_search_raw(term):
    url = (f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&retmax=5"
           f"&term={urllib.parse.quote(term)}")
    j = http_json(url)
    if not j:
        return [], 0
    res = j.get("esearchresult", {})
    return res.get("idlist", []), int(res.get("count", 0))


# ---------------- Unpaywall OA 補查 ----------------
def enrich_oa(papers, limit=400):
    todo = [p for p in papers if p.get("doi") and not p.get("oa_pdf")][:limit]
    print(f"[OA] Unpaywall 補查 {len(todo)} 篇…")
    for p in todo:
        j = http_json(f"https://api.unpaywall.org/v2/{urllib.parse.quote(p['doi'], safe='/')}?email={CONTACT}", retries=1)
        time.sleep(0.15)
        if j and j.get("best_oa_location"):
            loc = j["best_oa_location"]
            p["oa_pdf"] = loc.get("url_for_pdf") or loc.get("url") or ""


# ---------------- 主流程 ----------------
def main():
    global CTX_PM, CTX_EU
    backfill = "--backfill" in sys.argv
    kw = json.loads((ROOT / "keywords.json").read_text(encoding="utf-8"))
    CTX_PM = " OR ".join(f'"{t}"[Title/Abstract]' if " " in t else f'{t}[Title/Abstract]'
                         for t in CONTEXT_TERMS)
    CTX_EU = " OR ".join(f'(TITLE:"{t}" OR ABSTRACT:"{t}")' for t in CONTEXT_TERMS)
    cap = kw["settings"].get("max_per_query", 300)
    db = load_db()
    papers = db["papers"]
    idx = build_indexes(papers)
    state_f = DATA / "state.json"
    state = json.loads(state_f.read_text(encoding="utf-8")) if state_f.exists() else {}

    if backfill:
        date_from = (date.today() - timedelta(days=365 * kw["settings"].get("backfill_years", 5))).isoformat()
    else:
        last = state.get("last_run", (date.today() - timedelta(days=14)).isoformat())
        date_from = (date.fromisoformat(last) - timedelta(days=14)).isoformat()
    date_from_pm = date_from.replace("-", "/")
    print(f"[搜索] 起始日期 {date_from}（{'回溯' if backfill else '增量'}模式）")

    n_new = 0
    n_filtered = 0
    for g in kw["groups"]:
        tag = g["tag"]
        for q in g["queries"]:
            ids, total = pubmed_search(q, date_from_pm, cap)
            dropped = max(0, total - len(ids))
            print(f"[PubMed] {tag} / {q}: 取 {len(ids)} 篇" + (f"（總數 {total}，容量限制略過 {dropped} 篇較舊的）" if dropped else ""))
            recs = pubmed_fetch(ids)
            for r in recs:
                if not is_relevant(r):
                    n_filtered += 1
                    continue
                r["tags"] = [tag]
                if merge_paper(idx, papers, r):
                    n_new += 1
            time.sleep(0.4)

            eu, eu_total = europepmc_search(q, date_from, cap, tag)
            print(f"[EuropePMC] {tag} / {q}: 取 {len(eu)} 篇（總數 {eu_total}）")
            for r in eu:
                if not is_relevant(r):
                    n_filtered += 1
                    continue
                if merge_paper(idx, papers, r):
                    n_new += 1
            time.sleep(0.3)

            for r in s2_search(q, date_from[:4], cap, tag):
                if not is_relevant(r):
                    n_filtered += 1
                    continue
                if merge_paper(idx, papers, r):
                    n_new += 1

    # 手動收錄
    inbox_f = DATA / "inbox.json"
    if inbox_f.exists():
        inbox = json.loads(inbox_f.read_text(encoding="utf-8"))
        remaining = []
        for item in inbox.get("items", []):
            r = resolve_inbox_item(item.get("value", ""))
            if r:
                r["tags"] = ["手動收錄"]
                if merge_paper(idx, papers, r):
                    n_new += 1
                print(f"[手動收錄] OK: {item.get('value','')[:60]}")
            else:
                print(f"[手動收錄] 查無資料: {item.get('value','')[:60]}")
                item["error"] = "查無此文獻，請確認 PMID/DOI"
                remaining.append(item)
        inbox_f.write_text(json.dumps({"items": remaining}, ensure_ascii=False, indent=1), encoding="utf-8")

    enrich_oa(papers, limit=1000 if backfill else 200)

    state["last_run"] = date.today().isoformat()
    DATA.mkdir(exist_ok=True)
    state_f.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    save_db(db)
    n_untrans = sum(1 for p in papers if not p.get("title_zh"))
    print(f"[完成] 本次新增 {n_new} 篇，情境過濾剔除 {n_filtered} 篇不相干，"
          f"資料庫共 {len(papers)} 篇，待翻譯 {n_untrans} 篇")


if __name__ == "__main__":
    main()
