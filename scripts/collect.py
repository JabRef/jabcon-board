#!/usr/bin/env python3
"""Aggregate the participants' public GitHub activity into data.json for the board.

Usage: GITHUB_TOKEN=... python scripts/collect.py [--force] [--out data.json]
Outside the JabCon window the script exits without writing unless --force is given.
Stats for merged PRs are reused from an existing output file (merged PRs never change).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "config.json")))
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN")
PARTICIPANTS = CONFIG["participants"]
START = datetime.fromisoformat(CONFIG["jabcon_start"])
END = datetime.fromisoformat(CONFIG["jabcon_end"])
START_DATE = START.astimezone(timezone.utc).strftime("%Y-%m-%d")
EXCLUDE = {r.lower() for r in CONFIG.get("exclude_repos", [])}
BOT_SUFFIX = "[bot]"


def get(path, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp), resp.headers
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 2:
                reset = int(e.headers.get("X-RateLimit-Reset", time.time() + 60))
                time.sleep(max(1, min(reset - time.time(), 120)))
                continue
            print(f"GET {url} -> {e.code}", file=sys.stderr)
            raise


def search(query):
    """All hits of a GitHub issues search (paged, 2 s between calls to stay under 30 req/min)."""
    items = []
    for page in range(1, 6):
        data, _ = get("/search/issues", {"q": query, "per_page": 100, "page": page, "sort": "updated"})
        items += data["items"]
        if len(items) >= data["total_count"] or not data["items"]:
            break
        time.sleep(2)
    time.sleep(2)
    return items


def qualifiers(name):
    return " ".join(f"{name}:{p}" for p in PARTICIPANTS)


def repo_of(item):
    return item["repository_url"].removeprefix(API + "/repos/")


def card(item, column):
    pr = "pull_request" in item
    return {
        "id": item["html_url"],
        "repo": repo_of(item),
        "number": item["number"],
        "title": item["title"],
        "url": item["html_url"],
        "type": "pr" if pr else "issue",
        "draft": bool(item.get("draft")),
        "author": item["user"]["login"],
        "assignees": [a["login"] for a in item.get("assignees", [])],
        "labels": [l["name"] for l in item.get("labels", [])],
        "updated_at": item["updated_at"],
        "closed_at": item.get("closed_at"),
        "merged_at": (item.get("pull_request") or {}).get("merged_at"),
        "column": column,
    }


def keep(item):
    return repo_of(item).lower() not in EXCLUDE and not item["user"]["login"].endswith(BOT_SUFFIX)


def collect_cards():
    """Search per column, then dedupe so each item lives in exactly one column (done > progress > backlog)."""
    columns = [
        ("done", f"is:pr is:merged merged:>={START_DATE} {qualifiers('involves')}"),
        ("done", f"is:issue is:closed closed:>={START_DATE} {qualifiers('involves')}"),
        ("progress", f"is:pr is:open updated:>={START_DATE} {qualifiers('author')}"),
        ("progress", f"is:pr is:open updated:>={START_DATE} {qualifiers('reviewed-by')}"),
        ("backlog", f"org:{CONFIG['org']} is:pr is:open label:ready-for-review"),
        ("backlog", f"is:open {qualifiers('assignee')}"),
    ]
    seen = {}
    for column, query in columns:
        for item in search(query):
            if item["html_url"] not in seen and keep(item):
                c = card(item, column)
                if column == "done":
                    when = c["merged_at"] or c["closed_at"]
                    if when and datetime.fromisoformat(when.replace("Z", "+00:00")) < START:
                        continue
                if column == "progress" and "reviewed-by" in query and c["author"] in PARTICIPANTS:
                    continue  # authored PRs count once, as authored
                seen[c["id"]] = c
    return list(seen.values())


def collect_events():
    events = []
    for p in PARTICIPANTS:
        data, _ = get(f"/users/{p}/events/public", {"per_page": 100})
        for e in data:
            if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) < START:
                continue
            if e["repo"]["name"].lower() in EXCLUDE:
                continue
            payload = e.get("payload", {})
            events.append({
                "id": e["id"],
                "type": e["type"],
                "action": payload.get("action"),
                "actor": e["actor"]["login"],
                "repo": e["repo"]["name"],
                "created_at": e["created_at"],
                "summary": summarize(e),
            })
    events.sort(key=lambda e: e["created_at"], reverse=True)
    return events


def summarize(e):
    p = e.get("payload", {})
    t = e["type"]
    issue = p.get("issue") or p.get("pull_request") or {}
    ref = f"#{issue['number']}" if issue.get("number") else ""
    return {
        "PushEvent": f"pushed {len(p.get('commits', []))} commit(s) to {p.get('ref', '').removeprefix('refs/heads/')}",
        "PullRequestEvent": f"{p.get('action')} PR {ref}: {issue.get('title', '')}",
        "PullRequestReviewEvent": f"reviewed PR {ref} ({(p.get('review') or {}).get('state', '').lower()})",
        "PullRequestReviewCommentEvent": f"commented on PR {ref}",
        "IssuesEvent": f"{p.get('action')} issue {ref}: {issue.get('title', '')}",
        "IssueCommentEvent": f"commented on {ref}: {issue.get('title', '')}",
        "CreateEvent": f"created {p.get('ref_type')} {p.get('ref') or ''}".strip(),
        "DeleteEvent": f"deleted {p.get('ref_type')} {p.get('ref') or ''}".strip(),
        "WatchEvent": "starred",
        "ForkEvent": "forked",
        "ReleaseEvent": f"released {(p.get('release') or {}).get('tag_name', '')}",
    }.get(t, t.removesuffix("Event").lower())


def component(repo, path):
    if repo == f"{CONFIG['org']}/jabref":
        return path.split("/")[0] if "/" in path else "(root)"
    return repo.split("/")[1]


def pr_stats(c, cached):
    if c["id"] in cached:
        return cached[c["id"]]
    pr, _ = get(f"/repos/{c['repo']}/pulls/{c['number']}")
    files, _ = get(f"/repos/{c['repo']}/pulls/{c['number']}/files", {"per_page": 100})
    comps = {}
    for f in files:
        comps[component(c["repo"], f["filename"])] = comps.get(component(c["repo"], f["filename"]), 0) + f["changes"]
    return {"additions": pr["additions"], "deletions": pr["deletions"], "changed_files": pr["changed_files"], "components": comps}


def leaderboard(cards, events):
    score = {p: {"merged": 0, "reviews": 0, "other": 0} for p in PARTICIPANTS}
    for c in cards:
        if c["column"] == "done" and c["type"] == "pr" and c["author"] in score:
            score[c["author"]]["merged"] += 1
    for e in events:
        s = score.get(e["actor"])
        if s is None:
            continue
        if e["type"] == "PullRequestReviewEvent":
            s["reviews"] += 1
        elif e["type"] in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "IssuesEvent", "PushEvent"):
            s["other"] += 1
    return [{"login": p, "points": v["merged"] * 3 + v["reviews"] * 2 + v["other"], **v} for p, v in score.items()]


def main():
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else "data.json"
    now = datetime.now(timezone.utc)
    if "--force" not in args and not (START <= now <= END):
        print(f"outside JabCon window ({START} .. {END}), nothing to do")
        return
    cached = {}
    if os.path.exists(out):
        try:
            cached = {c["id"]: c["stats"] for c in json.load(open(out))["cards"] if c.get("stats")}
        except (ValueError, KeyError):
            pass
    cards = collect_cards()
    events = collect_events()
    for c in cards:
        if c["column"] == "done" and c["type"] == "pr":
            c["stats"] = pr_stats(c, cached)
    totals = {"additions": 0, "deletions": 0, "changed_files": 0, "components": {}}
    for c in cards:
        for k in ("additions", "deletions", "changed_files"):
            totals[k] += c.get("stats", {}).get(k, 0)
        for comp, n in c.get("stats", {}).get("components", {}).items():
            totals["components"][comp] = totals["components"].get(comp, 0) + n
    data = {
        "generated_at": now.isoformat(timespec="seconds"),
        "config": CONFIG,
        "cards": cards,
        "events": events[:200],
        "stats": totals,
        "leaderboard": sorted(leaderboard(cards, events), key=lambda l: -l["points"]),
    }
    with open(out, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {out}: {len(cards)} cards, {len(events)} events")


if __name__ == "__main__":
    main()
