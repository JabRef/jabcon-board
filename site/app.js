'use strict';
const VIDEO = 'https://files.jabref.org/gource/jabcon-2026.mp4';
const HIGHLIGHTS = 'highlights.mp4'; // rendered hourly by .github/workflows/highlights.yml next to this file
const COMMENTARY = 'commentary.mp4'; // same, the full run with a commentator's subtitles
const PLAYLIST = [VIDEO, HIGHLIGHTS, COMMENTARY];
const NAMES = { [VIDEO]: 'full', [HIGHLIGHTS]: 'highlights', [COMMENTARY]: 'commentary' };
const COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f778ba', '#a371f7', '#ff7b72', '#79c0ff', '#56d364', '#e3b341', '#ffa657'];
let previous = null;
let raw = null;
let data = null;
let color = {};

const $ = (s) => document.querySelector(s);
const avatar = (login, cls = 'avatar') => `<img class="${cls}" src="https://github.com/${login}.png?size=64" alt="" title="${login}" style="--c:${color[login] || 'var(--border)'}">`;
const link = (url, inner, cls = '') => `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener">${inner}</a>`;
const repoLink = (repo, text) => link(`https://github.com/${repo}`, esc(text), 'repo');
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (n) => Number(n).toLocaleString('en-US');
// Net size change of a component: added minus removed, signed. [impl->req~component-net~1]
const net = (n) => (n == null ? '' : `<span class="net ${n < 0 ? 'del' : 'add'}">${n < 0 ? '\u2212' : '+'}${fmt(Math.abs(n))}</span>`);
const group = (s) => s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');

