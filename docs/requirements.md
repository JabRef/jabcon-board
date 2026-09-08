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

### Activity heat strip under the timeline
`req~activity-heat-strip~1`

A row of cells under the timeline bar, one per JabCon hour, shows how many participant events fell into that hour
(brightness relative to the busiest hour); hovering a cell names the hour and the count. The strip shares the bar's
time axis, so working hours and night gaps are visible without taking panel space.

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

### Publishing waits for the running deployment
`req~publish-pacing~1`

A push to `gh-pages` cancels the GitHub Pages deployment of the previous one. When a deployment takes longer than the
publish interval, no deployment ever completes and the live site freezes while the branch keeps moving, so a push is
skipped while a deployment younger than 20 minutes is still running; the next run publishes. Only the
five-minute data publisher waits that way — the hourly video render publishes whatever it just spent half an hour on.

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
`req~scoring~9`

Merged PR (as author) 3 points, review 1 to 3 by the cyclomatic complexity of the reviewed diff (branch points in the
added code lines: 1 for a trivial diff such as docs, config or renames, 3 from 20 branch points on), comment / issue / push / PR opened or closed without merge 1 (closing a PR is triage work like closing an issue; merging someone else's PR still scores nothing). Labeling scores nothing: the public feed reports a labeling workflow under the user who triggered it, so it cannot be told from hand triage. On a JabCon item (focus label or configured
milestone) each counts tenfold; elsewhere the configured `repo_factors` apply, keyed by repo or org (anything in the
JabRef org and upstream JavaFX work count fivefold and sixfold; a repo entry overrides its org, which keeps the
board's own repository at 1 — building the board is not JabRef work).
A merged PR whose commits credit an AI assistant (the same trailers the nerd corner's AI chart counts) scores a
quarter of that: human-only code is the harder craft.
The ticker shows the same points per event as the leaderboard sums.

Needs: impl

### AI-written comments score nothing
`req~no-ai-comment-points~1`

A comment or review whose body carries the robot emoji or names Claude was written by an assistant, not by the
participant: it scores no points and counts for no bonus. Events cached before this rule kept no body; they are
checked against their stored excerpt instead.

Needs: impl

### Automated work is not counted
`req~automation-excluded~1`

Items whose title matches one of the configured `exclude_titles` and pushes to one of the `exclude_branches` are an
automation working under a human account (Crowdin's translation PRs): they yield no card, no ticker entry, no points
and no bonus, the same way bot accounts are skipped.

Needs: impl

### Bonus points
`req~bonus-points~19`

A second evaluation on top of the per-event points: +100 for each superlative a contributor holds — most comments,
most PRs and issues touched, most repositories worked on, most PRs opened, most reviews, most merged PRs, most
activity between 22:00 and 06:00, most before 08:00, most activity in repositories outside the org, the widest set of components written or reviewed (by the changed files, and
again by the PRs' "component:" labels), most activity in
JabRef's configured `dependency_repos` (openjdk/jfx, ICU4J, jgit, ...), and the most distinct repositories outside
the org that are not dependencies. Everybody tied for a category gets the award. The contributor whose first issue or PR in the org is the most recent gets a
newcomer award, the one who brought the oldest item of somebody else back into the conversation a necromancer award, and the author
of the PR that went from opened to merged in the shortest time a speedrun award. Every nerd corner record pays +100 to the PR's author as well, except for the authors listed in
`record_bonus_exclude` — there the runner-up holds the record bonus. Configured `honorary_awards` add +100 for what
the data cannot see. The leaderboard
shows one emoji per award under the login and names the category in the tooltip and the contributor detail view.
Each emoji links to what earned it: the record's PR, or a GitHub search for the comments, reviews, PRs or repositories
that were counted; an award with nothing to point at opens the contributor's detail view.

Needs: impl

### Mailing list posts count
`req~mailing-lists~1`

Posts by a participant to a list in `mailing_lists` score like a comment (1 point, times the factor of the repo the
list is mapped to) and show up in the ticker with a link into the archive. Mail sent from an `@openjdk.org` address
is the Skara bot mirroring GitHub pull request activity, which the board already counts, and is left out.

Needs: impl

### Activity rows name the PR or issue
`req~event-titles~1`

An activity row that refers to a tracked PR or issue shows its title next to the number, so "reviewed PR #2225"
says what was reviewed.

Needs: impl

### The points badge explains itself
`req~points-tooltip~2`

Every activity row (ticker or contributor detail) carries a `+n` badge, `+0` in muted grey when the event scored
nothing. Hovering it shows how that number came about: what the event was worth and, when it is not 1, the factor
and the repo or JabCon item it comes from — or, for `+0`, why it scored nothing (own PR, fork sync, labeling).

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

### Component detail view
`req~component-detail~1`

Clicking a row in the Components box opens the same full-screen view, listing the PRs that touched that component
ranked by the lines they changed in it, each with the PR's own added and removed lines. It is a `#component/<name>`
route, so Back, Escape and a shared link work like the contributor view.

Needs: impl

## Activity

### Ticker rows deep-link
`req~ticker-deep-links~1`

Each activity row links to the concrete comment, review or issue (not just the repo), shows an excerpt, the repo
badge and the points, newest first.

Needs: impl

### JabCon activity on top
`req~activity-grouped~2`

The ticker takes the newest events and shows those on JabCon items above an "other" divider, everything else
below it, newest first within each group. Both groups come out of the same window, so the divider moves with how
much recent activity is on JabCon items and the newest events stay visible in the clipped panel.

Needs: impl

### Lead change rings a bell
`req~leader-change-bell~3`

When the top of the leaderboard changes, a bell sounds at once, so the room looks up while the reels are still
rolling. The toast naming the new leader follows as the finale, after every reel has settled and every gain has
popped.

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

### Readable on a phone
`req~mobile-layout~1`

Below 900 px the board becomes one scrolling column with text at a readable size, so a phone shows every section
including the footer instead of clipping whatever falls below the browser toolbars.

Needs: impl

### Ambient motion against TV dimming
`req~ambient-motion~1`

Slow, low-contrast animation keeps content-adaptive TVs from dimming; off with `?still=1` or reduced-motion.
It must not animate `transform` / `filter` on ancestors of fixed-positioned elements (that would re-anchor the
enlarged video).

Needs: impl

### Sticker hand-overs and point gains are announced
`req~sticker-moves~1`

When a data run moves a sticker to another contributor (or hands out a new one), the toast announces it after the
reels have settled, and the newsticker repeats it. The newsticker also lists what the latest run changed on the
leaderboard: every contributor's gain (or loss) in points, largest first. Both stay in the strip until the next run
that changes something.

Needs: impl

### Stickers remember when they were earned
`req~sticker-since~1`

Each award carries the time it was first seen, kept across runs, so the newsticker lists the newest stickers first
and says "just earned" for those under three hours old and "holds" for the rest.

Needs: impl

### Newsticker
`req~newsticker~3`

A headline strip scrolls along the bottom edge of the wall, so there is something to read in quiet hours. It is
phrased from the board's own data in the gource commentator's voice: the tally so far, the latest merged PRs (with
their reviewers), recently closed issues, what is still left (backlog, milestones, focus label), who leads, the race
(see the catch-up requirement), and every sticker earned and by whom. Stickers are woven in one at a time between
the other headlines, so a screen width never shows stickers only. Headlines link to the item, sticker or
contributor. The strip stays still with `?still=1` or reduced-motion.

Needs: impl

### The race is commented
`req~catch-up~1`

From the recent events the newsticker tells who scored most in the last six hours (top three), who is catching up
on the place above (scored more than them in that window and the gap is at most five times that gain: points
behind and points scored), and who is back after a pause of more than sixteen hours, so a night's sleep does not
count.

Needs: impl

### Milestones
`req~milestones~2`

Configured milestones are listed with open/closed counts, a progress bar and how many were closed during JabCon
(baseline taken at the first run). The row counts what was closed since JabCon started; hovering it spells out the
full milestone name, the overall counts and what the two bar colours mean. Milestones in private repos need `BOARD_TOKEN`; a missing one
is skipped with a warning, not a failed run.

Needs: impl

### Nerd corner
`req~nerd-corner~3`

The stats show the top refactorings detected in merged PRs (records, sealed types, pattern matching, ...).
Together with the records below they take turns, four lines at a time, so everything is readable from the wall and
nothing is cut off by the leaderboard below.

Needs: impl

### Nerd corner records
`req~nerd-records~2`

The nerd corner also lists one record holder per funny category, mined from the merged PRs' diffs: longest
identifier, longest and shortest method, most code written, most code deleted, most tangled diff (cyclomatic
complexity) and wordiest changelog entry. Each line carries the category's icon and names the PR and its author.

Needs: impl

### AI models
`req~ai-models~1`

The nerd corner shows which AI assistants were credited in the merged PRs' commits (co-author trailers and tool
sign-off lines) as a pie chart with a legend beside it, one slice per model, counted in PRs.

Needs: impl

### Leaderboard slot machine
`req~leaderboard-slot-machine~4`

When new data arrives the leaderboard totals spin like a slot machine before settling on the new number, starting
with the lowest contributor and ending with the leader, all of them settled within 30 s. Its digits lock right to
left. A reel shows the previous total, grayed, until its turn. Only when every reel has stopped do the gained points
pop out of the numbers, in the same order, and fly off the top of the screen slowly enough to be read; each then
fades in as a badge over its contributor's avatar and stays there until the next data run. Off with `?still=1` or reduced-motion.

Needs: impl

<!-- markdownlint-disable-file MD022 -->

