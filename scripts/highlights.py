#!/usr/bin/env python3
"""Highlights reel from the gource video: a Star-Wars crawl introducing each of the biggest merged PRs over the gource
footage leading up to its merge, then a BOOM at the merge moment. Only seconds in which gource moves are used, so the
reel never shows a still. Only needs ffmpeg (drawtext, perspective) and the board's data.json.

    scripts/highlights.py data.json jabcon-2026.mp4 highlights.mp4 [count] [commentary.mp4]

With a fifth argument, a second video is written: the full gource run with a sports commentator's subtitles, one line
per merge, phrased from the board's data (no language model involved; see commentary()).
"""
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta

DATA, VIDEO, OUT = sys.argv[1:4]
COUNT = int(sys.argv[4]) if len(sys.argv) > 4 else 6
COMMENTARY = sys.argv[5] if len(sys.argv) > 5 else None
REPO = "JabRef/jabref"
# gource's timeline, fitted against the clock gource draws into the frames (JabRef/jabref's gource-jabcon.yml asks for
# 100 s/day and --auto-skip-seconds 30; the rendered video runs 1.5x faster, and starts a quarter hour early).
# ponytail: refit these three when the clock in the video drifts from the "merged by" labels.
SECONDS_PER_DAY = float(os.environ.get("SECONDS_PER_DAY", 67))
SKIP_CAP = float(os.environ.get("SKIP_CAP", 23))  # video seconds of idling before gource skips to the next commit
START_OFFSET = timedelta(minutes=-15)
END_HOLD = 10  # gource holds the final frame this long after the last commit; the graph settles over the first 3 s
SIZE, LEAD = 54, 72  # crawl fontsize, and the line advance it produces (fontsize + line_spacing)
SPEED, LINE = 165, 56  # crawl px/s, px per text line (measured: 54 px font plus spacing, after the perspective)
TAIL = 6  # moving gource seconds after the boom; the crawl runs over the moving seconds before it
W, H = 1920, 1080
FONT = "DejaVu Sans"
ENC = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", "-y"]

data = json.load(open(DATA))
start = datetime.fromisoformat(data["config"]["jabcon_start"])
when = lambda c: datetime.fromisoformat(c["merged_at"].replace("Z", "+00:00"))
merged = sorted((c for c in data["cards"] if c["repo"] == REPO and c.get("merged_at")), key=when)
duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", VIDEO]))

# the commits gource animates: main since JabCon started, by author date (gource's clock), via gh (GH_TOKEN in CI)
log = subprocess.check_output(["gh", "api", "--paginate", f"repos/{REPO}/commits?sha=main&since={start.isoformat()}&per_page=100",
                               "--jq", ".[] | [.commit.author.date, .commit.author.name, .commit.message] | @json"], text=True).splitlines()
# logins the board knows; a co-author trailer naming just a login ("subhramit <mail>") is resolved only for these,
# lest "Christoph <mail>" becomes some unrelated GitHub user called Christoph
known = {l.lower() for l in data["config"]["participants"]} | {l.lower() for l in data["pr_authors"].values()} | {e["actor"].lower() for e in data["all_events"]}
commits, author_of, coauthors, by_number = [], {}, {}, {}  # author date -> the name gource shows / the Co-authored-by
# trailers; PR number -> author date (squash and queue merges carry "(#1234)" in the title)
names = {}


def display(login):
    """The name gource would show for a GitHub login: the profile name, or the login when there is none."""
    if login not in names:
        user = subprocess.run(["gh", "api", f"users/{login}", "--jq", ".name // .login"], text=True, capture_output=True)
        names[login] = user.stdout.strip() if user.returncode == 0 and user.stdout.strip() else login
    return names[login]


for d, author, message in map(json.loads, log):
    t = datetime.fromisoformat(d.replace("Z", "+00:00"))
    commits.append(t)
    author_of[t] = author
    for n in re.findall(r"\(#(\d+)\)", message.split("\n")[0]):
        by_number[int(n)] = t
    for m in re.finditer(r"^co-authored-by:\s*([^<\n]+?)\s*<([^>]*)>", message, re.I | re.M):
        login = re.fullmatch(r"(?:\d+\+)?([^@]+)@users\.noreply\.github\.com", m[2])
        coauthors.setdefault(t, []).append(display(login[1] if login else m[1]) if login or m[1].lower() in known else m[1])