function ago(iso) {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// Tendency of a counted number: a triangle for the way it moved over the last hour (or over as much history as the
// collector has kept so far), green when that is the good direction. Nothing is drawn without a second sample.
// [impl->req~trend-arrows~7]
const TREND_H = 1;
// The pair of samples every tendency compares: the newest, and the oldest one still inside the trend window.
function trendSamples(at) {
  // only samples that carry the number in question: a run that could not collect it must not read as a change
  const h = (data.history || []).filter((s) => at(s) != null);
  return [h.filter((s) => Date.parse(s.t) <= Date.now() - TREND_H * 3600e3).pop() || h[0], h.at(-1)];
}
// [impl->req~delta-detail~2] what moved a contributor's total in that window: the counts that changed, and the
// stickers gained or lost, which are worth exactly 100 each. The other lines are counts, not points, since a single
// review is worth between 1 and 30 depending on the diff and the repo.
function deltaWhy(login) {
  const [then, last] = trendSamples((s) => s.parts?.[login]);
  const a = then?.parts?.[login], b = last?.parts?.[login];
  if (!a || !b) return [];
  const lines = [['m', 'merged PRs'], ['r', 'reviews'], ['o', 'comments, issues and pushes'],
    ['a', 'of them AI-assisted'], ['k', 'on JabCon items'], ['x', 'in boosted repos']]
    .filter(([k]) => a[k] !== b[k]).map(([k, what]) => `${what} ${a[k]} → ${b[k]}`);
  // the other side of a hand-over sits in the same two samples: whoever holds the sticker there and did not before
  const held = (s, t) => Object.entries(s?.parts || {}).filter(([l, p]) => l !== login && (p.b || []).includes(t)).map(([l]) => l);
  const side = (t, has, had, word) => {
    const who = held(has, t).filter((l) => !held(had, t).includes(l));
    return who.length ? ` ${word} ${who.join(' and ')}` : '';
  };
  (a.b || []).filter((t) => !(b.b || []).includes(t)).forEach((t) => lines.push(`lost ${t} (−100)${side(t, last, then, 'to')}`));
  (b.b || []).filter((t) => !(a.b || []).includes(t)).forEach((t) => lines.push(`earned ${t} (+100)${side(t, then, last, 'from')}`));
  return lines;
}
function trend(key, goodDown, withValue, flat, extra) {
  const at = (s) => (typeof key === 'function' ? key(s) : s?.[key]);
  const [then, last] = trendSamples(at);
  if (!then || then === last || at(then) == null || at(last) == null) return '';
  const d = at(last) - at(then);
  if (!d && !flat) return '';
  const mins = Math.round((Date.parse(last.t) - Date.parse(then.t)) / 60000);
  const window = `the last ${mins < 90 ? `${mins} min` : `${Math.round(mins / 60)} h`}`;
  const why = [d ? `${d > 0 ? '+' : ''}${d} in ${window}` : `unchanged in ${window}`, ...(extra || [])].join('\n');
  // a flat number gets a gray dash rather than no mark at all, the way a ticker shows an unmoved price
  const cls = !d ? 'flat' : (d < 0) === !!goodDown ? 'good' : 'bad';
  return `<span class="trend ${cls}" title="${esc(why)}">${d ? (d > 0 ? '\u25b2' : '\u25bc') : '\u25ac'}${withValue && d ? fmt(Math.abs(d)) : ''}</span>`;
}

// [impl->req~column-order~2]
// [impl->req~github-colours~1]
function renderColumn(id, cards) {
  const org = data.config.org + '/';
  const last = (c) => c.merged_at || c.closed_at || c.updated_at;
  const sorted = [...cards].sort((a, b) => (b.focus - a.focus) || last(b).localeCompare(last(a)));
  const nFocus = sorted.filter((c) => c.focus).length;
  const queued = new Set(queuedCards().map((c) => c.id));
  const box = $(`#${id} .cards`);
  const scrollTop = box.scrollTop;
  // a shrinking column is good in both cases: the backlog was picked up, the work in progress landed - and a
  // growing "done" is good for the same reason
  $(`#${id} .count`).innerHTML = `${cards.length}${trend(id, id !== 'done', true, true)}`;
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
      <span class="title">${esc(c.title)}</span>`, 'main')}${tags.join('')}${queued.has(c.id) ? queueMark(18) : ''}${repoLink(c.repo, other ? c.repo : c.repo.slice(org.length))}</div>`;
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

// [impl->req~milestones~2]
// [impl->req~leaderboard-breakdown~1]
function renderStats() {
  const s = data.stats;
  const tot = (k) => trend((h) => h.stats?.[k], false, true, true);
  $('#totals').innerHTML = `<span>${fmt(s.changed_files)} files${tot('changed_files')}</span><span class="add">+${fmt(s.additions)}${tot('additions')}</span><span class="del">−${fmt(s.deletions)}${tot('deletions')}</span>`;
  renderPrGoal();
  const comps = Object.entries(s.components).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const max = comps[0]?.[1] || 1;
  const compWhy = 'How much this component grew or shrank: added \u2212 removed lines.\nThe bar is how much moved in it overall. Click for the PRs behind the number.';
  $('#components').innerHTML = comps.map(([name, n]) => {
    const a = `data-comp="${esc(name)}" title="${esc(compWhy)}"`;
    return `<span ${a}>${esc(name)}</span><div class="bar" ${a} style="width:${(100 * n / max).toFixed(1)}%"></div><span ${a}>${net(s.components_net?.[name])}${trend((h) => h.components_net?.[name], true, true, true)}</span>`;
  }).join('');
  const queued = queuedCards();
  const queueMarkIf = (pred) => (queued.some(pred) ? queueMark(16) : '');
  const f = data.focus;
  const focusWhy = f && `Issues labeled "${f.label}" across the org — the JabCon focus.\n${f.closed} of ${f.closed + f.open} closed, ${f.open} to go.\nThe green bar is the closed share.`;
  $('#milestones').innerHTML = (f ? `<div class="milestone focus" title="${esc(focusWhy)}"><div class="label">${link(f.url, `${esc(f.label)}`)}${queueMarkIf((c) => c.labels.includes(f.label))}
      <span>${f.closed}/${f.closed + f.open} <span class="muted">${f.open} to go</span></span></div>
      <div class="bar"><div class="during" style="width:${(100 * f.closed / (f.closed + f.open || 1)).toFixed(1)}%"></div></div></div>` : '') +
    (data.milestones || []).map((m) => {
    const total = m.open + m.closed || 1, during = m.closed - m.baseline;
    // the label is truncated on narrow screens, so the tooltip repeats the full milestone name
    const why = `Milestone "${m.title}" in ${m.repo}.\n${m.closed} of ${total} issues closed, ${m.open} to go.\n${during} of them were closed since JabCon started (${m.baseline} were already done then).\nBlue bar: closed before JabCon, green tail: closed during it.`;
    return `<div class="milestone" title="${esc(why)}"><div class="label">${link(m.url, `${esc(m.title)} <span class="muted">${esc(m.repo.split('/')[1])}</span>`)}${queueMarkIf((c) => c.milestone === m.ref)}
      <span>${during} closed <span class="muted">${m.open} to go</span></span></div>
      <div class="bar"><div class="during" style="width:${(100 * m.closed / total).toFixed(1)}%"></div><div class="before" style="width:${(100 * m.baseline / total).toFixed(1)}%"></div></div></div>`;
  }).join('') + Object.entries(data.private_activity || {}).map(([repo, c]) =>
    `<div class="private" title="${esc(`${repo} is private: only counts since JabCon started, never titles or numbers.`)}">${esc(repo.split('/')[1])}: ${c.closed} closed · ${c.opened} opened · ${c.comments} comments</div>`).join('');
  renderNerd();
  renderAiModels();
  $('#leaderboard').innerHTML = data.leaderboard.map((l) => {
    const why = `${l.merged} merged PRs × 3 (${l.ai || 0} of them AI-assisted × 0.25)\n${l.reviews} reviews × 1..3 (by complexity of the diff)\n${l.other} comments / issues / pushes / PRs opened / closed × 1\n${l.milestone || 0} of these on JabCon items (focus label / milestone) × 10\n${l.boosted || 0} in ${boostText()}`
      + (l.bonuses || []).map((b) => `\n+${b.points} ${b.title}: ${b.text}`).join('');
    // the title must sit on the img itself: the avatar helper's own title would otherwise win over a wrapper's
    return `<div class="leader" data-login="${esc(l.login)}" style="--c:${color[l.login]}" title="${why}">${avatar(l.login, '').replace(`title="${l.login}"`, `title="${why}"`)}<div class="pts">${fmt(l.points)}</div><div>${esc(l.login)}${trend((s) => s.points?.[l.login], false, true, false, deltaWhy(l.login))}</div>${bonusRow(l)}</div>`;
  }).join('');
  slotMachine();
}

// The open-PR meter next to the stats heading: how far the review backlog still is from the goal, with the stretch
// target ticked on the bar. The colour runs green (zero open) to red at the goal; past the goal it flashes.
// [impl->req~pr-goal-meter~2]
let prgoalHtml;
const OVER_PX = 10; // how far the meter grows for every PR over the goal
const ALARM_MS = 1100; // one beat, the same number as the CSS animation's duration
const QUEUE_MS = 1200; // one hammer swing, the same number as the CSS animation's duration

// [impl->req~merge-queue-dwarf~5] While PRs wait in the merge queue a pixel dwarf stands where the bar ends and
// hammers at its tip; that last block is what the count is about to lose, and it flashes yellow on every hit.
function dwarf(n, at) {
  const why = esc(`${n} PR${n === 1 ? '' : 's'} in the merge queue.\nThe dwarf is hammering their block off the end of the bar.`);
  return `<span class="dwarf" style="left:${at}" title="${why}">${dwarfSvg()}</span>`;
}
function dwarfSvg(px = 40) {
  return `<svg viewBox="0 0 16 16" width="${px}" height="${px}" shape-rendering="crispEdges">
    <rect x="4" y="0" width="6" height="2" fill="#c0392b"/><rect x="3" y="2" width="9" height="1" fill="#c0392b"/>
    <rect x="5" y="3" width="5" height="2" fill="#e8b18a"/><rect x="8" y="3" width="1" height="1" fill="#2b2118"/>
    <rect x="4" y="5" width="7" height="3" fill="#dfe6ee"/>
    <rect x="5" y="8" width="6" height="3" fill="#3b6ea5"/><rect x="5" y="11" width="6" height="1" fill="#4a3527"/>
    <rect x="5" y="12" width="2" height="3" fill="#4a3527"/><rect x="9" y="12" width="2" height="3" fill="#4a3527"/>
    <g class="arm"><rect x="10" y="8" width="4" height="1" fill="#8a5a2b"/><rect x="13" y="6" width="3" height="4" fill="#9aa5b1"/>
      <rect x="13" y="6" width="3" height="1" fill="#c9d1d9"/></g>
  </svg>`;
}

// [impl->req~merge-queue-dwarf~5] The same dwarf, pocket-sized, hammers wherever a queued PR shows up: on its card
// and on the milestone row it belongs to. One animation everywhere - a second kind would only need explaining.
function queuedCards() {
  const g = data.pr_goal, nums = new Set(g?.queue_prs || []);
  return nums.size ? data.cards.filter((c) => c.type === 'pr' && c.repo === g.repo && nums.has(c.number)) : [];
}
function queueMark(px) {
  return `<span class="dwarf mark" title="Waiting in the merge queue">${dwarfSvg(px)}</span>`;
}

// [impl->req~merge-queue-dwarf~5] GitHub's own estimate for the last entry of the queue, counted down beside the
// dwarf so the board says how long he still has to hammer. Filled by the second in `tick`, never in the meter's
// markup: a text that changes every second would rebuild the meter and restart the swing on every beat.
function etaText(iso) {
  const left = Math.round((Date.parse(iso) - Date.now()) / 1000);
  const s = Math.abs(left), h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, sec = s % 60;
  // spelled out, or a bare "19:27" beside a wall clock reads as half past seven
  const t = h ? `${h}:${String(m).padStart(2, '0')} h` : `${m}:${String(sec).padStart(2, '0')} min`;
  // past the estimate the clock keeps running, with a plus: the queue is late, and how late is the news
  return left > 0 ? t : `+${t}`;
}
function renderEta() {
  const el = $('#queue-eta'), eta = data?.pr_goal?.queue_eta;
  if (!el || !eta) return;
  el.textContent = etaText(eta);
  const late = Date.parse(eta) < Date.now();
  el.classList.toggle('late', late);
  el.title = `GitHub expect${late ? 'ed' : 's'} the queue to be empty at `
    + new Date(eta).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data.config.timezone })
    + ` - the longest estimate of everything queued.${late ? ' It is running over; the plus counts how far.' : ''}`;
}

