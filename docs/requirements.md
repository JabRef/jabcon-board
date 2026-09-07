# JabCon board requirements

Traced with [OpenFastTrace](https://github.com/itsallcode/openfasttrace): every requirement below is covered by an
`[impl->req~name~1]` tag next to the code that implements it. `scripts/trace.sh` checks the coverage (also in CI).
The trace cannot see whether the behaviour still works; the tags exist so that whoever edits the code sees which
promise it keeps and re-checks it (see `CLAUDE.md`).

## Columns

### Each item lives in exactly one column
`req~one-column-per-item~1`

An issue or PR appears in Backlog, In progress or Done, never twice. Done wins over In progress, In progress over Backlog.

Needs: impl

### In progress shows only PRs touched during JabCon
`req~in-progress-recent~1`

Open PRs of participants count as "in progress" only when updated since the JabCon start; older open PRs stay out.

Needs: impl

### JabCon items first, then newest first
`req~column-order~2`

JabCon items (focus label `focus_label` or one of the configured `milestones`) come first, separated by an "other"
divider; within each group the most recently merged / closed / updated item is on top.

Needs: impl

### Backlog shows JabCon items only
`req~backlog-jabcon-only~1`

The backlog lists open items carrying the focus label or belonging to a configured milestone in a public repo,
nothing else (an issue merely assigned to a participant elsewhere on GitHub is not a JabCon task).

Needs: impl

### Columns scroll and show how much is hidden
`req~column-overflow~1`

A column that does not fit shows "▲ n more" / "▼ n more" lines; the mouse wheel scrolls it and a click on the line
pages it. The lines are correct after every re-render and the scroll position survives a re-render.

Needs: impl

### Section headings explain themselves
`req~heading-tooltips~1`

Hovering a section heading (Backlog, In progress, Done, Stats, Latest activity) shows a tooltip saying what the
section contains and why it is on the board.

Needs: impl

### State tags use GitHub's colours
`req~github-colours~1`

Merged PRs and completed issues are purple, closed-unmerged PRs red, not-planned / duplicate issues gray, drafts and
ready-for-review get their own tags.

Needs: impl

## Header

### Timeline with phases
`req~timeline~1`

A bar shows the elapsed part of JabCon, the configured phases with the time left in each, and a countdown
(hours in, days / hours left; "starts in" before, "over" after).

Needs: impl

### Refresh ring
`req~refresh-ring~2`

A ring fills over the expected refresh interval since the data was generated, pulses when a run is late and the
header turns stale (amber "!") when data is older than 30 minutes or the fetch fails. Hovering it explains what the
ring means and how old the data is.

Needs: impl

### Times in the JabCon timezone
`req~clock-timezone~1`

Clock, timeline and footer times use the configured `timezone`, whatever the viewer's machine is set to.

Needs: impl

## Data collection

### Collector runs only during JabCon
`req~jabcon-window~1`

Outside `jabcon_start`..`jabcon_end` the collector exits without touching the data, unless run with `--force`.

Needs: impl

### Bots are ignored
`req~bots-excluded~1`

Items authored by bot accounts and repos in `exclude_repos` never show up.

Needs: impl

### Events accumulate across runs
`req~events-accumulate~1`

GitHub's public feed returns only the newest events per user; events seen in earlier runs are kept so nobody loses
activity (or points) as JabCon goes on.

Needs: impl

### Private repositories show counts only
`req~private-counts-only~1`

For repos in `private_repos` the public data contains numbers (opened / closed / comments, per participant) but never
titles, numbers or bodies.

Needs: impl

## Scoring

### Points
`req~scoring~7`

Merged PR (as author) 3 points, review 1 to 3 by the cyclomatic complexity of the reviewed diff (branch points in the
added code lines: 1 for a trivial diff such as docs, config or renames, 3 from 20 branch points on), comment / issue / push / PR opened or closed without merge 1 (closing a PR is triage work like closing an issue; merging someone else's PR still scores nothing). Labeling scores nothing: the public feed reports a labeling workflow under the user who triggered it, so it cannot be told from hand triage. On a JabCon item (focus label or configured
milestone) each counts tenfold; elsewhere the configured `repo_factors` apply, keyed by repo or org (anything in the
JabRef org and upstream JavaFX work count fivefold and sixfold).
The ticker shows the same points per event as the leaderboard sums.

Needs: impl

### The points badge explains itself
`req~points-tooltip~1`

Hovering the `+n` badge of an activity row (ticker or contributor detail) shows how that number came about: what the
event was worth and, when it is not 1, the factor and the repo or JabCon item it comes from.

Needs: impl

### No review points on one's own PR
`req~no-self-review-points~1`

Reviews and review comments on a PR authored by the reviewer score nothing (they are mostly replies to bot threads).

Needs: impl

### No points for syncing a fork
`req~no-fork-sync-points~1`

A push to a repo outside the org that contains no commit by the pusher (fork sync) scores nothing and reads "synced <branch>".

Needs: impl

### Leaderboard breakdown
`req~leaderboard-breakdown~1`

Hovering a leaderboard avatar shows how the points add up.

Needs: impl

### Contributor detail view
`req~contributor-detail~2`

Clicking a leaderboard avatar opens a full-screen list of that contributor's activity with the points per row.
It has a Back button (the wall runs a kiosk browser without chrome) and closes on Escape. It is hidden until clicked.
The view is a `#user/<login>` route: the browser's Back button closes it, and the link can be shared.

Needs: impl

## Activity

### Ticker rows deep-link
`req~ticker-deep-links~1`

Each activity row links to the concrete comment, review or issue (not just the repo), shows an excerpt, the repo
badge and the points, newest first.

Needs: impl

### JabCon activity on top
`req~activity-grouped~1`

The ticker shows events on JabCon items first and everything else below an "other" divider, newest first within
each group.

Needs: impl

### Lead change rings a bell
`req~leader-change-bell~1`

When the top of the leaderboard changes, a bell sounds and a toast names the new leader.

Needs: impl

### Done items get confetti
`req~done-confetti~2`

A newly merged PR or closed issue triggers confetti and a toast naming who did it, the number and the title.

Needs: impl

## Gource video

### Hover enlarges the video in place
`req~gource-hover~1`

Hovering the gource video enlarges it to nearly the whole screen. The enlarged video must cover the small one so the
pointer stays over it (no flicker, no jump); moving the pointer to the free strip on the left shrinks it back.

Needs: impl

### Gource run, highlights reel and commentated run take turns
`req~gource-alternate~2`

The player shows a full run of the gource video, then the highlights reel (`highlights.mp4` next to the site), then
the full run again with a commentator's subtitles (`commentary.mp4`), then starts over. Players side by side would
leave each too small in the column; the enlarged view works for whichever is playing. A missing rendering is
skipped, not shown as a broken player.

Needs: impl

### Buttons skip to the previous and next video
`req~gource-next~2`

While the video is enlarged by hover, a button in each top corner switches to the previous or next video at once,
without waiting for the current run to end. Each button is named after the video it leads to ("full", "highlights",
"commentary"). The video stays enlarged while the pointer is on a button.

Needs: impl

### Gource plays at triple speed, the reel at normal speed
`req~gource-speed~2`

The gource video plays at three times its recorded speed, so a run through the repository history fits the wall's
attention span. The highlights reel and the commentated run play at recorded speed: their text is not readable faster.

Needs: impl

### Video refreshes without cutting a run
`req~gource-refresh~2`

Every swap between the two videos loads the newest rendering, so a fresh one is picked up after the current run
finished. When the gource video fails to load (not rendered yet, or replaced on the server mid-download), a
placeholder with the URL is shown instead of a broken player, and loading is retried after 30 seconds.

Needs: impl

## Display

### Self-updating wall
`req~auto-reload~2`

Data is fetched every minute and only re-rendered when it actually changed, so a tooltip stays readable while the
mouse rests on a card or avatar. A new deployment (changed `version.txt`) reloads the page within 5 minutes. The
deployed commit is shown in the footer.

Needs: impl

### Layout scales with the screen
`req~scaling~1`

Full HD and UHD show the same layout. `?scale=` sets a factor, Ctrl+mouse wheel changes it (remembered in the
browser), Ctrl+0 resets. Browser zoom is not a usable substitute (viewport units).

Needs: impl

### Ambient motion against TV dimming
`req~ambient-motion~1`

Slow, low-contrast animation keeps content-adaptive TVs from dimming; off with `?still=1` or reduced-motion.
It must not animate `transform` / `filter` on ancestors of fixed-positioned elements (that would re-anchor the
enlarged video).

Needs: impl

### Milestones
`req~milestones~2`

Configured milestones are listed with open/closed counts, a progress bar and how many were closed during JabCon
(baseline taken at the first run). The row counts what was closed since JabCon started; hovering it spells out the
full milestone name, the overall counts and what the two bar colours mean. Milestones in private repos need `BOARD_TOKEN`; a missing one
is skipped with a warning, not a failed run.

Needs: impl

### Nerd corner
`req~nerd-corner~1`

The stats show the top refactorings detected in merged PRs (records, sealed types, pattern matching, ...).

Needs: impl

### AI models
`req~ai-models~1`

The nerd corner shows which AI assistants were credited in the merged PRs' commits (co-author trailers and tool
sign-off lines) as a pie chart with a legend beside it, one slice per model, counted in PRs.

Needs: impl

### Leaderboard slot machine
`req~leaderboard-slot-machine~1`

When new data arrives the leaderboard totals spin like a slot machine before settling on the new number, starting
with the lowest contributor and ending with the leader, all of them settled within 30 s. A reel shows the previous
total until its turn. Off with `?still=1` or reduced-motion.

Needs: impl

<!-- markdownlint-disable-file MD022 -->

