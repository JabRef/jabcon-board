'use strict';
const VIDEO = 'https://files.jabref.org/gource/jabcon-2026.mp4';
const COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f778ba', '#a371f7', '#ff7b72', '#79c0ff', '#56d364', '#e3b341', '#ffa657'];
let previous = null;
let data = null;
let color = {};

const $ = (s) => document.querySelector(s);
const avatar = (login, cls = 'avatar') => `<img class="${cls}" src="https://github.com/${login}.png?size=64" alt="" title="${login}" style="--c:${color[login] || 'var(--border)'}">`;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function ago(iso) {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

function renderColumn(id, cards) {
  const org = data.config.org + '/';
  const last = (c) => c.merged_at || c.closed_at || c.updated_at;
  const sorted = [...cards].sort((a, b) => last(b).localeCompare(last(a)));
  const box = $(`#${id} .cards`);
  const scrollTop = box.scrollTop;
  $(`#${id} .count`).textContent = cards.length;
  box.innerHTML = sorted.map((c) => {
    const other = !c.repo.startsWith(org);
    const tags = [];
    if (c.draft) tags.push('<span class="tag draft">draft</span>');
    if (c.merged_at) tags.push('<span class="tag merged">merged</span>');
    else if (c.closed_at) tags.push('<span class="tag closed">closed</span>');
    if (c.labels.includes('ready-for-review')) tags.push('<span class="tag rfr">ready for review</span>');
    return `<div class="card ${other ? 'other' : ''} ${c.draft ? 'draft' : ''}" style="border-left-color:${color[c.author] || 'var(--border)'}">
      ${avatar(c.author)}<span class="num">${c.type === 'pr' ? '⇄' : '◉'} #${c.number}</span>
      <span class="title">${esc(c.title)}</span>${tags.join('')}<span class="repo">${esc(other ? c.repo : c.repo.slice(org.length))}</span></div>`;
  }).join('');
  box.scrollTop = scrollTop;
  updateMore(box);
}

function updateMore(box) {
  const cards = [...box.children];
  const above = cards.filter((c) => c.offsetTop + c.offsetHeight <= box.scrollTop + 1).length;
  const below = cards.filter((c) => c.offsetTop >= box.scrollTop + box.clientHeight - 1).length;
  const section = box.parentElement;
  section.querySelector('.more.above').textContent = above ? `▲ ${above} more` : '';
  section.querySelector('.more.below').textContent = below ? `▼ ${below} more` : '';
}

function renderStats() {
  const s = data.stats;
  $('#totals').innerHTML = `<span>${s.changed_files} files</span><span class="add">+${s.additions}</span><span class="del">−${s.deletions}</span>`;
  const comps = Object.entries(s.components).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const max = comps[0]?.[1] || 1;
  $('#components').innerHTML = comps.map(([name, n]) =>
    `<span>${esc(name)}</span><div class="bar" style="width:${(100 * n / max).toFixed(1)}%"></div><span>${n}</span>`).join('');
  $('#milestones').innerHTML = (data.milestones || []).map((m) => {
    const total = m.open + m.closed || 1, during = m.closed - m.baseline;
    return `<div class="milestone"><div class="label"><span>${esc(m.title)} <span class="muted">${esc(m.repo.split('/')[1])}</span></span>
      <span>${m.closed}/${total}${during ? ` <span class="muted">+${during}</span>` : ''}</span></div>
      <div class="bar"><div class="during" style="width:${(100 * m.closed / total).toFixed(1)}%"></div><div class="before" style="width:${(100 * m.baseline / total).toFixed(1)}%"></div></div></div>`;
  }).join('') + Object.entries(data.private_activity || {}).map(([repo, c]) =>
    `<div class="private">${esc(repo.split('/')[1])}: ${c.closed} closed · ${c.opened} opened · ${c.comments} comments</div>`).join('');
  $('#refactorings').innerHTML = data.refactorings.map((r) =>
    `<li>${avatar(r.author)}<span class="what">${esc(r.text)}</span><span class="repo">${esc(r.repo)}#${r.number}</span></li>`).join('');
  $('#leaderboard').innerHTML = data.leaderboard.map((l) =>
    `<div class="leader" style="--c:${color[l.login]}">${avatar(l.login, '')}<div class="pts">${l.points}</div><div>${esc(l.login)}</div></div>`).join('');
}

function renderTicker() {
  const org = data.config.org + '/';
  $('#ticker').innerHTML = data.events.filter((e) => e.type !== 'PullRequestReviewCommentEvent').slice(0, 40).map((e) =>
    `<li class="${e.repo.startsWith(org) ? '' : 'other'}">${avatar(e.actor)}<span class="when">${ago(e.created_at)}</span><span class="what"><b>${esc(e.actor)}</b> ${esc(e.summary)}</span><span class="repo">${esc(e.repo.startsWith(org) ? e.repo.slice(org.length) : e.repo)}</span></li>`).join('');
}

function celebrate(prev) {
  if (!prev) return;
  const before = new Set(prev.cards.filter((c) => c.column === 'done').map((c) => c.id));
  for (const c of data.cards.filter((c) => c.column === 'done' && !before.has(c.id))) {
    const who = c.type === 'pr' ? c.author : c.assignees[0] || c.author;
    toast(`🎉 ${who} ${c.type === 'pr' ? 'merged' : 'closed'} #${c.number}`);
    if (window.confetti) confetti({ particleCount: 200, spread: 90, origin: { y: 0.7 } });
  }
}

let toastTimer;
function toast(text) {
  $('#toast').textContent = text;
  $('#toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 8000);
}

function render() {
  data.config.participants.forEach((p, i) => { color[p] = COLORS[i % COLORS.length]; });
  $('#title').textContent = `JabCon ${new Date(data.config.jabcon_start).getFullYear()}`;
  for (const col of ['backlog', 'progress', 'done']) renderColumn(col, data.cards.filter((c) => c.column === col));
  renderStats();
  renderTicker();
  renderProgress();
  tick();
}

const REFRESH_MS = 15 * 60000; // cron interval of the board workflow

function renderProgress() {
  const start = Date.parse(data.config.jabcon_start), end = Date.parse(data.config.jabcon_end);
  const pct = (iso) => `${(100 * (Date.parse(iso) - start) / (end - start)).toFixed(2)}%`;
  const fmt = (iso) => new Date(iso).toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: data.config.timezone });
  const phases = data.config.phases || [];
  let from = data.config.jabcon_start;
  $('#phases').innerHTML = phases.map((p) => {
    const mid = new Date((Date.parse(from) + Date.parse(p.end)) / 2).toISOString();
    from = p.end;
    return `<span style="left:${pct(mid)}">${esc(p.label)}</span>`;
  }).join('');
  $('#ticks').innerHTML = phases.slice(0, -1).map((p) => `<span style="left:${pct(p.end)}"></span>`).join('');
  $('#from').textContent = fmt(data.config.jabcon_start);
  $('#to').textContent = fmt(data.config.jabcon_end);
}