// [impl->req~merge-queue-dwarf~5] An empty queue leaves him nothing to hammer, so he strolls across the board:
// a walk to a random spot at a dwarf's pace, a breather, and off again. Not while the board is held still.
const WANDER_PX_S = 60, WANDER_REST_MS = 2500;
let wanderAt = null, wanderTimer = 0;
function wander(on) {
  const el = $('#wanderer');
  const still = document.documentElement.classList.contains('still')
    || matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!on || still) {
    clearTimeout(wanderTimer);
    if (el) el.remove();
    wanderAt = null;
    return;
  }
  if (el) return; // already out for his walk, and it must not restart on every render
  document.body.insertAdjacentHTML('beforeend',
    `<div id="wanderer" title="Nothing in the merge queue - the dwarf is taking a walk.">${dwarfSvg()}</div>`);
  wanderAt = wanderAt || { x: innerWidth / 2, y: innerHeight - 80 };
  wanderStep();
}
function wanderStep() {
  const dwarfEl = $('#wanderer');
  if (!dwarfEl) return;
  const to = { x: Math.random() * (innerWidth - 40), y: Math.random() * (innerHeight - 40) };
  const secs = Math.hypot(to.x - wanderAt.x, to.y - wanderAt.y) / WANDER_PX_S;
  dwarfEl.style.transition = `transform ${secs.toFixed(1)}s linear`;
  // he faces the way he is going, and the flip rides along in the same transform, so it turns as he sets off
  dwarfEl.style.transform = `translate(${to.x}px, ${to.y}px) scaleX(${to.x < wanderAt.x ? -1 : 1})`;
  wanderAt = to;
  wanderTimer = setTimeout(wanderStep, secs * 1000 + WANDER_REST_MS);
}
function renderPrGoal() {
  const g = data.pr_goal;
  $('#prgoal').hidden = !g;
  if (!g) return;
  // past the goal the meter does not just fill up, it grows out of its box, OVER_PX per PR too many, so the
  // overshoot is a length and not only a colour. The scale then spans the count, with the goal ticked inside it.
  const over = Math.max(0, g.open - g.max), span = g.max + over;
  const pct = (n) => (100 * n / span).toFixed(1) + '%';
  const why = esc(`${g.open} open PRs in ${g.repo}.\n`
    + [g.max, g.target].map((t) => (g.open <= t ? `${t}: reached, ${t - g.open} to spare` : `${g.open - t} to go to ${t}`)).join('\n'));
  const html = `<a href="${esc(g.url)}" target="_blank" rel="noopener" title="${why}">
    <span class="cap">${g.open} open PRs${trend('open_prs', true, true, true)}</span>
    <span class="meter" style="width:calc(11rem + min(${over * OVER_PX}px, 20rem))"><span class="bar ${over ? 'alarm' : ''}" style="--t:${pct(g.target)};--g:${pct(g.max)}">${g.queue ? `<span class="queue" style="right:${pct(span - g.open)};width:${pct(Math.min(g.queue, g.open))}"></span>` : ''}<span class="rest" style="left:${pct(g.open)}"></span><span class="tick" style="left:${pct(g.target)}"></span>${over ? `<span class="tick" style="left:${pct(g.max)}"></span>` : ''}</span>
      <span class="scale"><span style="left:0">0</span><span style="left:${pct(g.target)};transform:translateX(-50%)">${g.target}</span>${over
        ? `<span style="left:${pct(g.max)};transform:translateX(-50%)">${g.max}</span><span class="over" style="right:0">${g.open}</span>`
        : `<span style="right:0">${g.max}</span>`}</span>${g.queue ? dwarf(g.queue, pct(g.open)) : ''}${g.queue && g.queue_eta
        ? `<span class="eta" id="queue-eta" style="left:calc(${pct(g.open)} + 1.6rem)"></span>` : ''}</span></a>`;
  if (html !== prgoalHtml) { // rebuilding the same meter would restart the alarm's beat mid-cycle for nothing
    prgoalHtml = html;
    $('#prgoal').innerHTML = html;
  }
  // and when it does have to be rebuilt, the beat picks up where the old one stood: it runs on the wall clock
  const bar = $('#prgoal .bar.alarm');
  if (bar) bar.style.animationDelay = `-${Date.now() % (2 * ALARM_MS)}ms`;
  // the same for the swing and the flash it sets off, which have to stay in step with each other above all
  const swing = `-${Date.now() % QUEUE_MS}ms`;
  document.querySelectorAll('.dwarf .arm, #prgoal .queue').forEach((el) => { el.style.animationDelay = swing; });
  // [impl->req~merge-queue-dwarf~5] queue empty = no work at the bar, so he is off wandering instead
  renderEta();
  wander(!g.queue);
}

// [impl->req~bonus-points~21] the +100 awards a contributor holds, one emoji each, the category in the tooltip.
// The emoji links to what earned it - the record's PR or a GitHub search; an award with no such page opens the
// contributor's detail view instead.
function bonusLink(b, login, inner) {
  const why = esc(`+${b.points} ${b.title}: ${b.text}`);
  return b.url ? `<a class="bonus" href="${esc(b.url)}" target="_blank" rel="noopener" title="${why}">${inner}</a>`
    : `<a class="bonus" href="#user/${encodeURIComponent(login)}" title="${why}">${inner}</a>`;
}
// newest sticker first: the one just earned is what somebody walking past the wall should spot
const freshest = (l) => [...(l.bonuses || [])].sort((a, b) => (b.since || '').localeCompare(a.since || ''));
function bonusRow(l) { // always rendered, empty included: equal heights keep the leaderboard on one baseline
  return `<div class="bonuses">${freshest(l).map((b) => bonusLink(b, l.login, b.emoji)).join('')}</div>`;
}

// The nerd corner holds more than fits: the detected refactorings and the funny records (longest identifier,
// most code deleted, ...) take turns, NERD_PAGE lines at a time, so the whole set is readable from the wall.
// [impl->req~nerd-corner~6]
// [impl->req~nerd-records~3]
const NERD_PAGE = 4, NERD_MS = 12000;
let nerdPage = 0, nerdTimer;

// What makes two lines feel like the same line: a record's category, or a detected fact's leading word ("deleted
// Foo, Bar" vs "deleted Baz"). [impl->req~nerd-variety~1]
const nerdKind = (r) => r.title || r.text.split(' ')[0];

// A page must not read as four times "deleted" by the same person. Greedy round-robin: of the items left, take the
// one whose kind and author sit furthest back in the page being filled, ties going to the higher-weighted item.
function nerdOrder(items) {
  const out = [], rest = [...items];
  while (rest.length) {
    const recent = out.slice(1 - NERD_PAGE).reverse();
    const seen = (r) => {
      const k = recent.findIndex((p) => nerdKind(p) === nerdKind(r)), a = recent.findIndex((p) => p.author === r.author);
      return (k < 0 ? 0 : NERD_PAGE - k) + (a < 0 ? 0 : NERD_PAGE - a);
    };
    const best = rest.reduce((b, r) => (seen(r) < seen(b) ? r : b));
    out.push(...rest.splice(rest.indexOf(best), 1));
  }
  return out;
}

