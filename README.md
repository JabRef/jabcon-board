# JabCon board

A self-refreshing wall display for [JabCon](https://contribute.jabref.org/), the JabRef developer meetup:
what participants are working on, what got merged, who did what, plus a [gource](https://gource.io/) video
of the JabRef repository during the meetup.

Live: <https://jabref.github.io/jabcon-board/> (only carries data while JabCon runs). The layout scales with the
screen width (Full HD and UHD look the same); append `?scale=0.8` to fit more cards, `?scale=1.2` for bigger text.

## How it works

- `scripts/collect.py` queries the GitHub search and events APIs for the participants' **public** activity
  in any repository and writes `data.json`. Cards from the configured org are shown normally, other repos dimmed.
  The ring next to the logo fills up over the typical gap between data runs (10 min; GitHub runs the 5-minute schedule only best-effort), turns gray when a run is late and amber when data is older than 30 min. "In progress" only lists open PRs touched since the start; "Backlog" lists the org's `ready-for-review` PRs
  and everything assigned to a participant.
- `site/` is plain HTML/CSS/JS. It fetches `data.json` every minute, the video every 15 minutes, and reloads itself when a new version of the site was deployed.
- `.github/workflows/board.yml` runs every 5 minutes (and on push to `main`), copies `site/` and a fresh
  `data.json` to the `gh-pages` branch. Outside the JabCon window it publishes the site but skips data collection.
- `.github/workflows/screenshot.yml` stores a screenshot under `screenshots/` every three hours during JabCon.
- The video is rendered by `gource-jabcon.yml` in [JabRef/jabref](https://github.com/JabRef/jabref) to
  `https://files.jabref.org/gource/jabcon-2026.mp4`; the URL is set at the top of `site/app.js`.

## Configuration

`config.json`: `jabcon_start` / `jabcon_end` (ISO timestamps with offset), `phases` (label + end time, drawn on the header progress bar), `timezone` (for the clock),
`participants` (GitHub logins; their order sets the colours), `org` (highlighting and the ready-for-review backlog), `focus_label` (a label in the org, e.g. `project: jabcon`: its open items are always in the Backlog, labeled cards form the first group of every column, and a progress bar for it sits above the milestones),
`exclude_repos` (`owner/name` entries to hide, e.g. when unrelated activity dominates the board),
`milestones` (`owner/repo/number`; progress bars in the stats panel, green = closed since the board first saw the milestone).
`private_repos` lists private repos whose issue activity is counted for the leaderboard and shown as counts only (no titles) under the milestones. Milestones and `private_repos` need a repository secret `BOARD_TOKEN` (fine-grained PAT with read access to issues of that repo); otherwise they are skipped with a warning.
Bot activity is excluded.

"Nerd corner" lists the five most interesting merged changes, detected by regexes on the diffs (sealed types, records, pattern matching, moved or deleted classes, net-negative PRs, ...).

## Leaderboard points

Recomputed at every data run from activity since `jabcon_start`, in any public repository (bots excluded):

| Activity | Points | Credited to |
|---|---|---|
| Pull request merged | 3 | the PR author (not the person who pressed merge) |
| Review submitted (approve, request changes, comment) | 2 | the reviewer |
| Issue comment or review comment | 1 | the commenter |
| Issue opened or closed | 1 | the actor |
| Push | 1 per push event (not per commit) | the pusher |
| Issue opened / closed / commented in a `private_repos` repo | 1 | the actor |

Labeling, assigning, starring, forking and merging someone else's PR score nothing. Hover a leaderboard entry to see
the breakdown; the activity ticker shows the points of each entry. A bell rings when position 1 changes (browsers may
need one click on the page after load before they allow sound). Weights live in `leaderboard()` in `scripts/collect.py`
and, for the ticker badge, in `eventPoints()` in `site/app.js`.

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