commits.sort()
position, video_t, prev = {}, 0.0, start + START_OFFSET  # commit time -> video second
for t in commits:
    if t < prev:
        continue
    video_t += min(SKIP_CAP, (t - prev).total_seconds() * SECONDS_PER_DAY / 86400)
    position[t], prev = video_t, t
# the video may lag behind the log by a render: only commits that fit before the final hold are in it
moving_end = max((v for v in position.values() if v + END_HOLD <= duration + 1), default=0) + 3


def nearest(c):
    """The PR's commit: by number from its title, else the closest by time."""
    if c["number"] in by_number:
        return by_number[c["number"]]
    return min(position, key=lambda t: abs((t - when(c)).total_seconds()), default=None)


def people(c):
    """The merge commit's author (the name gource shows) plus its co-authors, without duplicates; AI models collapse
    into one "Claude", named last."""
    out, seen = [], set()
    for n in [author_of.get(nearest(c), c["author"])] + coauthors.get(nearest(c), []):
        n = "Claude" if n.startswith("Claude") else n
        if n.lower() not in seen and not n.endswith("[bot]"):
            seen.add(n.lower())
            out.append(n)
    return sorted(out, key=lambda n: n == "Claude")


def involved(c, types, exclude):
    """Display names of those with an event of these types on the PR (from the board's data), minus those already
    credited under that name or login."""
    actors = {e["actor"] for e in data["all_events"] if e["repo"] == REPO and e["number"] == c["number"] and e["type"] in types}
    credited = {x.lower() for x in exclude}
    return sorted({display(a) for a in actors if a.lower() not in credited and display(a).lower() not in credited}, key=str.lower)


def merger(c):
    """Who pressed merge (a maintainer, or the merge queue on their behalf), from the PR itself."""
    return display(subprocess.check_output(["gh", "api", f"repos/{REPO}/pulls/{c['number']}", "--jq", ".merged_by.login"], text=True).strip())


def moment(c):
    """Video second of a merged PR's commit: the closest one within 25 minutes (the merge queue rebases the commit well
    before the merge is recorded), None when the video does not contain it yet."""
    t = nearest(c)
    if t is None or abs((t - when(c)).total_seconds()) > 1500 or position[t] > moving_end:
        return None
    return position[t]


shown = [c for c in merged if moment(c) is not None]
top = sorted(sorted(shown, key=lambda c: -(c["stats"].get("complexity") or 0))[:COUNT], key=when)

tmp = tempfile.mkdtemp()
segments = []


def run(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args], check=True)


# motion per second of the gource video: mean difference between the frames one second apart. Idling between
# commits scores ~0.3 (only the bloom flickers), animation 1.5 and more.
stats = os.path.join(tmp, "motion.txt")
run("-i", VIDEO, "-vf", f"fps=1,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={stats}",
    "-an", "-f", "null", "-")
motion = [float(l.split("=")[1]) for l in open(stats) if "YAVG" in l]
MOVING = float(os.environ.get("MOVING", 1.0))
moving = [k for k, m in enumerate(motion) if m > MOVING and k < moving_end]


def ranges(seconds):
    """ffmpeg select expression keeping exactly these whole seconds of the source."""
    runs, start_, prev = [], None, None
    for k in seconds:
        if start_ is None or k != prev + 1:
            if start_ is not None:
                runs.append((start_, prev + 1))
            start_ = k
        prev = k
    runs.append((start_, prev + 1))
    return "+".join(f"between(t,{a},{b - 0.001})" for a, b in runs)


