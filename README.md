# JabCon board

A self-refreshing wall display for [JabCon](https://contribute.jabref.org/), the JabRef developer meetup:
what participants are working on, what got merged, who did what, plus a [gource](https://gource.io/) video
of the JabRef repository during the meetup.

Live: <https://jabref.github.io/jabcon-board/> (only carries data while JabCon runs).

## How it works

- `scripts/collect.py` queries the GitHub search and events APIs for the participants' **public** activity
  in any repository and writes `data.json`. Cards from the configured org are shown normally, other repos dimmed.
  "In progress" only lists open PRs touched since the start; "Backlog" lists the org's `ready-for-review` PRs
  and everything assigned to a participant.
- `site/` is plain HTML/CSS/JS. It fetches `data.json` every minute and the video once per hour.
- `.github/workflows/board.yml` runs every 10 minutes (and on push to `main`), copies `site/` and a fresh
  `data.json` to the `gh-pages` branch. Outside the JabCon window it publishes the site but skips data collection.
- `.github/workflows/screenshot.yml` stores a screenshot under `screenshots/` every three hours during JabCon.
- The video is rendered by `gource-jabcon.yml` in [JabRef/jabref](https://github.com/JabRef/jabref) to
  `https://files.jabref.org/gource/jabcon-2026.mp4`; the URL is set at the top of `site/app.js`.

## Configuration

`config.json`: `jabcon_start` / `jabcon_end` (ISO timestamps with offset), `timezone` (for the clock),
`participants` (GitHub logins; their order sets the colours), `org` (highlighting and the ready-for-review backlog),
`exclude_repos` (`owner/name` entries to hide, e.g. when unrelated activity dominates the board).
Bot activity is excluded.

"Nerd corner" lists the five most interesting merged changes, detected by regexes on the diffs (sealed types, records, pattern matching, moved or deleted classes, net-negative PRs, ...).

Leaderboard points: merged PR 3, review 2, comment / issue / push 1.

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
