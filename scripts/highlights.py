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
from datetime import datetime

DATA, VIDEO, OUT = sys.argv[1:4]
COUNT = int(sys.argv[4]) if len(sys.argv) > 4 else 6
REPO = "JabRef/jabref"
SECONDS_PER_DAY = 100  # gource_seconds_per_day in JabRef/jabref's gource-jabcon.yml
# ponytail: gource's --auto-skip-seconds is 30, but the rendered video is shorter than that simulation; 12 matches the
# real length best. Positions are stretched to the real duration anyway, so this only tunes the in-between spacing.
SKIP_CAP = float(os.environ.get("SKIP_CAP", 12))
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

# simulate gource's timeline (idle stretches skipped), then stretch it onto the real video length
position, video_t, prev = {}, 0.0, start
for c in merged:
    video_t += min(SKIP_CAP, (when(c) - prev).total_seconds() * SECONDS_PER_DAY / 86400)
    position[c["number"]], prev = video_t, when(c)
scale = duration / video_t if video_t else 1
top = sorted(sorted(merged, key=lambda c: -(c["stats"].get("complexity") or 0))[:COUNT], key=when)

tmp = tempfile.mkdtemp()
segments = []


def run(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args], check=True)


def crawl(name, text, title=""):
    """Yellow text crawling into the distance; the tilt is a perspective warp of a flat scrolling canvas."""
    path = os.path.join(tmp, f"{name}.txt")
    open(path, "w").write(text)
    vf = (f"drawtext=textfile='{path}':font='{FONT}':fontsize=54:fontcolor=#ffd23f:line_spacing=18:x=(w-text_w)/2"
          f":y=h-t*{SPEED},"
          # narrow the top: letters lean towards the vanishing point, as in the real crawl
          f"perspective=x0={W * 0.3}:y0=0:x1={W * 0.7}:y1=0:x2=0:y2={H}:x3={W}:y3={H}:sense=destination,"
          "fade=t=out:st=%d:d=0.5" % (CRAWL - 0.5))
    if title:
        vf = f"drawtext=text='{title}':font='{FONT}':fontsize=40:fontcolor=#4bd5ee:x=(w-text_w)/2:y=h*0.42:enable='lt(t,2.2)'," + vf
    out = os.path.join(tmp, f"{name}.mp4")
    run("-f", "lavfi", "-i", f"color=black:s={W}x{H}:d={CRAWL}", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={CRAWL}",
        "-vf", vf, *ENC, out)
    segments.append(out)


def boom(name, at, label):
    """BOOM at the merge moment: white flash, zoom punch, camera shake and an RGB-split glitch over half a second, with a
    bass hit; the clip runs LEAD seconds of plain gource before, so the eye has settled when it hits."""
    at = max(0.0, min(at - LEAD, duration - LEAD - TAIL))
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
    body = f"Episode {i + 1}\n\n{c['title']}\n\nby {c['author']}\n\n+{c['stats']['additions']} / -{c['stats']['deletions']} lines\n\n\n\n\n"
    crawl(f"crawl{i}", body)
    boom(f"boom{i}", position[c["number"]] * scale, f"#{c['number']} merged by {c['author']}".replace("'", ""))
crawl("outro", "To be continued...\n\n\n\n\n")

lst = os.path.join(tmp, "list.txt")
open(lst, "w").write("".join(f"file '{s}'\n" for s in segments))
run("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-y", OUT)
print(OUT, f"{len(top)} highlights, {len(segments)} segments, tmp {tmp}")