def highlight(name, text, before, after=None, title="", label=""):
    """Crawl text over dimmed gource footage of the moving seconds `before`; with `after`, a BOOM at the junction (white
    flash, zoom punch, shake, RGB split, bass hit) and the plain footage of those seconds with a label."""
    path = os.path.join(tmp, f"{name}.txt")
    open(path, "w").write(text)
    n = len(before)
    # pace the crawl so the whole block clears the top within the card, however many lines it has
    speed = (H + LEAD * len(text.splitlines())) / n
    text_v = (f"[1:v]drawtext=textfile='{path}':font='{FONT}':fontsize={SIZE}:fontcolor=#ffd23f:line_spacing={LEAD - SIZE}:x=(w-text_w)/2"
              f":y=h-t*{speed},"
              # narrow the top: letters lean towards the vanishing point, as in the real crawl
              f"perspective=x0={W * 0.3}:y0=0:x1={W * 0.7}:y1=0:x2=0:y2={H}:x3={W}:y3={H}:sense=destination,format=gbrp[text];")
    if title:
        text_v = text_v.replace("[1:v]", f"[1:v]drawtext=text='{title}':font='{FONT}':fontsize=40:fontcolor=#4bd5ee:x=(w-text_w)/2:y=h*0.42:enable='lt(t,2.2)',")
    fc = (f"[0:v]select='{ranges(before)}',setpts=N/30/TB,trim=duration={n},eq=brightness=-0.25:saturation=0.5,format=gbrp[dim];"
          + text_v + "[dim][text]blend=all_mode=screen,format=yuv420p[card];")  # blend in RGB: screen on chroma planes tints
    if after is None:
        fc += f"[card]fade=t=out:st={n - 0.5}:d=0.5[v]"
        af = f"anullsrc=r=44100:cl=stereo:d={n}"
    else:
        b, clip = n, n + len(after)
        fc += (f"[0:v]select='{ranges(after)}',setpts=N/30/TB,trim=duration={len(after)}[post];[card][post]concat=n=2:v=1:a=0,"
               f"scale={W * 1.2}:{H * 1.2},"
               f"crop={W}:{H}:x='{W * 0.1}+if(between(t,{b},{b + 0.6}),(random(0)-0.5)*160*({b + 0.6}-t),0)'"
               f":y='{H * 0.1}+if(between(t,{b},{b + 0.6}),(random(0)-0.5)*160*({b + 0.6}-t),0)',"
               f"zoompan=z='if(between(in,{b * 30},{b * 30 + 15}),1.6-(in-{b * 30})*0.04,1)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,"
               f"rgbashift=rh=25:bh=-25:enable='between(t,{b},{b + 0.35})',"
               f"eq=brightness='if(between(t,{b},{b + 0.4}),({b + 0.4}-t)/0.4,0)':saturation='if(between(t,{b},{b + 0.4}),0,1)':eval=frame,"
               f"drawtext=text='{label}':font='{FONT}':fontsize=64:fontcolor=white:borderw=3:bordercolor=black"
               f":x=(w-text_w)/2:y=h-140:alpha='if(lt(t,{b + 0.5}),0,min(1,(t-{b + 0.5})*2))'[v]")
        af = (f"aevalsrc='if(gte(t,{b}),exp(-5*(t-{b}))*(0.9*sin(2*PI*48*(t-{b}))+0.5*sin(2*PI*31*(t-{b}))"
              f"+0.6*exp(-40*(t-{b}))*(random(0)*2-1)),0)':c=stereo:s=44100:d={clip}")
    out = os.path.join(tmp, f"{name}.mp4")
    run("-i", VIDEO, "-f", "lavfi", "-i", f"color=black:s={W}x{H}:d={n}", "-f", "lavfi", "-i", af,
        "-filter_complex", fc, "-map", "[v]", "-map", "2:a", *ENC, out)
    segments.append(out)


def crawl_seconds(text):
    """Long enough for the last line to rise to about 60 % of the frame height."""
    return math.ceil((H * 0.4 + (len(text.rstrip("\n").split("\n")) - 1) * LINE) / SPEED)


def around(second, n):
    """The last n moving seconds before this one and the first TAIL moving seconds from it on."""
    return [k for k in moving if k < second][-n:], [k for k in moving if k >= second][:TAIL]


year = start.year
intro = f"JabCon {year}\n\n{len(merged)} pull requests merged\ninto {REPO}\n\nThese are the {len(top)} biggest.\n\n\n\n\n"
highlight("intro", intro, moving[:crawl_seconds(intro)], title="A long time ago in a repository far, far away....")
for i, c in enumerate(top):
    authors = people(c)
    reviewers = involved(c, {"PullRequestReviewEvent"}, authors)
    commenters = involved(c, {"IssueCommentEvent", "PullRequestReviewCommentEvent"}, authors + reviewers)
    credits = [f"by {', '.join(authors)}"]
    if reviewers:
        credits.append(f"reviews by {', '.join(reviewers)}")
    if commenters:
        credits.append(f"comments by {', '.join(commenters)}")
    st = c["stats"]
    comps = sorted(st.get("components", {}), key=lambda k: -st["components"][k])[:3]
    facts = [f"+{st['additions']} / -{st['deletions']} lines in {st['changed_files']} files", f"complexity {st['complexity']}"]
    if comps:
        facts.append("touching " + ", ".join(comps))
    body = "\n".join(textwrap.fill(line, 34) for line in
                     [f"Episode {i + 1}", "", c["title"], "", *credits, "", *facts])
    before, after = around(int(moment(c)), crawl_seconds(body))
    highlight(f"pr{i}", body, before, after, label=f"#{c['number']} merged by {merger(c)}")
