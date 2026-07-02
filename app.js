/* EMS 文獻庫前端邏輯 */
const OWNER = 'sharky83920-png';
const REPO = 'ems-literature';
const BRANCH = 'main';
const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
const PAGE_SIZE = 50;

let papers = [];
let keywords = null;
let activeTag = '全部';
let page = 0;

/* ---------- 載入資料 ---------- */
async function loadPapers() {
  try {
    const r = await fetch(`data/papers.json?t=${Date.now()}`);
    if (!r.ok) throw new Error(r.status);
    const db = await r.json();
    papers = db.papers || [];
    document.getElementById('meta').textContent =
      `共 ${papers.length} 篇 · 最後更新 ${db.updated || '—'}`;
  } catch (e) {
    papers = [];
    document.getElementById('meta').textContent = '資料庫尚未建立';
    document.getElementById('list').innerHTML =
      '<div class="loading">還沒有文獻資料。第一次搜索完成後就會出現。</div>';
    return;
  }
  buildPills();
  render();
}

function buildPills() {
  const tags = new Set();
  papers.forEach(p => (p.tags || []).forEach(t => tags.add(t)));
  const special = ['全部', '本週新進', '待翻譯', '有中文全文'];
  const el = document.getElementById('pills');
  el.innerHTML = '';
  [...special, ...[...tags].sort((a, b) => a.localeCompare(b, 'zh-Hant'))].forEach(t => {
    const b = document.createElement('button');
    b.className = 'pill' + (t === activeTag ? ' on' : '');
    b.textContent = t;
    b.onclick = () => { activeTag = t; page = 0; render(); };
    el.appendChild(b);
  });
}

/* ---------- 篩選與渲染 ---------- */
function isNew(p) {
  if (!p.added) return false;
  return (Date.now() - new Date(p.added).getTime()) < 8 * 86400000;
}

function match(p, q) {
  if (!q) return true;
  const hay = [p.title, p.title_zh, p.abstract, p.abstract_zh,
    p.journal, p.authors, (p.tags || []).join(' ')].join(' ').toLowerCase();
  return q.toLowerCase().split(/\s+/).every(w => hay.includes(w));
}

function filtered() {
  const q = document.getElementById('q').value.trim();
  return papers.filter(p => {
    if (activeTag === '本週新進' && !isNew(p)) return false;
    if (activeTag === '待翻譯' && p.title_zh) return false;
    if (activeTag === '有中文全文' && !p.translation) return false;
    if (!['全部', '本週新進', '待翻譯', '有中文全文'].includes(activeTag)
      && !(p.tags || []).includes(activeTag)) return false;
    return match(p, q);
  });
}