function tick() {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data?.config.timezone });
  if (!data) return;
  const age = now - Date.parse(data.generated_at);
  $('#updated').style.setProperty('--p', Math.min(1, age / REFRESH_MS));
  $('#updated').title = `last update ${ago(data.generated_at)}`;
  $('#data-time').textContent = `data ${new Date(data.generated_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data.config.timezone })}`;
  $('#header').classList.toggle('stale', age > 30 * 60000);
  const start = Date.parse(data.config.jabcon_start), end = Date.parse(data.config.jabcon_end);
  $('#elapsed').style.width = `${Math.max(0, Math.min(100, 100 * (now - start) / (end - start)))}%`;
  const left = end - now;
  $('#countdown').textContent = now < start ? `starts in ${Math.floor((start - now) / 3600000)} h`
    : left > 0 ? `${Math.floor((now - start) / 3600000)} h in · ${Math.floor(left / 86400000)} d ${Math.floor(left / 3600000) % 24} h left`
    : 'JabCon is over – thank you!';
}

async function load() {
  try {
    const r = await fetch('data.json?ts=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.statusText);
    previous = data;
    data = await r.json();
    render();
    celebrate(previous);
  } catch (e) {
    console.error('load failed', e);
    $('#header').classList.add('stale');
  }
}

const video = $('#gource');
video.addEventListener('ended', () => { video.loop = true; video.src = `${VIDEO}?ts=${Date.now()}`; video.play().catch(() => {}); });
video.addEventListener('error', () => video.removeAttribute('src')); // no rendering yet: hide, retry next hour
function loadVideo() {
  if (video.getAttribute('src')) { video.loop = false; return; } // finish the current loop, then swap
  video.loop = true;
  video.src = `${VIDEO}?ts=${Date.now()}`;
}

document.querySelectorAll('.cards').forEach((b) => b.addEventListener('scroll', () => updateMore(b)));
const scale = parseFloat(new URLSearchParams(location.search).get('scale'));
if (scale > 0) document.documentElement.style.fontSize = `min(${1.146 * scale}vw, ${2.037 * scale}vh)`;
load();
loadVideo();
setInterval(load, 60000);
setInterval(tick, 1000);
setInterval(loadVideo, 3600000);
setInterval(renderTicker, 30000);

// version.txt holds the deployed commit; shown in the corner and used to reload the page after a new deployment.
let version;
async function checkVersion() {
  try {
    const r = await fetch('version.txt?ts=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) return;
    const v = (await r.text()).trim();
    if (version && v !== version) location.reload();
    version = v;
    $('#version').textContent = `site ${v}`;
  } catch (e) { /* offline: try again later */ }
}
checkVersion();
setInterval(checkVersion, 5 * 60000);