highlight("outro", "To be continued...\n\n\n\n\n", moving[-crawl_seconds("To be continued..."):])


def commentary(out):
    """The whole gource run with a commentator's subtitles: an opener, a line at every merge, a word when a night is
    skipped, and a closing tally. Lines are picked from phrase banks by PR size, seeded by PR number so a re-render
    says the same things."""
    SLOW = float(os.environ.get("SLOW", 2))  # the run plays this much slower than rendered, for reading time
    MIN, MAX, LATE = 4.0, 8.0, 5.0  # a line shows 4 to 8 s; when it cannot start within 5 s of its moment it is dropped
    cues = []  # (moment, hold, text)
    size = lambda c: c["stats"]["additions"] + c["stats"]["deletions"]
    big = ["WHAT A MONSTER! {who} lands {title}: {add} lines added, {dele} gone!",
           "Ohh, the crowd is on its feet! {who} with {title}, {add} new lines!",
           "That's a heavyweight from {who}: {title}. {add} lines added, {dele} removed!"]
    mid = ["{who} slots it in: {title}. {add} lines, clean finish.",
           "Nicely worked by {who}: {title}.",
           "And {who} delivers: {title}. {add} lines added."]
    small = ["A quick one from {who}: {title}.", "{who} keeps it tidy: {title}.", "Tap-in for {who}: {title}."]
    reviewed = [" {rev} waves it through.", " Reviewed by {rev}, no complaints.", " {rev} had a look first, all clear."]
    cues.append((0, 6, f"Good evening and welcome to JabCon {start.year}! {len(merged)} pull requests merged into {REPO} so far. Let's go!"))
    for c in merged:
        at = moment(c)
        if at is None:
            continue
        rng = random.Random(c["number"])
        bank = big if size(c) > 800 else mid if size(c) > 150 else small
        text = rng.choice(bank).format(who=people(c)[0], title=c["title"], add=c["stats"]["additions"], dele=c["stats"]["deletions"])
        revs = involved(c, {"PullRequestReviewEvent"}, people(c))
        if revs:
            text += rng.choice(reviewed).format(rev=" and ".join(revs[:2]))
        cues.append((at, MAX, text))
    for t, nxt in zip(commits, commits[1:]):
        if (nxt - t).total_seconds() * SECONDS_PER_DAY / 86400 > SKIP_CAP and position.get(nxt, 1e9) < moving_end:
            cues.append((position[nxt] - 1.5, 4, f"The night falls over the repository... and we're back on {nxt.strftime('%A')} morning!"))
    lead = data["leaderboard"][0]
    cues.append((moving_end, (duration - moving_end) * SLOW, f"And that's the state of play: {len(merged)} merged, {data['stats']['additions']} lines added. "
                 f"{display(lead['login'])} leads the table with {lead['points']} points. Back to the studio!"))
    lines, free = [], 0.0  # (start, end, text) in slowed seconds: one line at a time, each waiting for the previous
    for at, hold, text in sorted((at * SLOW, hold, text) for at, hold, text in cues):
        begin = max(at, free)
        if begin - at > LATE:
            continue
        if lines and lines[-1][1] > begin:
            lines[-1] = (lines[-1][0], begin, lines[-1][2])
        lines.append((begin, min(begin + hold, duration * SLOW), text))
        free = begin + MIN
    ass = os.path.join(tmp, "commentary.ass")
    fmt = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    esc = lambda x: x.replace("\\", "").replace("{", "(").replace("}", ")")
    open(ass, "w").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},52,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,3,10,0,2,200,200,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "".join(f"Dialogue: 0,{fmt(a)},{fmt(b)},Default,,0,0,0,,{{\\fad(150,300)}}{esc(t)}\n" for a, b, t in lines))
    run("-i", VIDEO, "-vf", f"setpts={SLOW}*PTS,subtitles='{ass}'", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", out)
    print(out, f"{len(lines)} lines of commentary")


lst = os.path.join(tmp, "list.txt")
open(lst, "w").write("".join(f"file '{s}'\n" for s in segments))
run("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-y", OUT)
if COMMENTARY:
    commentary(COMMENTARY)
print(OUT, f"{len(top)} highlights of {len(shown)} PRs in the video ({len(merged)} merged), {len(moving)} moving of {len(motion)} seconds, tmp {tmp}")
