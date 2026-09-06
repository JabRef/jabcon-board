'use strict';
const VIDEO = 'https://files.jabref.org/gource/jabcon-2026.mp4';
const COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f778ba', '#a371f7', '#ff7b72', '#79c0ff', '#56d364', '#e3b341', '#ffa657'];
let previous = null;
let data = null;
let color = {};

const $ = (s) => document.querySelector(s);
const avatar = (login, cls = 'avatar') => `<img class="${cls}" src="https://github.com/${login}.png?size=64" alt="" title="${login}" style="--c:${color[login] || 'var(--border)'}">`;
const link = (url, inner, cls = '') => `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener">${inner}</a>`;
const repoLink = (repo, text) => link(`https://github.com/${repo}`, esc(text), 'repo');
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function ago(iso) {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// [impl->req~column-order~1]
// [impl->req~github-colours~1]
function renderColumn(id, cards) {
  const org = data.config.org + '/';
  const last = (c) => c.merged_at || c.closed_at || c.updated_at;
  const sorted = [...cards].sort((a, b) => (b.focus - a.focus) || last(b).localeCompare(last(a)));
  const nFocus = sorted.filter((c) => c.focus).length;
  const box = $(`#${id} .cards`);
  const scrollTop = box.scrollTop;
  $(`#${id} .count`).textContent = cards.length;
  box.innerHTML = sorted.map((c, i) => (i === nFocus && nFocus && i < sorted.length ? '<div class="divider">other</div>' : '') + (() => {
    const other = !c.repo.startsWith(org);
    const tags = [];
    if (c.draft) tags.push('<span class="tag draft">draft</span>');
    // GitHub's colours: merged / completed purple, closed PR red, not planned or duplicate gray
    if (c.merged_at) tags.push('<span class="tag merged">merged</span>');
    else if (c.closed_at && c.type === 'pr') tags.push('<span class="tag closed">closed</span>');
    else if (c.closed_at && ['not_planned', 'duplicate'].includes(c.state_reason)) tags.push(`<span class="tag notplanned">${c.state_reason.replace('_', ' ')}</span>`);
    else if (c.closed_at) tags.push('<span class="tag merged">done</span>');
    if (c.labels.includes('ready-for-review')) tags.push('<span class="tag rfr">ready for review</span>');
    return `<div class="card ${other ? 'other' : ''} ${c.draft ? 'draft' : ''} ${c.focus ? 'focus' : ''}" style="border-left-color:${color[c.author] || 'var(--border)'}">
      ${avatar(c.author)}${link(c.url, `<span class="num">${c.type === 'pr' ? '⇄' : '◉'} #${c.number}</span>
      <span class="title">${esc(c.title)}</span>`, 'main')}${tags.join('')}${repoLink(c.repo, other ? c.repo : c.repo.slice(org.length))}</div>`;
  })()).join('');
  box.scrollTop = scrollTop;
  updateMore(box);
}

// [impl->req~column-overflow~1]
function updateMore(box) {
  const cards = [...box.children];
  const above = cards.filter((c) => c.offsetTop + c.offsetHeight <= box.scrollTop + 1).length;
  const below = cards.filter((c) => c.offsetTop >= box.scrollTop + box.clientHeight - 1).length;
  const section = box.parentElement;
  section.querySelector('.more.above').textContent = above ? `▲ ${above} more` : '';
  section.querySelector('.more.below').textContent = below ? `▼ ${below} more` : '';
}

// [impl->req~milestones~1]
// [impl->req~nerd-corner~1]
// [impl->req~leaderboard-breakdown~1]
function renderStats() {
  const s = data.stats;
  $('#totals').innerHTML = `<span>${s.changed_files} files</span><span class="add">+${s.additions}</span><span class="del">−${s.deletions}</span>`;
  const comps = Object.entries(s.components).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const max = comps[0]?.[1] || 1;
  $('#components').innerHTML = comps.map(([name, n]) =>
    `<span>${esc(name)}</span><div class="bar" style="width:${(100 * n / max).toFixed(1)}%"></div><span>${n}</span>`).join('');
  const f = data.focus;
  $('#milestones').innerHTML = (f ? `<div class="milestone focus"><div class="label">${link(f.url, `${esc(f.label)}`)}
      <span>${f.closed}/${f.closed + f.open} <span class="muted">${f.open} to go</span></span></div>
      <div class="bar"><div class="during" style="width:${(100 * f.closed / (f.closed + f.open || 1)).toFixed(1)}%"></div></div></div>` : '') +
    (data.milestones || []).map((m) => {
    const total = m.open + m.closed || 1, during = m.closed - m.baseline;
    return `<div class="milestone"><div class="label">${link(m.url, `${esc(m.title)} <span class="muted">${esc(m.repo.split('/')[1])}</span>`)}
      <span>${m.closed}/${total}${during ? ` <span class="muted">+${during}</span>` : ''} <span class="muted">${m.open} to go</span></span></div>
      <div class="bar"><div class="during" style="width:${(100 * m.closed / total).toFixed(1)}%"></div><div class="before" style="width:${(100 * m.baseline / total).toFixed(1)}%"></div></div></div>`;
  }).join('') + Object.entries(data.private_activity || {}).map(([repo, c]) =>
    `<div class="private">${esc(repo.split('/')[1])}: ${c.closed} closed · ${c.opened} opened · ${c.comments} comments</div>`).join('');
  $('#refactorings').innerHTML = data.refactorings.map((r) =>
    `<li>${avatar(r.author)}<span class="what">${esc(r.text)}</span>${link(r.url, `${esc(r.repo)}#${r.number}`, 'repo')}</li>`).join('');
  $('#leaderboard').innerHTML = data.leaderboard.map((l) => {
    const why = `${l.merged} merged PRs × 3 = ${l.merged * 3}\n${l.reviews} reviews × 2 = ${l.reviews * 2}\n${l.other} comments / issues / pushes × 1 = ${l.other}`;
    // the title must sit on the img itself: the avatar helper's own title would otherwise win over a wrapper's
    return `<div class="leader" data-login="${esc(l.login)}" style="--c:${color[l.login]}" title="${why}">${avatar(l.login, '').replace(`title="${l.login}"`, `title="${why}"`)}<div class="pts">${l.points}</div><div>${esc(l.login)}</div></div>`;
  }).join('');
}

// Mirrors the scoring in collect.py: merged PR (author) 3, review 2, comment / issue / push 1.
// [impl->req~scoring~1]
// [impl->req~no-self-review-points~1]
function eventPoints(e) {
  if (e.self) return 0; // own PR
  if (e.type === 'PullRequestReviewEvent') return 2;
  if (['IssueCommentEvent', 'IssuesEvent', 'PushEvent'].includes(e.type)) return 1;
  if (e.type === 'PullRequestEvent' && e.merged) {
    const pr = data.cards.find((c) => c.column === 'done' && c.repo === e.repo && c.number === e.number);
    if (pr && pr.author === e.actor) return 3;
  }
  return 0;
}

// [impl->req~ticker-deep-links~1]
function eventRow(e) {
  const org = data.config.org + '/', pts = eventPoints(e);
  return `<li class="${e.repo.startsWith(org) ? '' : 'other'}">${avatar(e.actor)}<span class="when">${ago(e.created_at)}</span>${link(e.number ? `https://github.com/${e.repo}/issues/${e.number}` : e.url, `<span class="what"><span class="line"><b>${esc(e.actor)}</b> ${esc(e.summary.replace(' (commented)', ''))}</span>${e.excerpt ? `<span class="excerpt">“${esc(e.excerpt)}”</span>` : ''}</span>`, 'main')}${pts ? `<span class="pts">+${pts}</span>` : ''}${repoLink(e.repo, e.repo.startsWith(org) ? e.repo.slice(org.length) : e.repo)}</li>`;
}

function renderTicker() {
  $('#ticker').innerHTML = data.events.filter((e) => e.type !== 'PullRequestReviewCommentEvent').slice(0, 40).map(eventRow).join('');
}

// Click on a leaderboard avatar: full-screen list of everything that contributor scored (or did not) during JabCon.
// [impl->req~contributor-detail~1]
function showDetail(login) {
  const l = data.leaderboard.find((x) => x.login === login) || { points: 0, merged: 0, reviews: 0, other: 0 };
  const events = (data.all_events || []).filter((e) => e.actor === login && e.type !== 'PullRequestReviewCommentEvent')
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  $('#detail h2').innerHTML = `${avatar(login)} ${esc(login)} <span class="muted">${l.points} points · ${l.merged} merged × 3 · ${l.reviews} reviews × 2 · ${l.other} other × 1</span>`;
  $('#detail ul').innerHTML = events.map(eventRow).join('') || '<li class="muted">no public activity yet</li>';
  $('#detail').hidden = false;
}
$('#detail .back').addEventListener('click', () => { $('#detail').hidden = true; });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') $('#detail').hidden = true; });
$('#leaderboard').addEventListener('click', (e) => { const who = e.target.closest('.leader')?.dataset.login; if (who) showDetail(who); });

// [impl->req~leader-change-bell~1]
// [impl->req~done-confetti~1]
function celebrate(prev) {
  if (!prev) return;
  const leader = data.leaderboard[0]?.login, wasLeader = prev.leaderboard[0]?.login;
  if (leader && wasLeader && leader !== wasLeader) {
    bell();
    toast(`🔔 ${leader} takes the lead!`);
  }
  const before = new Set(prev.cards.filter((c) => c.column === 'done').map((c) => c.id));
  for (const c of data.cards.filter((c) => c.column === 'done' && !before.has(c.id))) {
    const who = c.type === 'pr' ? c.author : c.assignees[0] || c.author;
    toast(`🎉 ${who} ${c.type === 'pr' ? 'merged' : 'closed'} #${c.number}`);
    if (window.confetti) confetti({ particleCount: 200, spread: 90, origin: { y: 0.7 } });
  }
}

// Fairground bell: a few bright partials with a fast decay, struck three times. Browsers may block audio until
// the page got one click after load; the click handler below unlocks it.
let audio;
function bell() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === 'suspended') audio.resume();
    const t0 = audio.currentTime;
    [0, 0.35, 0.7].forEach((offset) => {
      [1, 2.4, 3.9, 5.2].forEach((ratio, i) => {
        const osc = audio.createOscillator(), gain = audio.createGain();
        osc.frequency.value = 880 * ratio;
        gain.gain.setValueAtTime(0.25 / (i + 1), t0 + offset);
        gain.gain.exponentialRampToValueAtTime(0.001, t0 + offset + 1.2);
        osc.connect(gain).connect(audio.destination);
        osc.start(t0 + offset);
        osc.stop(t0 + offset + 1.3);
      });
    });
  } catch (e) { /* no audio */ }
}
document.addEventListener('click', () => { if (audio?.state === 'suspended') audio.resume(); }, { once: false });

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

