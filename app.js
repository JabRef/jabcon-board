'use strict';
const VIDEO = 'https://files.jabref.org/gource/jabcon-2026.mp4';
const COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f778ba', '#a371f7', '#ff7b72', '#79c0ff', '#56d364', '#e3b341', '#ffa657'];
const MAX_CARDS = { backlog: 14, progress: 14, done: 14 };
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
  const sorted = [...cards].sort((a, b) => (b.merged_at || b.closed_at || b.updated_at).localeCompare(a.merged_at || a.closed_at || a.updated_at));
  const shown = sorted.slice(0, MAX_CARDS[id]);
  $(`#${id} .count`).textContent = cards.length;
  $(`#${id} .cards`).innerHTML = shown.map((c) => {
    const other = !c.repo.startsWith(org);
    const tags = [];
    if (c.draft) tags.push('<span class="tag draft">draft</span>');
    if (c.merged_at) tags.push('<span class="tag merged">merged</span>');
    if (c.labels.includes('ready-for-review')) tags.push('<span class="tag rfr">ready for review</span>');
    return `<div class="card ${other ? 'other' : ''} ${c.draft ? 'draft' : ''}" style="border-left-color:${color[c.author] || 'var(--border)'}">
      ${avatar(c.author)}<span class="num">${c.type === 'pr' ? '⇄' : '◉'} #${c.number}</span>
      <span class="title">${esc(c.title)}</span>${tags.join('')}<span class="repo">${esc(c.repo)}</span></div>`;
  }).join('') + (cards.length > shown.length ? `<div class="more">+ ${cards.length - shown.length} more</div>` : '');
}

function renderStats() {
  const s = data.stats;
  $('#totals').innerHTML = `<span>${s.changed_files} files</span><span class="add">+${s.additions}</span><span class="del">−${s.deletions}</span>`;
  const comps = Object.entries(s.components).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const max = comps[0]?.[1] || 1;
  $('#components').innerHTML = comps.map(([name, n]) =>
    `<span>${esc(name)}</span><div class="bar" style="width:${(100 * n / max).toFixed(1)}%"></div><span>${n}</span>`).join('');
  $('#leaderboard').innerHTML = data.leaderboard.map((l) =>
    `<div class="leader" style="--c:${color[l.login]}">${avatar(l.login, '')}<div class="pts">${l.points}</div><div>${esc(l.login)}</div></div>`).join('');
}

function renderTicker() {
  $('#ticker').innerHTML = data.events.slice(0, 40).map((e) =>
    `<li>${avatar(e.actor)}<span class="when">${ago(e.created_at)}</span><span class="what"><b>${esc(e.actor)}</b> ${esc(e.summary)} <span class="repo">${esc(e.repo)}</span></span></li>`).join('');
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
  tick();
}

function tick() {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data?.config.timezone });
  if (!data) return;
  const age = (now - Date.parse(data.generated_at)) / 60000;
  $('#updated').textContent = `last update ${ago(data.generated_at)}`;
  $('#header').classList.toggle('stale', age > 30);
  const left = Date.parse(data.config.jabcon_end) - now;
  $('#countdown').textContent = left > 0 ? `ends in ${Math.floor(left / 86400000)} d ${Math.floor(left / 3600000) % 24} h` : 'JabCon is over – thank you!';
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

load();
loadVideo();
setInterval(load, 60000);
setInterval(tick, 1000);
setInterval(loadVideo, 3600000);
setInterval(renderTicker, 30000);
