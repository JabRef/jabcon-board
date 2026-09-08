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
const group = (s) => s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');

function ago(iso) {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// [impl->req~column-order~2]
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

// [impl->req~milestones~2]
// [impl->req~leaderboard-breakdown~1]
function renderStats() {
  const s = data.stats;
  $('#totals').innerHTML = `<span>${fmt(s.changed_files)} files</span><span class="add">+${fmt(s.additions)}</span><span class="del">−${fmt(s.deletions)}</span>`;
  const comps = Object.entries(s.components).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const max = comps[0]?.[1] || 1;
  $('#components').innerHTML = comps.map(([name, n]) =>
    `<span>${esc(name)}</span><div class="bar" style="width:${(100 * n / max).toFixed(1)}%"></div><span>${fmt(n)}</span>`).join('');
  const f = data.focus;
  const focusWhy = f && `Issues labeled "${f.label}" across the org — the JabCon focus.\n${f.closed} of ${f.closed + f.open} closed, ${f.open} to go.\nThe green bar is the closed share.`;
  $('#milestones').innerHTML = (f ? `<div class="milestone focus" title="${esc(focusWhy)}"><div class="label">${link(f.url, `${esc(f.label)}`)}
      <span>${f.closed}/${f.closed + f.open} <span class="muted">${f.open} to go</span></span></div>
      <div class="bar"><div class="during" style="width:${(100 * f.closed / (f.closed + f.open || 1)).toFixed(1)}%"></div></div></div>` : '') +
    (data.milestones || []).map((m) => {
    const total = m.open + m.closed || 1, during = m.closed - m.baseline;
    // the label is truncated on narrow screens, so the tooltip repeats the full milestone name
    const why = `Milestone "${m.title}" in ${m.repo}.\n${m.closed} of ${total} issues closed, ${m.open} to go.\n${during} of them were closed since JabCon started (${m.baseline} were already done then).\nBlue bar: closed before JabCon, green tail: closed during it.`;
    return `<div class="milestone" title="${esc(why)}"><div class="label">${link(m.url, `${esc(m.title)} <span class="muted">${esc(m.repo.split('/')[1])}</span>`)}
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
    return `<div class="leader" data-login="${esc(l.login)}" style="--c:${color[l.login]}" title="${why}">${avatar(l.login, '').replace(`title="${l.login}"`, `title="${why}"`)}<div class="pts">${fmt(l.points)}</div><div>${esc(l.login)}</div>${bonusRow(l)}</div>`;
  }).join('');
  slotMachine();
}

// [impl->req~bonus-points~8] the +100 awards a contributor holds, one emoji each, the category in the tooltip.
// The emoji links to what earned it - the record's PR or a GitHub search; an award with no such page opens the
// contributor's detail view instead.
function bonusLink(b, login, inner) {
  const why = esc(`+${b.points} ${b.title}: ${b.text}`);
  return b.url ? `<a class="bonus" href="${esc(b.url)}" target="_blank" rel="noopener" title="${why}">${inner}</a>`
    : `<a class="bonus" href="#user/${encodeURIComponent(login)}" title="${why}">${inner}</a>`;
}
function bonusRow(l) {
  return (l.bonuses || []).length
    ? `<div class="bonuses">${l.bonuses.map((b) => bonusLink(b, l.login, b.emoji)).join('')}</div>`
    : '';
}

// The nerd corner holds more than fits: the detected refactorings and the funny records (longest identifier,
// most code deleted, ...) take turns, NERD_PAGE lines at a time, so the whole set is readable from the wall.
// [impl->req~nerd-corner~2]
// [impl->req~nerd-records~2]
const NERD_PAGE = 5, NERD_MS = 12000;
let nerdPage = 0, nerdTimer;

function renderNerd() {
  const items = [...data.refactorings.map((r) => ({...r, title: ''})), ...(data.records || [])];
  const pages = Math.ceil(items.length / NERD_PAGE) || 1;
  nerdPage %= pages;
  $('#refactorings').innerHTML = items.slice(nerdPage * NERD_PAGE, (nerdPage + 1) * NERD_PAGE).map((r) =>
    `<li>${avatar(r.author)}${r.title ? `<span class="title">${r.emoji || ''} ${esc(r.title)}:</span>` : ''}<span class="what">${esc(r.text)}</span>${link(r.url, `${esc(r.repo)}#${r.number}`, 'repo')}</li>`).join('');
  clearInterval(nerdTimer);
  nerdTimer = setInterval(() => { nerdPage++; renderNerd(); }, NERD_MS);
}

// Slot machine: new numbers do not just appear, they spin into place, lowest contributor first and the leader last,
// the whole board settled within SLOT_TOTAL_MS. A reel that has not had its turn shows the previous total, grayed.
// Within a reel the digits lock right to left. Only once every reel stands still do the gains pop, in the same order,
// so the three acts (rolling, points, badges) never overlap.
// One interval drives every reel; the next render's call cancels it, which also drops the then-stale nodes.
// [impl->req~leaderboard-slot-machine~4]
const SLOT_TOTAL_MS = 30000, SLOT_ROLL_MS = 2500, POP_STAGGER_MS = 500, POP_MS = 5000;
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
      if (locked >= r.final.length) r.settled = true; else running = true;
    }
    if (running) return;
    clearInterval(slotTimer);
    plan.forEach((r, i) => popTimers.push(setTimeout(() => popPoints(r.el, r.gain), i * POP_STAGGER_MS)));
    popTimers.push(setTimeout(settleSlots, (plan.length - 1) * POP_STAGGER_MS + POP_MS));
  }, 60);
}

// The gain jumps out of the reel, hangs there long enough to be read, then flies off the top of the screen and
// settles as a badge over the avatar. Fixed and on <body>, so no ancestor of the fixed video is transformed.
// [impl->req~leaderboard-slot-machine~4]
function popPoints(el, gain) {
  if (gain <= 0) return;
  const box = el.getBoundingClientRect(), pop = document.createElement('div');
  pop.className = 'pop';
  pop.textContent = `+${fmt(gain)}`;
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
  if (e.type === 'PullRequestEvent' && (e.action === 'opened' || (e.action === 'closed' && !e.merged))) return [1, `PR ${e.action}`];
  if (e.type === 'PullRequestEvent' && e.merged && card?.column === 'done' && card.author === e.actor) return [3, 'merged PR'];
  if (e.type === 'PullRequestEvent') return [0, e.merged || e.action === 'merged' ? 'a merge scores for the PR author only' : `PR ${e.action}: only opening and closing score`];
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
function renderTicker() {
  const recent = data.events.filter((e) => e.type !== 'PullRequestReviewCommentEvent').slice(0, 25);
  const jabcon = recent.filter((e) => cardOf(e)?.focus), rest = recent.filter((e) => !cardOf(e)?.focus);
  $('#ticker').innerHTML = jabcon.map(eventRow).join('') + (jabcon.length ? '<li class="divider">other</li>' : '') + rest.map(eventRow).join('');
}

// Click on a leaderboard avatar: full-screen list of everything that contributor scored (or did not) during JabCon.
// [impl->req~contributor-detail~2]
function showDetail(login) {
  const l = data.leaderboard.find((x) => x.login === login) || { points: 0, merged: 0, reviews: 0, other: 0 };
  const events = (data.all_events || []).filter((e) => e.actor === login && e.type !== 'PullRequestReviewCommentEvent')
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  $('#detail h2').innerHTML = `${avatar(login)} ${esc(login)} <span class="muted">${fmt(l.points)} points · ${l.merged} merged × 3 (${l.ai || 0} AI-assisted × 0.25) · ${l.reviews} reviews × 1..3 · ${l.other} other × 1 · ${l.milestone || 0} on JabCon items × 10 · ${l.boosted || 0} in ${boostText()}</span>`;
  $('#detail h2').innerHTML += (l.bonuses || []).map((b) => ' ' + bonusLink(b, login, `${b.emoji} ${esc(b.title)} +${b.points}`)).join('');
  $('#detail ul').innerHTML = events.map(eventRow).join('') || '<li class="muted">no public activity yet</li>';
  $('#detail').hidden = false;
}
// The detail view is a route (#user/<login>), so the browser's Back button and a shared link both work.
// [impl->req~contributor-detail~2]
let pushedDetail = false; // only then is a history.back() ours to take; a deep link must not leave the site
function route() {
  const login = decodeURIComponent((location.hash.match(/^#user\/(.+)$/) || [])[1] || '');
  if (login && data) showDetail(login);
  else { $('#detail').hidden = true; pushedDetail = pushedDetail && !!login; }
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

// [impl->req~leader-change-bell~3]
// [impl->req~done-confetti~2]
function celebrate(prev) {
  if (!prev) return;
  const leader = data.leaderboard[0]?.login, wasLeader = prev.leaderboard[0]?.login;
  if (leader && wasLeader && leader !== wasLeader) {
    bell(); // the bell opens the act: it makes the room look up while the reels are still rolling
    whenSlotsSettled(() => toast(`🔔 ${leader} takes the lead!`)); // the name comes once the numbers stand
  }
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