// GitHub runs a */5 schedule only best-effort (observed 7-20 min between runs), so the ring is sized for a typical gap
const REFRESH_MS = 10 * 60000;

// [impl->req~timeline~1]
function renderProgress() {
  const start = Date.parse(data.config.jabcon_start), end = Date.parse(data.config.jabcon_end);
  const pct = (iso) => `${(100 * (Date.parse(iso) - start) / (end - start)).toFixed(2)}%`;
  const fmt = (iso) => new Date(iso).toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: data.config.timezone });
  const phases = data.config.phases || [];
  let from = data.config.jabcon_start;
  $('#phases').innerHTML = phases.map((p, i) => {
    const mid = new Date((Date.parse(from) + Date.parse(p.end)) / 2).toISOString();
    from = p.end;
    return `<span style="left:${pct(mid)}">${esc(p.label)} <b class="phase-left" data-end="${esc(p.end)}"></b></span>`;
  }).join('');
  $('#ticks').innerHTML = phases.slice(0, -1).map((p) => `<span style="left:${pct(p.end)}"></span>`).join('');
  $('#from').textContent = fmt(data.config.jabcon_start);
  $('#to').textContent = fmt(data.config.jabcon_end);
}

// [impl->req~refresh-ring~1]
// [impl->req~clock-timezone~1]
function tick() {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data?.config.timezone });
  if (!data) return;
  const age = now - Date.parse(data.generated_at);
  $('#updated').style.setProperty('--p', Math.min(1, age / REFRESH_MS));
  $('#updated').classList.toggle('overdue', age > REFRESH_MS);
  $('#updated').title = `last update ${ago(data.generated_at)}`;
  $('#data-time').textContent = `data ${new Date(data.generated_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data.config.timezone })}`;
  $('#header').classList.toggle('stale', age > 30 * 60000);
  const start = Date.parse(data.config.jabcon_start), end = Date.parse(data.config.jabcon_end);
  $('#elapsed').style.width = `${Math.max(0, Math.min(100, 100 * (now - start) / (end - start)))}%`;
  const left = end - now;
  const dh = (ms) => `${Math.floor(ms / 86400000)} d ${Math.floor(ms / 3600000) % 24} h`;
  document.querySelectorAll('.phase-left').forEach((el) => {
    const remaining = Date.parse(el.dataset.end) - now;
    el.textContent = remaining > 0 ? `· ${dh(remaining)} left` : '· done';
  });
  $('#countdown').textContent = now < start ? `starts in ${Math.floor((start - now) / 3600000)} h`
    : left > 0 ? `${Math.floor((now - start) / 3600000)} h in · ${Math.floor(left / 86400000)} d ${Math.floor(left / 3600000) % 24} h left`
    : 'JabCon is over – thank you!';
}

