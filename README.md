# JabCon board

A self-refreshing wall display for [JabCon](https://contribute.jabref.org/), the JabRef developer meetup:
what participants are working on, what got merged, who did what, plus a [gource](https://gource.io/) video
of the JabRef repository during the meetup.

Requirements: [docs/requirements.md](docs/requirements.md), traced with OpenFastTrace (`scripts/trace.sh`).

Live: <https://jabref.github.io/jabcon-board/> (only carries data while JabCon runs). The layout scales with the
screen width (Full HD and UHD look the same); Ctrl+mouse wheel scales the page (remembered in the browser, Ctrl+0 resets); `?scale=0.8` / `?scale=1.2` sets it via the URL; `?still=1` to switch off the slow background animation that keeps TVs from dimming a "static" image.

## How it works

- `scripts/collect.py` queries the GitHub search and events APIs for the participants' **public** activity
  in any repository and writes `data.json`. Cards from the configured org are shown normally, other repos dimmed.
  The ring next to the logo fills up over the typical gap between data runs (10 min; GitHub runs the 5-minute schedule only best-effort), turns gray when a run is late and amber when data is older than 30 min. "In progress" only lists open PRs touched since the start; "Backlog" lists the org's `ready-for-review` PRs
  and everything assigned to a participant.
- Posts by participants to the `mailing_lists` are read from the OpenJDK HyperKitty archive and join the ticker.
  Senders are matched by the public name and e-mail of their GitHub profile; mail from an `@openjdk.org` address is
  the Skara bot mirroring GitHub pull request activity and is skipped, so JavaFX reviews are not counted twice.
- `site/` is plain HTML/CSS/JS. It fetches `data.json` every minute, the video every 15 minutes, and reloads itself when a new version of the site was deployed.
- `.github/workflows/board.yml` runs every 5 minutes (and on push to `main`), copies `site/` and a fresh
  `data.json` to the `gh-pages` branch. Outside the JabCon window it publishes the site but skips data collection.
  `gh-pages` is always a single commit (`scripts/gh-pages.sh` force-pushes a fresh one), so it never piles up old data or videos.
- `.github/workflows/screenshot.yml` stores a screenshot under `screenshots/` every three hours during JabCon.
- The video is rendered by `gource-jabcon.yml` in [JabRef/jabref](https://github.com/JabRef/jabref) to
  `https://files.jabref.org/gource/jabcon-2026.mp4`; the URL is set at the top of `site/app.js`.
- `scripts/highlights.py data.json jabcon-2026.mp4 highlights.mp4 [count]` cuts a highlights reel from that video: a
  Star-Wars crawl per biggest merged PR over the gource footage leading up to it, then a BOOM at the merge moment.
  Only seconds in which gource moves are used, so the reel never shows a still. Needs `ffmpeg` and `gh`
  (the merge commits on `main` locate the moments; PRs the video does not contain yet are left out).
  With a fifth argument it also writes the full run with a sports commentator's subtitles, one line per merge, phrased
  from the board's data (no language model), at half speed for reading. `.github/workflows/highlights.yml` renders both hourly to
  <https://jabref.github.io/jabcon-board/highlights.mp4> and `commentary.mp4`; the wall plays the three videos in turn.

## Configuration

`config.json`: `jabcon_start` / `jabcon_end` (ISO timestamps with offset), `phases` (label + end time, drawn on the header progress bar), `timezone` (for the clock),
`participants` (GitHub logins; their order sets the colours), `org` (highlighting and the ready-for-review backlog), `focus_label` (a label in the org, e.g. `project: jabcon`: its open items are always in the Backlog, labeled cards form the first group of every column, and a progress bar for it sits above the milestones),
`exclude_repos` (`owner/name` entries to hide, e.g. when unrelated activity dominates the board),
`mailing_lists` (archive address -> the repo whose factor and link its posts use, e.g. `openjfx-dev@openjdk.org` -> `openjdk/jfx`),
`milestones` (`owner/repo/number`; progress bars in the stats panel, green = closed since the board first saw the milestone),
`repo_factors` (multipliers keyed by repo or whole org; a repo entry beats its org entry, which is how `JabRef/jabcon-board` stays at 1 while the rest of the org counts fivefold),
`dependency_repos` (JabRef's own dependency stack, for the 🔧 bonus; forks of them count too),
`record_bonus_exclude` (logins that keep their nerd corner records but pass the +100 to the runner-up),
`honorary_awards` (`login`, `title`, `text`, `emoji`, optional `url`: +100 for what the API cannot see).
`private_repos` lists private repos whose issue activity is counted for the leaderboard and shown as counts only (no titles) under the milestones. Milestones and `private_repos` need a repository secret `BOARD_TOKEN` (fine-grained PAT with read access to issues of that repo); otherwise they are skipped with a warning.
Bot activity is excluded.

"Nerd corner" lists the five most interesting merged changes, detected by regexes on the diffs (sealed types, records, pattern matching, moved or deleted classes, net-negative PRs, ...), plus one record holder per funny category (longest identifier, longest and shortest method, most code written or deleted, most tangled diff, wordiest changelog entry). Each record carries an icon and pays its author +100 bonus points.

## Leaderboard points

Recomputed at every data run from activity since `jabcon_start`, in any public repository (bots excluded):

| Activity | Points | Credited to |
|---|---|---|
| Pull request merged | 3 | the PR author (not the person who pressed merge) |
| Review submitted (approve, request changes, comment) | 1, 2 or 3 by the complexity of the reviewed diff (branch points in added code: trivial, normal, 20+) | the reviewer |
| Issue comment or review comment | 1 | the commenter |
| Issue opened or closed, PR closed without merge | 1 | the actor |
| Push | 1 per push event (not per commit) | the pusher |
| Issue opened / closed / commented in a `private_repos` repo | 1 | the actor |
| Mail to a configured mailing list | 1 | the sender |

Each of these is multiplied: ten-fold on a JabCon item (focus label or a configured milestone), otherwise by
`repo_factors` (repo before org). A merged PR whose commits credit an AI assistant scores a **quarter** — writing it
by hand is the harder craft. A comment or review whose body carries 🤖 or names Claude was written by the assistant
and scores **nothing at all**, and counts for no bonus either.

Labeling, assigning, starring, forking and merging someone else's PR score nothing. Hover a leaderboard entry to see
the breakdown; the activity ticker shows the points of each entry. A bell rings when position 1 changes (browsers may
need one click on the page after load before they allow sound). Weights live in `leaderboard()` in `scripts/collect.py`
and, for the ticker badge, in `eventPoints()` in `site/app.js`.

## Bonus points

A second evaluation, like the bonus round in a game: **+100 for every superlative a contributor holds**, shared by
everyone tied for it. The icons sit under the login on the leaderboard and in the contributor detail view; each links
to what earned it (the record's PR, or the GitHub search behind the number). Self-reviews, fork syncs and
AI-written comments count for none of them.

| Icon | Award | Who gets it |
|---|---|---|
| 💬 | Chatterbox | most comments |
| 🐝 | Busy bee | most PRs and issues touched |
| 🌍 | Globetrotter | most repositories worked on |
| 💡 | Idea machine | most PRs opened |
| 🛡️ | Gatekeeper | most reviews |
| 🏁 | Closer | most merged PRs |
| 🦉 | Night owl | most activity between 22:00 and 06:00 |
| 🐦 | Early bird | most activity before 08:00 |
| ☕ | Ambassador | most activity outside the org (own forks do not count) |
| 🔧 | Dependency whisperer | most activity in `dependency_repos` and their forks |
| 🎨 | Jack of all trades | widest set of components written or reviewed (by changed files) |
| 🏷️ | Component collector | most distinct `component:` labels written or reviewed |
| 🛸 | Exotic explorer | most foreign repositories that are not dependencies |
| 🔍 | Reviewer's reviewer | largest share of own activity spent reviewing (from 10 reviews on) |
| 🤐 | Actions over words | most reviews per comment written (from 10 reviews on) |
| ✅ | Rubber stamp | most approvals given |
| 🧹 | Janitor | most branches deleted |
| 🤝 | Widest reach | reviewed the PRs of the most different authors |
| ❓ | Socratic | most questions asked |
| 🙏 | Most gracious | most thanks said |
| 🕰️ | Always on | active in the most hours of the day |
| 🧲 | Magnet | own PRs pulled in the most reviews |
| ⚡ | First responder | first to review the most PRs |
| 🐣 | Newcomer | most recent first issue or PR in the org |
| 📏🐍🤏✍️🔥🍝📜 | Nerd corner records | longest identifier, longest and shortest method, most code written, most deleted, most tangled diff, wordiest changelog entry |
| 🍸 … | `honorary_awards` | whatever the jury decides |

Categories, thresholds and the 100 itself live in `BONUS_KINDS` and `BONUS` in `scripts/collect.py`.

## Manual runs

All workflows have `workflow_dispatch` (Actions tab → workflow → "Run workflow"). "Board" takes a `force`
flag to collect data outside the JabCon window.

Locally:

```bash
GITHUB_TOKEN=$(gh auth token) python3 scripts/collect.py --force --out site/data.json
python3 -m http.server -d site 8000   # open http://localhost:8000/
```

## After JabCon

Delete the `gh-pages` branch, switch or remove the gource workflow in JabRef/jabref. `screenshots/` stays on `main`.
