#!/usr/bin/env python3
"""Highlights reel from the gource video: a Star-Wars crawl introducing each of the biggest merged PRs, then a BOOM
into the gource clip of the moment it was merged. Only needs ffmpeg (drawtext, perspective) and the board's data.json.

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
LEAD, TAIL = 5, 6  # gource seconds shown before the boom hits at the merge moment, and after
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
    if t is None or abs((t - when(c)).total_seconds()) > 1500 or position[t] + TAIL > moving_end:
        return None
    return position[t]


shown = [c for c in merged if moment(c) is not None]
top = sorted(sorted(shown, key=lambda c: -(c["stats"].get("complexity") or 0))[:COUNT], key=when)

tmp = tempfile.mkdtemp()
segments = []


def run(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args], check=True)


def crawl(name, text, title=""):
    """Yellow text crawling into the distance; the tilt is a perspective warp of a flat scrolling canvas."""
    path = os.path.join(tmp, f"{name}.txt")
    open(path, "w").write(text)
    vf = (f"geq=r=0:g='4*max(0,(Y-{H // 2})/{H // 2})':b='48*max(0,(Y-{H // 2})/{H // 2})',"
          f"drawtext=textfile='{path}':font='{FONT}':fontsize=54:fontcolor=#ffd23f:line_spacing=18:x=(w-text_w)/2"
          f":y=h-t*{SPEED},"
          # narrow the top: letters lean towards the vanishing point, as in the real crawl
          f"perspective=x0={W * 0.3}:y0=0:x1={W * 0.7}:y1=0:x2=0:y2={H}:x3={W}:y3={H}:sense=destination,"
          "fade=t=out:st=%d:d=0.5" % (CRAWL - 0.5))
    if title:
        vf = f"drawtext=text='{title}':font='{FONT}':fontsize=40:fontcolor=#4bd5ee:x=(w-text_w)/2:y=h*0.42:enable='lt(t,2.2)'," + vf
    out = os.path.join(tmp, f"{name}.mp4")
    # a faint glow at the bottom makes the frame edge visible, so text entering there reads as entering, not as cut off
    run("-f", "lavfi", "-i", f"color=black:s={W}x{H}:d={CRAWL}", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={CRAWL}",
        "-vf", vf, *ENC, out)
    segments.append(out)


def boom(name, at, label):
    """BOOM at the merge moment: white flash, zoom punch, camera shake and an RGB-split glitch over half a second, with a
    bass hit; the clip runs LEAD seconds of plain gource before, so the eye has settled when it hits."""
    at = max(0.0, at - LEAD)
    b, clip = LEAD, LEAD + TAIL
    vf = (f"scale={W * 1.2}:{H * 1.2},"
          f"crop={W}:{H}:x='{W * 0.1}+if(between(t,{b},{b + 0.6}),(random(0)-0.5)*160*({b + 0.6}-t),0)'"
          f":y='{H * 0.1}+if(between(t,{b},{b + 0.6}),(random(0)-0.5)*160*({b + 0.6}-t),0)',"
          f"zoompan=z='if(between(in,{b * 30},{b * 30 + 15}),1.6-(in-{b * 30})*0.04,1)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,"
          f"rgbashift=rh=25:bh=-25:enable='between(t,{b},{b + 0.35})',"
          f"eq=brightness='if(between(t,{b},{b + 0.4}),({b + 0.4}-t)/0.4,0)':saturation='if(between(t,{b},{b + 0.4}),0,1)':eval=frame,"
          f"drawtext=text='{label}':font='{FONT}':fontsize=64:fontcolor=white:borderw=3:bordercolor=black"
          f":x=(w-text_w)/2:y=h-140:alpha='if(lt(t,{b + 0.5}),0,min(1,(t-{b + 0.5})*2))'")
    af = (f"aevalsrc='if(gte(t,{b}),exp(-5*(t-{b}))*(0.9*sin(2*PI*48*(t-{b}))+0.5*sin(2*PI*31*(t-{b}))"
          f"+0.6*exp(-40*(t-{b}))*(random(0)*2-1)),0)':c=stereo:s=44100:d={clip}")
    out = os.path.join(tmp, f"{name}.mp4")
    run("-ss", f"{at:.2f}", "-t", str(clip), "-i", VIDEO, "-f", "lavfi", "-i", af, "-vf", vf, "-map", "0:v", "-map", "1:a", *ENC, out)
    segments.append(out)


year = start.year
crawl("intro", f"JabCon {year}\n\n{len(merged)} pull requests merged\ninto {REPO}\n\nThese are the {len(top)} biggest.\n\n\n\n\n",
      "A long time ago in a repository far, far away....")
for i, c in enumerate(top):
    body = f"Episode {i + 1}\n\n{textwrap.fill(c['title'], 34)}\n\nby {c['author']}\n\n+{c['stats']['additions']} / -{c['stats']['deletions']} lines\n\n\n\n\n"
    crawl(f"crawl{i}", body)
    boom(f"boom{i}", moment(c), f"#{c['number']} merged by {c['author']}".replace("'", ""))
crawl("outro", "To be continued...\n\n\n\n\n")

lst = os.path.join(tmp, "list.txt")
open(lst, "w").write("".join(f"file '{s}'\n" for s in segments))
run("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-y", OUT)
print(OUT, f"{len(top)} highlights of {len(shown)} PRs in the video ({len(merged)} merged), footage moves until {moving_end:.0f}s of {duration:.0f}s, tmp {tmp}")