// [impl->req~auto-reload~1]
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
video.addEventListener('loadedmetadata', () => { video.playbackRate = 3; }); // [impl->req~gource-speed~1] re-applied per source: a src swap resets the rate
// [impl->req~gource-refresh~1]
function loadVideo() {
  if (video.getAttribute('src')) { video.loop = false; return; } // finish the current loop, then swap
  video.loop = true;
  video.src = `${VIDEO}?ts=${Date.now()}`;
}

document.querySelectorAll('.cards').forEach((b) => b.addEventListener('scroll', () => updateMore(b)));
// clicking "n more" pages the column in that direction (for desktop use; the wall never scrolls)
document.querySelectorAll('.more').forEach((m) => m.addEventListener('click', () => {
  const box = m.parentElement.querySelector('.cards');
  box.scrollBy({ top: (m.classList.contains('above') ? -1 : 1) * box.clientHeight * 0.9, behavior: 'smooth' });
}));
const params = new URLSearchParams(location.search);
if (params.get('still')) document.documentElement.classList.add('still');
// Browser zoom is a no-op here: the layout is in vw/vh, so a zoomed viewport shrinks the text right back.
// Ctrl+wheel therefore scales the page itself; the factor survives the self-reloads via localStorage. Ctrl+0 resets.
let scale = parseFloat(params.get('scale')) || parseFloat(localStorage.getItem('scale')) || 1;
// [impl->req~scaling~1]
function applyScale() {
  document.documentElement.style.fontSize = `min(${1.146 * scale}vw, ${2.037 * scale}vh)`;
  try { localStorage.setItem('scale', scale); } catch (e) { /* private mode */ }
}
if (scale !== 1) applyScale();
document.addEventListener('wheel', (e) => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  scale = Math.min(3, Math.max(0.3, scale * (e.deltaY < 0 ? 1.1 : 1 / 1.1)));
  applyScale();
}, { passive: false });
document.addEventListener('keydown', (e) => { if (e.ctrlKey && e.key === '0') { scale = 1; applyScale(); } });
load();
loadVideo();
setInterval(load, 60000);
setInterval(tick, 1000);
setInterval(loadVideo, 15 * 60000);
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