function esc(s) {
  return (s || '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function card(p, i) {
  const badges = [];
  if (isNew(p)) badges.push('<span class="badge b-new">本週新進</span>');
  if (p.oa_pdf) badges.push('<span class="badge b-oa">開放取用</span>');
  if (!p.title_zh) badges.push('<span class="badge b-wait">待翻譯</span>');
  if (p.translation) badges.push('<span class="badge b-trans">有中文全文</span>');
  if ((p.tags || []).includes('手動收錄')) badges.push('<span class="badge b-manual">手動收錄</span>');
  const jd = [p.date ? p.date.slice(0, 7) : '', p.journal, p.authors]
    .filter(Boolean).join(' · ');
  const abst = p.abstract_zh || p.abstract || '';
  const btns = [];
  if (p.oa_pdf) btns.push(`<a class="btn" target="_blank" href="${esc(p.oa_pdf)}">看 PDF</a>`);
  if (p.url) btns.push(`<a class="btn" target="_blank" href="${esc(p.url)}">${p.pmid ? 'PubMed' : '原文連結'}</a>`);
  if (p.translation) btns.push(`<a class="btn primary" target="_blank" href="${esc(p.translation)}">看中文全文</a>`);
  else btns.push(`<button class="btn" onclick="askTranslate(${i})">申請全文翻譯</button>`);
  return `<div class="card">
    <div class="badges">${badges.join('')}<span class="jd">${esc(jd)}</span></div>
    ${p.title_zh ? `<p class="t-zh">${esc(p.title_zh)}</p><p class="t-en">${esc(p.title)}</p>`
      : `<p class="t-zh">${esc(p.title)}</p>`}
    ${abst ? `<p class="abst" onclick="this.classList.toggle('open')" title="點一下展開／收合">${esc(abst)}</p>` : ''}
    ${p.abstract_zh && p.abstract ? `<p class="abst-hint" onclick="const a=this.previousElementSibling;a.textContent=a.dataset.sw==='1'?this.dataset.zh:this.dataset.en;a.dataset.sw=a.dataset.sw==='1'?'0':'1';this.textContent=a.dataset.sw==='1'?'顯示中文摘要':'顯示英文原摘要'" data-zh="${esc(p.abstract_zh)}" data-en="${esc(p.abstract)}">顯示英文原摘要</p>` : ''}
    <div class="btns">${btns.join('')}</div>
  </div>`;
}

function render(resetPage = true) {
  if (resetPage) page = 0;
  buildPills();
  const list = filtered();
  const shown = list.slice(0, (page + 1) * PAGE_SIZE);
  document.getElementById('count').textContent =
    `符合 ${list.length} 篇，顯示 ${shown.length} 篇`;
  document.getElementById('list').innerHTML =
    shown.map(p => card(p, papers.indexOf(p))).join('') ||
    '<div class="loading">沒有符合的文獻</div>';
  document.getElementById('more').style.display =
    shown.length < list.length ? 'block' : 'none';
}

/* ---------- 全文翻譯懶人包 ---------- */
function askTranslate(i) {
  const p = papers[i];
  const id = p.pmid ? `PMID ${p.pmid}` : (p.doi ? `DOI ${p.doi}` : `標題「${p.title}」`);
  document.getElementById('cmdText').textContent =
    `幫我翻譯文獻庫 ${id} 的全文（repo: ${OWNER}/${REPO}），照維護手冊的全文翻譯流程做。`;
  document.getElementById('copyMsg').style.display = 'none';
  document.getElementById('modalBg').classList.add('show');
}
function copyCmd() {
  navigator.clipboard.writeText(document.getElementById('cmdText').textContent)
    .then(() => document.getElementById('copyMsg').style.display = 'block');
}
function closeModal() { document.getElementById('modalBg').classList.remove('show'); }

/* ---------- 分頁切換 ---------- */
function switchTab(t) {
  ['lib', 'manage', 'help'].forEach(x => {
    document.getElementById('tab-' + x).style.display = x === t ? '' : 'none';
    document.querySelector(`nav button[data-tab="${x}"]`).classList.toggle('on', x === t);
  });
  if (t === 'manage') initManage();
}

/* ---------- 金鑰 ---------- */
function token() { return localStorage.getItem('ems_lit_token') || ''; }
function saveToken() {
  const v = document.getElementById('tokenInput').value.trim();
  if (!v) return;
  localStorage.setItem('ems_lit_token', v);
  document.getElementById('tokenInput').value = '';
  showTokenStatus();
}
function showTokenStatus() {
  document.getElementById('tokenStatus').innerHTML = token()
    ? '<p class="ok">已設定金鑰，可以使用下方所有功能。想更換就再貼一組新的。</p>'
    : '<p class="err">尚未設定金鑰——下方功能需要金鑰才能使用。</p>';
}
async function gh(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      'Authorization': `Bearer ${token()}`,
      'Accept': 'application/vnd.github+json',
      ...(opts.headers || {})
    }
  });
  if (r.status === 401 || r.status === 403) throw new Error('金鑰無效或權限不足，請重新申請');
  return r;
}
function b64encode(str) {
  return btoa(String.fromCharCode(...new TextEncoder().encode(str)));
}
function b64decode(b64) {
  return new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\n/g, '')), c => c.charCodeAt(0)));
}
async function getFile(path) {
  const r = await gh(`/contents/${path}?ref=${BRANCH}&t=${Date.now()}`);
  if (r.status === 404) return { json: null, sha: null };
  const j = await r.json();
  return { json: JSON.parse(b64decode(j.content)), sha: j.sha };
}
async function putFile(path, obj, sha, msg) {
  const body = { message: msg, branch: BRANCH, content: b64encode(JSON.stringify(obj, null, 1)) };
  if (sha) body.sha = sha;
  const r = await gh(`/contents/${path}`, { method: 'PUT', body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`儲存失敗 (${r.status})`);
}

/* ---------- 立即搜索 ---------- */
async function runSearch() {
  const m = document.getElementById('runMsg');
  if (!token()) { m.innerHTML = '<span class="err">請先在上方設定金鑰</span>'; return; }
  m.textContent = '啟動中…';
  try {
    const r = await gh(`/actions/workflows/search.yml/dispatches`, {
      method: 'POST', body: JSON.stringify({ ref: BRANCH })
    });
    if (r.status === 204) m.innerHTML = '<span class="ok">已啟動！約 3-5 分鐘後重新整理本頁</span>';
    else throw new Error(r.status);
  } catch (e) { m.innerHTML = `<span class="err">${e.message}</span>`; }
}

/* ---------- 手動收錄 ---------- */
async function addInbox() {
  const m = document.getElementById('inboxMsg');
  const v = document.getElementById('inboxInput').value.trim();
  if (!v) return;
  if (!token()) { m.innerHTML = '<span class="err">請先在上方設定金鑰</span>'; return; }
  m.textContent = '儲存中…';
  try {
    const { json, sha } = await getFile('data/inbox.json');
    const inbox = json || { items: [] };
    inbox.items.push({ value: v, added: new Date().toISOString().slice(0, 10) });
    await putFile('data/inbox.json', inbox, sha, `手動收錄: ${v.slice(0, 60)}`);
    document.getElementById('inboxInput').value = '';
    m.innerHTML = '<span class="ok">已加入！按「立即搜索」馬上處理，或等每週一自動處理</span>';
  } catch (e) { m.innerHTML = `<span class="err">${e.message}</span>`; }
}

/* ---------- 關鍵字管理 ---------- */
let kwSha = null;
async function initManage() {
  showTokenStatus();
  try {
    const r = await fetch(`keywords.json?t=${Date.now()}`);
    keywords = await r.json();
    kwSha = null;
    renderKw();
  } catch (e) {
    document.getElementById('kwArea').innerHTML = '<p class="err">關鍵字檔載入失敗</p>';
  }
}
function renderKw() {
  const el = document.getElementById('kwArea');
  el.innerHTML = keywords.groups.map((g, gi) => `
    <div class="kwgroup">
      <div class="kwtag"><span>${esc(g.tag)}</span>
        <button class="del" onclick="delGroup(${gi})">刪除整組</button></div>
      <div class="kwlist">
        ${g.queries.map((q, qi) =>
          `<span class="kw">${esc(q)}<b onclick="delQuery(${gi},${qi})" title="刪除">✕</b></span>`).join('')}
        <span class="kw" style="cursor:pointer;color:var(--accent)" onclick="addQuery(${gi})">＋加詞</span>
      </div>
    </div>`).join('');
}
async function saveKw(msg) {
  const m = document.getElementById('kwMsg');
  if (!token()) { m.innerHTML = '<span class="err">請先在上方設定金鑰</span>'; initManage(); return; }
  m.textContent = '儲存中…';
  try {
    const { sha } = await getFile('keywords.json');
    await putFile('keywords.json', keywords, sha, msg);
    m.innerHTML = '<span class="ok">已儲存，下次搜索生效</span>';
    renderKw();
  } catch (e) { m.innerHTML = `<span class="err">${e.message}</span>`; }
}
function delQuery(gi, qi) {
  const q = keywords.groups[gi].queries[qi];
  if (!confirm(`刪除搜尋詞「${q}」？`)) return;
  keywords.groups[gi].queries.splice(qi, 1);
  saveKw(`刪除關鍵字: ${q}`);
}
function delGroup(gi) {
  const t = keywords.groups[gi].tag;
  if (!confirm(`刪除「${t}」整個主題群組？（已收錄的文獻不會被刪除）`)) return;
  keywords.groups.splice(gi, 1);
  saveKw(`刪除主題: ${t}`);
}
function addQuery(gi) {
  const q = prompt(`為「${keywords.groups[gi].tag}」新增英文搜尋詞：`);
  if (!q || !q.trim()) return;
  keywords.groups[gi].queries.push(q.trim());
  saveKw(`新增關鍵字: ${q.trim()}`);
}
function addGroup() {
  const tag = document.getElementById('newTag').value.trim();
  const qs = document.getElementById('newQueries').value.split(',').map(s => s.trim()).filter(Boolean);
  const m = document.getElementById('kwMsg');
  if (!tag || !qs.length) { m.innerHTML = '<span class="err">標籤和英文搜尋詞都要填</span>'; return; }
  keywords.groups.push({ tag, queries: qs });
  document.getElementById('newTag').value = '';
  document.getElementById('newQueries').value = '';
  saveKw(`新增主題: ${tag}`);
}

/* 瀏覽器有時會無視 autocomplete=off 硬塞 email 進搜尋框，載入後強制清空 */
function clearAutofill() {
  const q = document.getElementById('q');
  if (q.value && !q.dataset.userTyped) { q.value = ''; render(); }
}
document.getElementById('q').addEventListener('input', e => {
  if (document.activeElement === e.target) e.target.dataset.userTyped = '1';
});
window.addEventListener('load', () => { setTimeout(clearAutofill, 300); setTimeout(clearAutofill, 1500); });

loadPapers();