function renderNerd() {
  const items = nerdOrder([...data.refactorings.map((r) => ({...r, title: ''})), ...(data.records || [])]);
  const pages = Math.ceil(items.length / NERD_PAGE) || 1;
  nerdPage %= pages;
  $('#refactorings').innerHTML = items.slice(nerdPage * NERD_PAGE, (nerdPage + 1) * NERD_PAGE).map((r) =>
    `<li>${avatar(r.author)}${r.title ? `<span class="title">${r.emoji || ''} ${esc(r.title)}:</span>` : ''}<span class="what">${esc(r.text)}</span>${link(r.url, `${esc(r.repo)}#${r.number}`, 'repo')}</li>`).join('');
  clearInterval(nerdTimer);
  nerdTimer = setInterval(() => { nerdPage++; renderNerd(); }, NERD_MS);
}

// Slot machine: new numbers do not just appear, they spin into place, lowest contributor first and the leader last,
// the whole board settled within SLOT_TOTAL_MS. A reel that has not had its turn shows the previous total, grayed.
// Within a reel the digits lock right to left, and the moment one stands still its gain pops out of it, so each
// contributor gets their own roll-then-points beat before the next reel takes over.
// One interval drives every reel; the next render's call cancels it, which also drops the then-stale nodes.
// [impl->req~leaderboard-slot-machine~5]
const SLOT_TOTAL_MS = 30000, SLOT_ROLL_MS = 2500, POP_MS = 5000;
let slotTimer, popTimers = [];
// The bell rings at once, the toast naming the new leader waits for the reels and the pops. Nothing pending means it rings now
// (still mode, reduced motion, first load). A new render flushes what is still queued: it belongs to older data.
// [impl->req~leader-change-bell~3]
let slotsRunning = false, afterSlots = [];
function whenSlotsSettled(fn) { slotsRunning ? afterSlots.push(fn) : fn(); }
function settleSlots() { slotsRunning = false; const queue = afterSlots; afterSlots = []; queue.forEach((fn) => fn()); }
function slotMachine() {
  clearInterval(slotTimer);
  popTimers.forEach(clearTimeout); // pending pops point at the leaderboard nodes this render is replacing
  popTimers = [];
  settleSlots();
  const reels = [...document.querySelectorAll('#leaderboard .pts')].reverse();
  if (!reels.length || document.documentElement.classList.contains('still') || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const was = Object.fromEntries((previous?.leaderboard || []).map((l) => [l.login, l.points]));
  const plan = reels.map((el, i) => {
    const final = el.textContent.replace(/,/g, ''), before = was[el.parentElement.dataset.login];
    el.textContent = group(String(before ?? final));
    el.classList.add('pending');
    return { el, final, gain: before == null ? 0 : Number(final) - before, start: i * (SLOT_TOTAL_MS - SLOT_ROLL_MS) / Math.max(1, reels.length - 1) };
  });
  slotsRunning = true;
  const t0 = performance.now();
  slotTimer = setInterval(() => {
    const t = performance.now() - t0;
    let running = false;
    for (const r of plan) {
      if (t < r.start || r.settled) { running = running || !r.settled; continue; }
      const locked = Math.floor(r.final.length * (t - r.start) / SLOT_ROLL_MS); // digits held from the right
      r.el.classList.remove('pending');
      r.el.classList.toggle('rolling', locked < r.final.length);
      r.el.textContent = group([...r.final].map((d, i) => (i >= r.final.length - locked ? d : Math.floor(Math.random() * 10))).join(''));
      if (locked < r.final.length) { running = true; continue; }
      r.settled = true;
      popPoints(r.el, r.gain); // this reel's gain, right where it stopped, before the next reel takes over
    }
    if (running) return;
    clearInterval(slotTimer);
    popTimers.push(setTimeout(settleSlots, POP_MS)); // the last gain still has to fly off
  }, 60);
}

// Where the gain came from, in three words under the "+n". A data run does not only bring new events: it also
// re-scores earlier work (a focus label added to an item multiplies its events by ten, a resolved diff complexity
// changes what a review was worth), credits a merge to the PR's author, or counts private-repo work that no ticker
// row may name. Those gains have nothing recent in "Latest activity" to point at, which is exactly what looks wrong.
// [impl->req~gain-source~1]
function gainSource(login) {
  const was = (previous?.leaderboard || []).find((l) => l.login === login), now = data.leaderboard.find((l) => l.login === login);
  if (!was || !now) return '';
  const held = new Set((was.bonuses || []).map((b) => b.title));
  const sticker = (now.bonuses || []).find((b) => !held.has(b.title));
  if (sticker) return `${sticker.emoji} ${sticker.title} sticker`;
  if (now.merged > was.merged) return 'merged PR';
  if (now.reviews > was.reviews) return 'review';
  const priv = (d) => Object.values(d.private_activity || {}).reduce((n, c) => n + (c.by?.[login] || 0), 0);
  if (priv(data) > priv(previous)) return 'private repo work';
  if (now.other > was.other) return 'comment, push or issue';
  return 'earlier work re-scored';
}

// The gain jumps out of the reel, hangs there long enough to be read, then flies off the top of the screen and
// settles as a badge over the avatar. A contributor who gained nothing gets a bare +0, so every reel has its beat.
// Fixed and on <body>, so no ancestor of the fixed video is transformed.
// [impl->req~leaderboard-slot-machine~5]
function popPoints(el, gain) {
  if (gain < 0) return;
  const why = gain ? gainSource(el.parentElement.dataset.login) : ''; // nothing gained, nothing to explain
  const box = el.getBoundingClientRect(), pop = document.createElement('div');
  pop.className = 'pop';
  pop.innerHTML = `+${fmt(gain)}${why ? `<i>${esc(why)}</i>` : ''}`;
  pop.style.left = `${box.left + box.width / 2}px`;
  pop.style.top = `${box.top}px`;
  document.body.appendChild(pop);
  pop.animate([{ transform: 'translate(-50%, 0) scale(1)', opacity: 1 },
    { transform: 'translate(-50%, -1.5rem) scale(1.8)', opacity: 1, offset: 0.1 },
    { transform: 'translate(-50%, -2rem) scale(1.8)', opacity: 1, offset: 0.55 },
    { transform: `translate(-50%, ${-box.top - 40}px) scale(1.2)`, opacity: 0 }],
  { duration: POP_MS, easing: 'cubic-bezier(.3,.9,.4,1)' }).onfinish = () => {
    pop.remove();
    const badge = document.createElement('div'); // survives until the next render, so the last gain stays readable
    badge.className = 'delta';
    badge.textContent = `+${fmt(gain)}`;
    badge.title = why;
    el.parentElement.appendChild(badge);
  };
}


// Pie chart of the AI assistants credited in the merged PRs' commits, legend on its right.
// [impl->req~ai-models~1]
function renderAiModels() {
  const models = Object.entries(data.ai_models || {});
  const total = models.reduce((sum, [, n]) => sum + n, 0);
  $('#aimodels').hidden = !total;
  if (!total) return;
  let acc = 0;
  const slices = models.map(([, n], i) => {
    const from = 100 * acc / total;
    acc += n;
    return `${COLORS[i % COLORS.length]} ${from.toFixed(2)}% ${(100 * acc / total).toFixed(2)}%`;
  });
  $('#aimodels .chart').innerHTML = `<div class="pie" style="background:conic-gradient(${slices.join(',')})"></div>
    <ul class="legend">${models.map(([name, n], i) =>
      `<li><i style="background:${COLORS[i % COLORS.length]}"></i>${esc(name)} <span class="muted">${n}</span></li>`).join('')}</ul>`;
}

// Mirrors the scoring in collect.py: merged PR (author) 3, review 1..3 by the complexity of the reviewed diff, comment / issue / push / PR opened or closed unmerged 1; tenfold on a JabCon
// item, times config.repo_factors elsewhere (keys are repos or orgs: the JabRef org, upstream JavaFX work).
// [impl->req~scoring~9]
// [impl->req~no-self-review-points~1]
// [impl->req~no-fork-sync-points~1]
const cardOf = (e) => data.cards.find((c) => c.repo === e.repo && c.number === e.number);
// the feed is inconsistent about the merged flag: some merges only say so in the action, and dropping those cost the
// author the three points collect.py credits them from the card
const isMerge = (e) => e.type === 'PullRequestEvent' && (e.merged || e.action === 'merged');
const reviewPoints = (cc) => (cc == null ? 2 : cc <= 2 ? 1 : cc >= 20 ? 3 : 2);
const boostText = () => Object.entries(data.config.repo_factors || {}).filter(([, f]) => f !== 1).map(([r, f]) => `${r} × ${f}`).join(', ') || 'boosted repos';
const NOSCORE = { CreateEvent: 'creating a branch or tag', DeleteEvent: 'deleting a branch', WatchEvent: 'starring a repo', ForkEvent: 'forking a repo', MemberEvent: 'a membership change', PullRequestReviewCommentEvent: 'a review comment (its review scored)' };
// What the event is worth before the factor, and the words for it, so the score and its explanation cannot drift apart.
// [impl->req~points-tooltip~2]
function eventBase(e) {
  const card = cardOf(e);
  if (e.self) return [0, 'review on own PR'];
  if (e.sync) return [0, 'fork sync'];
  if (e.ai) return [0, 'written by an AI assistant']; // [impl->req~no-ai-comment-points~1]
  if (e.type === 'PullRequestReviewEvent') {
    const cc = card?.stats?.complexity;
    return [reviewPoints(cc), `review of a ${cc == null ? 'diff of unknown complexity' : cc <= 2 ? 'trivial' : cc >= 20 ? 'complex' : 'medium'} diff`];
  }
  if (e.type === 'PushEvent') return [1, 'push'];
  if (e.type === 'IssueCommentEvent') return [1, 'comment'];
  // [impl->req~mailing-lists~1]
  if (e.type === 'MailEvent') return [1, 'mailing list post'];
  if (e.type === 'IssuesEvent') return ['labeled', 'unlabeled'].includes(e.action) ? [0, 'labeling (a workflow looks like triage)'] : [1, `issue ${e.action}`];
  if (e.type === 'PullRequestEvent' && (e.action === 'opened' || (e.action === 'closed' && !isMerge(e)))) return [1, `PR ${e.action}`];
  if (isMerge(e) && card?.column === 'done' && card.author === e.actor) return [3, 'merged PR'];
  if (e.type === 'PullRequestEvent') return [0, isMerge(e) ? 'a merge scores for the PR author only' : `PR ${e.action}: only opening and closing score`];
  return [0, NOSCORE[e.type] || 'this kind of event never scores'];
}
// [impl->req~points-tooltip~2]
function eventFactor(e) {
  const rf = data.config.repo_factors || {}, org = e.repo.split('/')[0];
  if (cardOf(e)?.focus) return [10, 'JabCon item'];
  if (rf[e.repo]) return [rf[e.repo], e.repo];
  if (rf[org]) return [rf[org], org];
  return [1, ''];
}
const eventPoints = (e) => eventBase(e)[0] * eventFactor(e)[0];
// [impl->req~points-tooltip~2]
function pointsWhy(e) {
  const [base, what] = eventBase(e), [f, where] = eventFactor(e);
  if (!base) return `no points: ${what}`;
  return f === 1 ? `${what}: ${base}` : `${what} ${base} × ${f} (${where}) = ${base * f}`;
}

// [impl->req~ticker-deep-links~1]
// [impl->req~event-titles~1]
function eventRow(e) {
  const org = data.config.org + '/', pts = eventPoints(e), card = cardOf(e);
  const title = card && !e.summary.includes(card.title) ? card.title : ''; // most summaries carry it already; reviews do not
  return `<li class="${e.repo.startsWith(org) ? '' : 'other'}">${avatar(e.actor)}<span class="when">${ago(e.created_at)}</span>${link(e.number ? `https://github.com/${e.repo}/issues/${e.number}` : e.url, `<span class="what"><span class="line"><b>${esc(e.actor)}</b> ${esc(e.summary.replace(' (commented)', ''))}${title ? ` <span class="subject">${esc(title)}</span>` : ''}</span>${e.excerpt ? `<span class="excerpt">“${esc(e.excerpt)}”</span>` : ''}</span>`, 'main')}<span class="pts${pts ? '' : ' zero'}" title="${esc(pointsWhy(e))}">+${pts}</span>${repoLink(e.repo, e.repo.startsWith(org) ? e.repo.slice(org.length) : e.repo)}</li>`;
}

// The two groups share one window of the newest events instead of the JabCon group getting a fixed five rows:
// the ticker is clipped, so a fixed block pushed the newest activity out of sight whenever JabCon items were quiet.
// The divider therefore moves with how much recent activity is on JabCon items.
// [impl->req~activity-grouped~2]
// [impl->req~newsticker~4] one strip of headlines along the bottom, phrased from the board's data like the gource
// commentary: the tally, the latest merges, what is still left, and who earned which sticker. Seeded by PR number so
// a refresh says the same things, and only re-rendered on a change, so the scroll never jumps back.
const FRESH_MS = 3 * 3600000; // a sticker counts as just earned for this long
const CATCHUP_MS = 6 * 3600000, QUIET_MS = 16 * 3600000; // the catch-up window, and how long a pause must be to be "back" from (a night is 8-10 h)
function newsItems() {
  const merged = data.cards.filter((c) => c.merged_at).sort((a, b) => b.merged_at.localeCompare(a.merged_at));
  const closed = data.cards.filter((c) => c.type === 'issue' && c.column === 'done');
  const items = [[`JabCon ${new Date(data.config.jabcon_start).getFullYear()}: ${merged.length} PRs merged, ${closed.length} issues closed, +${fmt(data.stats.additions)} / −${fmt(data.stats.deletions)} lines`]];
  const big = ['WHAT A MONSTER! {who} lands {title}: {add} lines added, {del} gone!', 'The crowd is on its feet! {who} with {title}, {add} new lines!', "That's a heavyweight from {who}: {title}. {add} lines added, {del} removed!"];
  const mid = ['{who} slots it in: {title}. {add} lines, clean finish.', 'Nicely worked by {who}: {title}.', 'And {who} delivers: {title}. {add} lines added.'];
  const small = ['A quick one from {who}: {title}.', '{who} keeps it tidy: {title}.', 'Tap-in for {who}: {title}.'];
  const reviewed = [' {rev} waves it through.', ' Reviewed by {rev}, no complaints.', ' {rev} had a look first, all clear.'];
  // [impl->req~release-party~1]
  if (data.release) items.push([`\u{1f3f7}\u{fe0f} ${data.release.repo} ${data.release.name} released ${ago(data.release.at)}`, data.release.url]);
  // [impl->req~sticker-moves~1]
  if (changes.points.length) items.push([`Latest run (${ago(changes.at)}): ${changes.points.map(([l, d]) => `${l} ${d > 0 ? '+' : '−'}${fmt(Math.abs(d))}`).join(', ')}`]);
  for (const m of changes.moves) items.push([moveText(m), `#user/${encodeURIComponent(m.to[0])}`]);
  for (const c of merged.slice(0, 8)) {
    const st = c.stats || {}, size = (st.additions || 0) + (st.deletions || 0);
    const bank = size > 800 ? big : size > 150 ? mid : small;
    let text = bank[c.number % bank.length].replace('{who}', c.author).replace('{title}', c.title).replace('{add}', fmt(st.additions || 0)).replace('{del}', fmt(st.deletions || 0));
    const revs = [...new Set(data.all_events.filter((e) => e.type === 'PullRequestReviewEvent' && e.repo === c.repo && e.number === c.number && e.actor !== c.author).map((e) => e.actor))];
    if (revs.length) text += reviewed[c.number % reviewed.length].replace('{rev}', revs.slice(0, 2).join(' and '));
    items.push([text, c.url]);
  }
  // no name: the card knows its author and assignee, neither of whom is necessarily who closed it
  for (const c of closed.slice(0, 5)) items.push([`Closed: #${c.number} ${c.title}`, c.url]);
  const backlog = data.cards.filter((c) => c.column === 'backlog');
  if (backlog.length) items.push([`Still waiting: ${backlog.length} items in the backlog — ${backlog.slice(0, 3).map((c) => `#${c.number} ${c.title}`).join(', ')}${backlog.length > 3 ? ', …' : ''}`]);
  for (const m of data.milestones) items.push([`${m.title}: ${m.open ? `${m.open} to go, ` : 'done! '}${m.closed - m.baseline} closed during JabCon`, m.url]);
  if (data.focus) items.push([`${data.focus.label}: ${data.focus.closed} done, ${data.focus.open} open`, data.focus.url]);
  const [lead, second] = data.leaderboard;
  if (lead) items.push([`${lead.login} leads the table with ${fmt(lead.points)} points${second ? `, ${second.login} is ${fmt(lead.points - second.points)} behind` : ''}`, `#user/${encodeURIComponent(lead.login)}`]);
  // [impl->req~catch-up~1] the race: who scored most in the last hours, who is closing in on the place above, who is back
  const since = Date.now() - CATCHUP_MS, participants = new Set(data.config.participants);
  const recent = {}, latest = {}, before = {};
  for (const e of data.all_events) { // newest first
    if (!participants.has(e.actor)) continue;
    const t = Date.parse(e.created_at);
    if (t >= since) recent[e.actor] = (recent[e.actor] || 0) + eventPoints(e);
    if (!(e.actor in latest)) latest[e.actor] = t;
    else if (!(e.actor in before) && latest[e.actor] - t > QUIET_MS) before[e.actor] = t; // the pause that ended with their latest event
  }
  const hours = CATCHUP_MS / 3600000, user = (l) => `#user/${encodeURIComponent(l)}`;
  const gainers = Object.entries(recent).filter(([, p]) => p > 0).sort((a, b) => b[1] - a[1]);
  const pts = (p) => `${fmt(p)} point${p === 1 ? '' : 's'}`;
  for (const [l, p] of gainers.slice(0, 3)) items.push([`${l} scored ${pts(p)} in the last ${hours} hours`, user(l)]);
  data.leaderboard.forEach((l, i) => {
    const above = data.leaderboard[i - 1];
    const gap = above ? above.points - l.points : Infinity; // only a gap this pace closes within a day or so counts as catching up
    if (above && (recent[l.login] || 0) > (recent[above.login] || 0) && gap <= 5 * recent[l.login])
      items.push([`${l.login} is catching up on ${above.login}: ${pts(gap)} behind, ${pts(recent[l.login])} scored in the last ${hours} hours`, user(l.login)]);
  });
  for (const [l, t] of Object.entries(before)) if (latest[l] >= since) items.push([`${l} is back after ${Math.round((latest[l] - t) / 3600000)} hours of silence`, user(l)]);
  // [impl->req~sticker-since~1] freshly earned stickers come first and say so
  const stickers = data.leaderboard.flatMap((l) => (l.bonuses || []).map((b) => [l, b])).sort(([, a], [, b]) => (b.since || '').localeCompare(a.since || '')).map(([l, b]) => {
    const fresh = b.since && Date.now() - new Date(b.since) < FRESH_MS;
    return [`${b.emoji} ${l.login} ${fresh ? 'just earned' : 'holds'} the ${b.title} sticker: ${b.text}`, b.url || user(l.login)];
  });
  // [impl->req~newsticker~4] one sticker between every two headlines, so a screen width is never stickers only
  const mixed = [];
  for (let i = 0; i < Math.max(items.length, stickers.length); i++) mixed.push(...items.slice(i, i + 1), ...stickers.slice(i, i + 1));
  return mixed;
  return items;
}
function renderNews() {
  const items = newsItems();
  const strip = $('#news span');
  const html = items.map(([t, url]) => (url ? link(url, esc(t), 'headline') : esc(t))).join('<i>✦</i>');
  if (strip.innerHTML === html) return;
  // The marquee's elapsed time keeps growing, so where it stands is (elapsed mod duration). After a few hours on the
  // wall that quotient is large, and the second the duration changes - one headline's "3 min ago" ticking over is
  // enough - the strip lands somewhere random and never gets through the list. So carry the position over by hand.
  const anim = strip.getAnimations()[0], was = anim && anim.currentTime / anim.effect.getTiming().duration % 1;
  strip.innerHTML = html;
  strip.style.animationDuration = `${Math.max(20, items.reduce((n, [t]) => n + t.length, 0) / 6)}s`;
  if (anim) anim.currentTime = was * anim.effect.getTiming().duration;
}

// [impl->req~news-scrub~1] The strip is one CSS animation, so dragging it is just scrubbing that animation:
// pixels become milliseconds through the strip's own width and duration. Clicking a separator opens the full list,
// for when the headline that just went past is worth reading properly.
let newsDrag = 0;
$('#news').addEventListener('pointerdown', (e) => {
  const strip = $('#news span'), anim = strip.getAnimations()[0];
  if (!anim) return; // reduced motion: nothing to scrub
  const perPx = anim.effect.getTiming().duration / strip.offsetWidth, x0 = e.clientX, t0 = anim.currentTime;
  anim.pause();
  newsDrag = 0;
  const move = (ev) => {
    newsDrag = Math.max(newsDrag, Math.abs(ev.clientX - x0));
    anim.currentTime = Math.max(0, t0 - (ev.clientX - x0) * perPx); // drag right, go back in time
  };
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', () => { document.removeEventListener('pointermove', move); anim.play(); }, { once: true });
});
$('#news').addEventListener('click', (e) => {
  if (newsDrag > 4) return e.preventDefault(); // the drag ended on a headline; that is not a click on it
  if (e.target.tagName === 'I') { pushedDetail = true; location.hash = 'news'; }
});

// [impl->req~news-scrub~1]
function showNewsList() {
  const cell = (t) => `<span class="what"><span class="line">${esc(t)}</span></span>`;
  $('#detail h2').innerHTML = 'Headlines <span class="muted">everything the strip is saying, in order</span>';
  $('#detail ul').innerHTML = newsItems().map(([t, url]) => `<li>${url ? link(url, cell(t), 'main') : cell(t)}</li>`).join('');
  $('#detail').hidden = false;
}

// A merge scores 3 x the factor for the PR's author, but merging is the merger's event, not the author's: without a
// row of its own the ticker cannot show what the author's total (and the "merged" toast) just got.
// [impl->req~merge-credit-rows~1]
function mergeCredits() {
  const own = new Set(data.events.filter(isMerge).map((e) => `${e.actor}@${e.repo}#${e.number}`));
  const participants = new Set(data.config.participants);
  return data.cards.filter((c) => c.type === 'pr' && c.merged_at && participants.has(c.author) && !own.has(`${c.author}@${c.repo}#${c.number}`))
    .map((c) => ({ type: 'PullRequestEvent', action: 'closed', merged: true, actor: c.author, repo: c.repo, number: c.number,
      created_at: c.merged_at, summary: `got #${c.number} merged`, url: c.url, excerpt: '' }));
}

function renderTicker() {
  const recent = [...data.events.filter((e) => e.type !== 'PullRequestReviewCommentEvent'), ...mergeCredits()]
    .sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 25);
  const jabcon = recent.filter((e) => cardOf(e)?.focus), rest = recent.filter((e) => !cardOf(e)?.focus);
  $('#ticker').innerHTML = jabcon.map(eventRow).join('') + (jabcon.length ? '<li class="divider">other</li>' : '') + rest.map(eventRow).join('');
}

// Click on a leaderboard avatar: full-screen list of everything that contributor scored (or did not) during JabCon.
// [impl->req~contributor-detail~2]
// Click a part of the points breakdown: the list below shrinks to the events that part is made of, so a surprising
// total can be traced to its rows. One segment at a time, and a Clear chip to get back.
// [impl->req~breakdown-filter~1]
const SEGMENTS = {
  merged: (e) => eventBase(e)[1] === 'merged PR',
  ai: (e) => eventBase(e)[1] === 'merged PR' && !!cardOf(e)?.stats?.ai,
  reviews: (e) => e.type === 'PullRequestReviewEvent' && eventBase(e)[0] > 0,
  other: (e) => eventBase(e)[0] > 0 && e.type !== 'PullRequestReviewEvent' && eventBase(e)[1] !== 'merged PR',
  milestone: (e) => eventPoints(e) > 0 && eventFactor(e)[1] === 'JabCon item',
  boosted: (e) => eventPoints(e) > 0 && eventFactor(e)[0] !== 1 && eventFactor(e)[1] !== 'JabCon item',
};
let segment = null, segmentOf = null; // the active segment, and whose detail view it belongs to
const seg = (key, text) => `<button class="seg${segment === key ? ' on' : ''}" data-seg="${key}">${text}</button>`;

function showDetail(login) {
  const l = data.leaderboard.find((x) => x.login === login) || { points: 0, merged: 0, reviews: 0, other: 0 };
  if (segmentOf !== login) { segment = null; segmentOf = login; }
  let events = (data.all_events || []).filter((e) => e.actor === login && e.type !== 'PullRequestReviewCommentEvent')
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  if (segment) events = events.filter(SEGMENTS[segment]);
  $('#detail h2').innerHTML = `${avatar(login)} ${esc(login)} <span class="muted">${fmt(l.points)} points · ${seg('merged', `${l.merged} merged × 3`)} (${seg('ai', `${l.ai || 0} AI-assisted × 0.25`)}) · ${seg('reviews', `${l.reviews} reviews × 1..3`)} · ${seg('other', `${l.other} other × 1`)} · ${seg('milestone', `${l.milestone || 0} on JabCon items × 10`)} · ${seg('boosted', `${l.boosted || 0} in ${boostText()}`)}${segment ? ' <button class="seg clear" data-seg="">✕ clear filter</button>' : ''}</span>`;
  $('#detail h2').innerHTML += freshest(l).map((b) => ' ' + bonusLink(b, login, `${b.emoji} ${esc(b.title)} +${b.points}`)).join('');
  // [impl->req~delta-detail~2] why the number moved: guessing from the ticker alone is not possible
  const moved = deltaWhy(login), gain = trend((s) => s.points?.[login], false, true, true);
  $('#detail h2').innerHTML += gain
    ? `<div class="moved">${gain} in the last hour${moved.length ? ': ' + moved.map(esc).join(' · ') : ''}</div>` : '';
  $('#detail ul').innerHTML = events.map(eventRow).join('')
    || `<li class="muted">${segment ? 'no events of this kind in the collected activity' : 'no public activity yet'}</li>`;
  $('#detail').hidden = false;
}
// [impl->req~breakdown-filter~1]
$('#detail h2').addEventListener('click', (e) => {
  const key = e.target.closest('.seg')?.dataset.seg;
  if (key === undefined) return;
  segment = segment === key || !key ? null : key;
  showDetail(segmentOf);
});
// Click a component row: the merged PRs that touched it, biggest first, so a surprising total (32k removed lines,
// say) can be traced back to the PRs it came from.
// [impl->req~component-detail~1]
function showComponentDetail(name) {
  segment = segmentOf = null;
  const lines = (c) => c.stats.components[name];
  const prs = data.cards.filter((c) => c.stats?.components?.[name]).sort((a, b) => lines(b) - lines(a));
  const total = prs.reduce((sum, c) => sum + lines(c), 0);
  const totalNet = prs.reduce((sum, c) => sum + (c.stats.components_net?.[name] ?? 0), 0);
  $('#detail h2').innerHTML = `${esc(name)} <span class="muted">${fmt(total)} lines changed ${net(totalNet)} in ${prs.length} PR${prs.length === 1 ? '' : 's'}, biggest first</span>`;
  $('#detail ul').innerHTML = prs.map((c) => `<li>${avatar(c.author)}${link(c.url,
    `<span class="what"><span class="line"><b>#${c.number}</b> ${esc(c.title)}</span></span>`, 'main')}<span class="pts" title="${esc(`lines changed in ${name}`)}">${fmt(lines(c))}</span><span class="add" title="over the whole PR">+${fmt(c.stats.additions || 0)}</span><span class="del" title="over the whole PR">\u2212${fmt(c.stats.deletions || 0)}</span>${repoLink(c.repo, c.repo)}</li>`).join('')
    || '<li class="muted">no PRs recorded for this component</li>';
  $('#detail').hidden = false;
}

// The detail view is a route (#user/<login>, #component/<name>), so the browser's Back button and a shared link both work.
// [impl->req~contributor-detail~2]
// [impl->req~component-detail~1]
let pushedDetail = false; // only then is a history.back() ours to take; a deep link must not leave the site
function route() {
  const [, kind, arg] = location.hash.match(/^#(user|component)\/(.+)$/) || [];
  if (arg && data) (kind === 'user' ? showDetail : showComponentDetail)(decodeURIComponent(arg));
  else if (location.hash === '#news' && data) showNewsList();
  else { $('#detail').hidden = true; pushedDetail = pushedDetail && !!arg; }
}
function closeDetail() {
  if (pushedDetail) history.back();
  else location.replace('#');
}
window.addEventListener('hashchange', route);
$('#detail .back').addEventListener('click', closeDetail);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetail(); });
$('#leaderboard').addEventListener('click', (e) => {
  if (e.target.closest('a')) return; // a bonus emoji links to what earned it, the detail view must not steal the click
  const who = e.target.closest('.leader')?.dataset.login;
  if (who) { pushedDetail = true; location.hash = `user/${encodeURIComponent(who)}`; }
});

// [impl->req~component-detail~1]
$('#components').addEventListener('click', (e) => {
  const comp = e.target.closest('[data-comp]')?.dataset.comp;
  if (comp) { pushedDetail = true; location.hash = `component/${encodeURIComponent(comp)}`; }
});

// [impl->req~leader-change-bell~3]
// [impl->req~done-confetti~2]
// [impl->req~sticker-moves~1] what the latest data run changed: points gained per contributor and stickers that
// changed hands. Kept until the next change, so the newsticker can tell it; a hand-over is also toasted.
let changes = { at: null, points: [], moves: [] };
function noteChanges(prev) {
  if (!prev) return;
  const holders = (board) => {
    const h = {};
    for (const l of board) for (const b of l.bonuses || []) (h[b.title] ||= { emoji: b.emoji, logins: new Set() }).logins.add(l.login);
    return h;
  };
  const was = holders(prev.leaderboard), now = holders(data.leaderboard), moves = [];
  for (const [title, { emoji, logins }] of Object.entries(now)) {
    const before = was[title]?.logins || new Set();
    const gained = [...logins].filter((l) => !before.has(l)), lost = [...before].filter((l) => !logins.has(l));
    if (gained.length) moves.push({ emoji, title, from: lost, to: gained });
  }
  const pts = Object.fromEntries(prev.leaderboard.map((l) => [l.login, l.points]));
  const points = data.leaderboard.map((l) => [l.login, l.points - (pts[l.login] ?? l.points)]).filter(([, d]) => d).sort((a, b) => b[1] - a[1]);
  if (moves.length || points.length) changes = { at: data.generated_at, points, moves };
}
const moveText = (m) => `${m.emoji} the ${m.title} sticker ${m.from.length ? `moves from ${m.from.join(' and ')} to ${m.to.join(' and ')}` : `goes to ${m.to.join(' and ')}`}`;

function celebrate(prev) {
  if (!prev) return;
  for (const m of changes.at === data.generated_at ? changes.moves : []) whenSlotsSettled(() => toast(moveText(m)));
  const leader = data.leaderboard[0]?.login, wasLeader = prev.leaderboard[0]?.login;
  if (leader && wasLeader && leader !== wasLeader) {
    bell(); // the bell opens the act: it makes the room look up while the reels are still rolling
    whenSlotsSettled(() => toast(`🔔 ${leader} takes the lead!`)); // the name comes once the numbers stand
  }
  // [impl->req~pr-goal-fanfare~1] the meter's big moment: the open PRs drop to the stretch target or below
  const g = data.pr_goal, was = prev.pr_goal;
  if (g && was && was.open > g.target && g.open <= g.target) {
    bell();
    toast(`\u{1f3af} ${g.open} open PRs \u2014 the ${g.target} mark is reached!`);
    if (window.confetti) confetti({ particleCount: 300, spread: 120, origin: { y: 0.6 } });
  }
  // [impl->req~release-party~1] a tag we had not seen in the run before; a first-ever reading is no release
  if (data.release && prev.release && data.release.tag !== prev.release.tag) releaseParty(data.release);
  const before = new Set(prev.cards.filter((c) => c.column === 'done').map((c) => c.id));
  for (const c of data.cards.filter((c) => c.column === 'done' && !before.has(c.id))) {
    // the name is the author, not the merger: credit it with "by", never as the one who merged
    if (c.type === 'pr')
      toast(`🎉 PR #${c.number} ${c.title} by ${c.author} ${c.merged_at ? 'merged' : 'closed'}`);
    else
      toast(`🎉 ${c.assignees[0] || c.author} closed #${c.number} ${c.title}`);
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

// [impl->req~release-party~1] The moment the hammering was for: a new tag on the goal repo. The bell rings, the
// confetti keeps coming for a minute and a chorus line of dwarfs dances along the bottom edge.
const PARTY_MS = 60000, PARTY_DWARFS = 9, PARTY_BURST_MS = 1500;
let partyTimer = 0;
function releaseParty(rel) {
  bell();
  toast(`\u{1f3f7}\u{fe0f} ${rel.repo} ${rel.name} is out!`);
  // the same rule as the wandering dwarf: reduced motion or a board held still gets the news, not the dance
  if (document.documentElement.classList.contains('still') || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  clearTimeout(partyTimer);
  $('#party')?.remove();
  // each dwarf a beat behind the one before, so the row reads as a dance and not as one animation nine times
  document.body.insertAdjacentHTML('beforeend', `<div id="party" title="${esc(rel.name)} is released!">`
    + Array.from({ length: PARTY_DWARFS }, (_, i) => `<span style="animation-delay:-${i * 120}ms">${dwarfSvg(64)}</span>`).join('')
    + '</div>');
  const until = Date.now() + PARTY_MS;
  (function burst() {
    if (Date.now() > until) { $('#party')?.remove(); return; }
    if (window.confetti) confetti({ particleCount: 120, spread: 100, origin: { y: 0.85, x: Math.random() } });
    partyTimer = setTimeout(burst, PARTY_BURST_MS);
  })();
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
  renderNews();
  renderProgress();
  tick();
  route(); // a deep link renders once the data is there; an open detail view follows the refreshed data
}

// GitHub runs a */5 schedule only best-effort (measured over a night: median 9 min between runs, 40 at worst), so the
// ring is sized for the long end of a healthy gap and only pulses when a run is really missing
const REFRESH_MS = 15 * 60000;

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
  // [impl->req~activity-heat-strip~1]
  const hours = new Array(Math.ceil((end - start) / 3600000)).fill(0);
  for (const e of data.all_events || []) {
    const h = Math.floor((Date.parse(e.created_at) - start) / 3600000);
    if (h >= 0 && h < hours.length) hours[h]++;
  }
  const max = Math.max(1, ...hours);
  $('#heat').innerHTML = hours.map((n, h) => `<span style="--o:${(n / max).toFixed(3)}" title="${fmt(new Date(start + h * 3600000).toISOString())} · ${n} event${n === 1 ? '' : 's'}"></span>`).join('');
}

// [impl->req~refresh-ring~2]
// [impl->req~clock-timezone~1]
function tick() {
  const now = new Date();
  $('#clock').textContent = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data?.config.timezone });
  if (!data) return;
  const age = now - Date.parse(data.generated_at);
  $('#updated').style.setProperty('--p', Math.min(1, age / REFRESH_MS));
  $('#updated').classList.toggle('overdue', age > REFRESH_MS);
  $('#updated').title = `Data freshness: last data run ${ago(data.generated_at)}, the next one is ${age > REFRESH_MS ? 'overdue' : `expected in ${Math.ceil((REFRESH_MS - age) / 60000)} min`}. The ring fills over ${REFRESH_MS / 60000} min, one turn per data run; full and pulsing means the run is late, amber "!" means the data is stale.`;
  $('#data-time').textContent = `data ${new Date(data.generated_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: data.config.timezone })}`;
  $('#header').classList.toggle('stale', age > 30 * 60000);
  renderEta(); // [impl->req~merge-queue-dwarf~5] the queue's countdown runs on the same second as the clock
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

// [impl->req~auto-reload~2]
async function load() {
  try {
    const r = await fetch('data.json?ts=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.statusText);
    const text = await r.text();
    // Re-rendering identical data replaces the node under the mouse, which kills the open title tooltip and
    // shows no new one until the pointer moves again — on a wall display it never does. Only render on a change.
    if (text === raw) return;
    raw = text;
    previous = data;
    data = JSON.parse(text);
    noteChanges(previous);
    render();
    celebrate(previous);
  } catch (e) {
    console.error('load failed', e);
    $('#header').classList.add('stale');
  }
}

const video = $('#gource');
let current = COMMENTARY; // advanced before each load, so the wall starts with the gource run
// [impl->req~gource-alternate~2] the gource run, the highlights reel, the commentated run, and again; every swap fetches the newest rendering
const neighbour = (step) => PLAYLIST[(PLAYLIST.indexOf(current) + step + PLAYLIST.length) % PLAYLIST.length];
function stepVideo(step) {
  current = neighbour(step);
  video.src = `${current}?ts=${Date.now()}`;
  video.play().catch(() => {});
  $('#prev-video').textContent = `◀ ${NAMES[neighbour(-1)]}`; // [impl->req~gource-next~2] buttons name where they lead
  $('#next-video').textContent = `${NAMES[neighbour(1)]} ▶`;
}
const nextVideo = () => stepVideo(1);
video.addEventListener('ended', nextVideo);
$('#next-video').addEventListener('click', nextVideo);
$('#prev-video').addEventListener('click', () => stepVideo(-1));
// load failed: skip to the next video, or (gource itself) hide the player (placeholder shows) and retry in 30 s. Besides "not rendered yet", this
// happens when files.jabref.org swaps the file (every 15 min) under a running download: the browser's next range request
// hits a different ETag and the media errors out.
video.addEventListener('error', () => { if (current !== VIDEO) nextVideo(); else { video.removeAttribute('src'); setTimeout(loadVideo, 30000); } });
// [impl->req~gource-speed~2] re-applied per source: a src swap resets the rate; the reel's crawl is only readable at 1x
video.addEventListener('loadedmetadata', () => { video.playbackRate = current === VIDEO ? 3 : 1; });
// [impl->req~gource-refresh~2]
function loadVideo() { if (!video.getAttribute('src')) nextVideo(); }

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

// version.txt holds the deployed commit and when it was made; shown in the corner so the wall can be told apart
// from what is pushed, and used to reload the page after a new deployment.
// [impl->req~deployed-version~2]
let version;
async function checkVersion() {
  try {
    const r = await fetch('version.txt?ts=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) return;
    const v = (await r.text()).trim();
    if (version && v !== version) location.reload();
    version = v;
    const [sha, iso] = v.split(/\s+/);
    const when = iso && new Date(iso);
    $('#version').textContent = `site ${sha}${when ? ` \u00b7 ${when.toLocaleString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZone: data?.config.timezone })}` : ''}`;
    $('#version').title = when ? `Deployed commit ${sha}, committed ${ago(iso)}. The page reloads itself within five minutes of the next deployment.`
      : `Deployed commit ${sha}. The page reloads itself within five minutes of the next deployment.`;
  } catch (e) { /* offline: try again later */ }
}
checkVersion();
setInterval(checkVersion, 5 * 60000);
