#!/usr/bin/env python3
"""Highlights reel from the gource video: a Star-Wars crawl introducing each of the biggest merged PRs over the gource
footage leading up to its merge, then a BOOM at the merge moment. Only seconds in which gource moves are used, so the
reel never shows a still. Only needs ffmpeg (drawtext, perspective) and the board's data.json.

    scripts/highlights.py data.json jabcon-2026.mp4 highlights.mp4 [count]
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timedelta

DATA, VIDEO, OUT = sys.argv[1:4]
COUNT = int(sys.argv[4]) if len(sys.argv) > 4 else 6
REPO = "JabRef/jabref"
# gource's timeline, fitted against the clock gource draws into the frames (JabRef/jabref's gource-jabcon.yml asks for
# 100 s/day and --auto-skip-seconds 30; the rendered video runs 1.5x faster, and starts a quarter hour early).
# ponytail: refit these three when the clock in the video drifts from the "merged by" labels.
SECONDS_PER_DAY = float(os.environ.get("SECONDS_PER_DAY", 67))
SKIP_CAP = float(os.environ.get("SKIP_CAP", 23))  # video seconds of idling before gource skips to the next commit
START_OFFSET = timedelta(minutes=-15)
END_HOLD = 10  # gource holds the final frame this long after the last commit; the graph settles over the first 3 s
CRAWL, SPEED = 7, 165  # seconds per card, crawl px/s
TAIL = 6  # moving gource seconds after the boom; the crawl runs over the CRAWL moving seconds before it
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
                               "--jq", ".[].commit.author.date"], text=True).split()
commits = sorted(datetime.fromisoformat(d.replace("Z", "+00:00")) for d in log)
position, video_t, prev = {}, 0.0, start + START_OFFSET  # commit time -> video second
for t in commits:
    if t < prev:
        continue
    video_t += min(SKIP_CAP, (t - prev).total_seconds() * SECONDS_PER_DAY / 86400)
    position[t], prev = video_t, t
# the video may lag behind the log by a render: only commits that fit before the final hold are in it
moving_end = max((v for v in position.values() if v + END_HOLD <= duration + 1), default=0) + 3


def moment(c):
    """Video second of a merged PR's commit: the closest one within 25 minutes (the merge queue rebases the commit well
    before the merge is recorded), None when the video does not contain it yet."""
    t = min(position, key=lambda t: abs((t - when(c)).total_seconds()), default=None)
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
    text_v = (f"[1:v]drawtext=textfile='{path}':font='{FONT}':fontsize=54:fontcolor=#ffd23f:line_spacing=18:x=(w-text_w)/2"
              f":y=h-t*{SPEED},"
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


def around(second):
    """The last CRAWL moving seconds before this one and the first TAIL moving seconds from it on."""
    return [k for k in moving if k < second][-CRAWL:], [k for k in moving if k >= second][:TAIL]


year = start.year
highlight("intro", f"JabCon {year}\n\n{len(merged)} pull requests merged\ninto {REPO}\n\nThese are the {len(top)} biggest.\n\n\n\n\n",
          moving[:CRAWL], title="A long time ago in a repository far, far away....")
for i, c in enumerate(top):
    body = f"Episode {i + 1}\n\n{textwrap.fill(c['title'], 34)}\n\nby {c['author']}\n\n+{c['stats']['additions']} / -{c['stats']['deletions']} lines\n\n\n\n\n"
    before, after = around(int(moment(c)))
    highlight(f"pr{i}", body, before, after, label=f"#{c['number']} merged by {c['author']}".replace("'", ""))
highlight("outro", "To be continued...\n\n\n\n\n", moving[-CRAWL:])

lst = os.path.join(tmp, "list.txt")
open(lst, "w").write("".join(f"file '{s}'\n" for s in segments))
run("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-y", OUT)
print(OUT, f"{len(top)} highlights of {len(shown)} PRs in the video ({len(merged)} merged), {len(moving)} moving of {len(motion)} seconds, tmp {tmp}")
