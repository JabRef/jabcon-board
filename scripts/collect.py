#!/usr/bin/env python3
"""Aggregate the participants' public GitHub activity into data.json for the board.

Usage: GITHUB_TOKEN=... python scripts/collect.py [--force] [--out data.json]
Outside the JabCon window the script exits without writing unless --force is given.
Stats for merged PRs are reused from an existing output file (merged PRs never change).
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "config.json")))
API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN")
# A fine-grained PAT scoped to private repos; used only for milestones and private_repos (it cannot run global searches: 422)
MILESTONE_TOKEN = os.environ.get("MILESTONE_TOKEN") or TOKEN
PARTICIPANTS = CONFIG["participants"]
START = datetime.fromisoformat(CONFIG["jabcon_start"])
END = datetime.fromisoformat(CONFIG["jabcon_end"])
START_DATE = START.astimezone(timezone.utc).strftime("%Y-%m-%d")
EXCLUDE = {r.lower() for r in CONFIG.get("exclude_repos", [])}
FOCUS = CONFIG.get("focus_label", "")
FOCUS_Q = f'org:{CONFIG["org"]} label:"{FOCUS}"' if FOCUS else ""
BOT_SUFFIX = "[bot]"
PR_AUTHORS = {}  # "owner/repo#n" -> login, loaded from the previous data.json


def get(path, params=None, token=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    token = token or TOKEN
    if token:
        req.add_header("Authorization", "Bearer " + token)
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
        "state_reason": item.get("state_reason"),  # issues: completed | not_planned | duplicate | reopened
        "merged_at": (item.get("pull_request") or {}).get("merged_at"),
        "column": column,
        "focus": bool(FOCUS) and FOCUS in [l["name"] for l in item.get("labels", [])],
    }


def keep(item):
    return repo_of(item).lower() not in EXCLUDE and not item["user"]["login"].endswith(BOT_SUFFIX)


def collect_cards():
    """Search per column, then dedupe so each item lives in exactly one column (done > progress > backlog)."""
    columns = [
        ("done", f"{FOCUS_Q} is:closed closed:>={START_DATE}"),
        ("done", f"is:pr is:merged merged:>={START_DATE} {qualifiers('involves')}"),
        ("done", f"is:pr is:closed is:unmerged closed:>={START_DATE} {qualifiers('involves')}"),
        ("done", f"is:issue is:closed closed:>={START_DATE} {qualifiers('involves')}"),
        ("progress", f"is:pr is:open updated:>={START_DATE} {qualifiers('author')}"),
        ("progress", f"is:pr is:open updated:>={START_DATE} {qualifiers('reviewed-by')}"),
        ("backlog", f"{FOCUS_Q} is:open"),
        ("backlog", f"org:{CONFIG['org']} is:pr is:open label:ready-for-review"),
        ("backlog", f"is:open {qualifiers('assignee')}"),
    ]
    seen = {}
    for column, query in columns:
        if query.startswith(" "):  # focus queries without a focus label configured
            continue
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


def collect_events(previous):
    """Events since START. The public feed only returns the newest 300 per user, so events seen in earlier runs
    (previous data.json) are kept; otherwise active participants would lose points as JabCon goes on."""
    seen = {e["id"]: e for e in previous}
    for p in PARTICIPANTS:
        for page in (1, 2, 3):
            data, _ = get(f"/users/{p}/events/public", {"per_page": 100, "page": page})
            for e in data:
                if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) < START:
                    continue
                if e["repo"]["name"].lower() in EXCLUDE:
                    continue  # a fresh fetch overwrites the stored copy, so new fields reach older events too
                payload = e.get("payload", {})
                number = (payload.get("issue") or payload.get("pull_request") or {}).get("number")
                seen[e["id"]] = {
                    "id": e["id"],
                    "type": e["type"],
                    "action": payload.get("action"),
                    "actor": e["actor"]["login"],
                    "repo": e["repo"]["name"],
                    "created_at": e["created_at"],
                    "summary": summarize(e),
                    "number": number,
                    "merged": bool((payload.get("pull_request") or {}).get("merged")),
                    # comments and reviews have their own html_url; issue/PR objects in events are slimmed and have
                    # none, /issues/N redirects to PRs too
                    "url": ((payload.get("comment") or payload.get("review") or {}).get("html_url")
                            or f"https://github.com/{e['repo']['name']}" + (f"/issues/{number}" if number else "")),
                    "excerpt": excerpt((payload.get("comment") or payload.get("review") or {}).get("body")),
                    "review_id": (payload.get("review") or {}).get("id") or (payload.get("comment") or {}).get("pull_request_review_id"),
                }
            if len(data) < 100 or datetime.fromisoformat(data[-1]["created_at"].replace("Z", "+00:00")) < START:
                break
    events = list(seen.values())
    events.sort(key=lambda e: e["created_at"], reverse=True)
    # reviewing one's own PR (e.g. replying to review threads) scores nothing; the slimmed PR object in the event
    # has no author, so resolve it once per PR and cache in data.json
    for e in events:
        if e["type"] in ("PullRequestReviewEvent", "PullRequestReviewCommentEvent") and e.get("number") and "self" not in e:
            key = f"{e['repo']}#{e['number']}"
            if key not in PR_AUTHORS:
                try:
                    pr, _ = get(f"/repos/{e['repo']}/pulls/{e['number']}")
                    PR_AUTHORS[key] = pr["user"]["login"]
                except urllib.error.HTTPError:
                    PR_AUTHORS[key] = ""
            e["self"] = PR_AUTHORS[key] == e["actor"]
    # a review made of inline comments only has an empty body: borrow the first inline comment's excerpt
    first_comment = {}
    for e in reversed(events):
        if e["type"] == "PullRequestReviewCommentEvent" and e.get("review_id") and e.get("excerpt"):
            first_comment.setdefault(e["review_id"], e["excerpt"])
    for e in events:
        if e["type"] == "PullRequestReviewEvent" and not e.get("excerpt"):
            e["excerpt"] = first_comment.get(e.get("review_id"), "")
    return events


def excerpt(body, limit=140):
    """First line of a comment, markdown-ish noise stripped, cut to limit."""
    if not body:
        return ""
    line = next((l.strip() for l in body.splitlines()
                 if l.strip() and not l.strip().startswith(("```", "<!--", ">", "|", "🤖"))), "")
    line = re.sub(r"[`*_#]+", "", line)
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def summarize(e):
    p = e.get("payload", {})
    t = e["type"]
    issue = p.get("issue") or p.get("pull_request") or {}
    ref = f"#{issue['number']}" if issue.get("number") else ""
    title = f": {issue['title']}" if issue.get("title") else ""
    return {
        "PushEvent": f"pushed {len(p.get('commits', []))} commit(s) to {p.get('ref', '').removeprefix('refs/heads/')}",
        "PullRequestEvent": f"{'merged' if (p.get('pull_request') or {}).get('merged') else p.get('action')} PR {ref}{title}",
        "PullRequestReviewEvent": f"reviewed PR {ref} ({(p.get('review') or {}).get('state', '').lower()})",
        "PullRequestReviewCommentEvent": f"commented on PR {ref}",
        "IssuesEvent": f"{p.get('action')} issue {ref}{title}",
        "IssueCommentEvent": f"commented on {ref}{title}",
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


# (weight, regex on added lines, label) - the nerdier the change, the higher the weight.
DETECTORS = [
    (6, r"\bsealed\s+(interface|class)\s+(\w+)", "sealed type {1}"),
    (6, r"Thread\.ofVirtual|newVirtualThreadPerTaskExecutor", "virtual threads"),
    (5, r"\brecord\s+(\w+)\s*\(", "record {0}"),
    (5, r"\bcase\s+[A-Z]\w*(<[^>]*>)?\s+\w+\s*->", "pattern-matching switch"),
    (4, r"\bcase\s+[A-Z]\w*\s*\(", "record deconstruction pattern"),
    (4, r"\binstanceof\s+[A-Z]\w*(<[^>]*>)?\s+\w+\b", "instanceof pattern"),
    (4, r"\bSequenced(Collection|Set|Map)\b|\.reversed\(\)", "sequenced collections"),
    (3, r"\bStructuredTaskScope\b|\bScopedValue\b", "structured concurrency"),
    (3, r"@NullMarked", "JSpecify null-marked"),
    (3, r'^\+\s*"""', "text block"),
    (3, r"\bswitch\s*\(.*\)\s*\{?\s*$|\bcase\s+.*->", "arrow switch"),
    (2, r"\bList\.of\(|\bMap\.of\(|\bSet\.of\(", "immutable collection literals"),
    (2, r"\.stream\(\)", "streams"),
    (2, r"^\+\s*///", "markdown javadoc"),
    (2, r"\bvar\s+\w+\s*=", "local var inference"),
    (2, r"\bOptional\.(ofNullable|of)\(|\.ifPresentOrElse\(", "Optional"),
]
DETECTORS = [(w, re.compile(rx, re.M), label) for w, rx, label in DETECTORS]


def refactorings(pr, files, repo):
    """Nerdy facts about a merged PR, mined from its patches. Returns [(weight, text)]."""
    found = []
    renamed = [f for f in files if f["status"] == "renamed"]
    removed = [f for f in files if f["status"] == "removed" and f["filename"].endswith(".java")]
    if renamed:
        f = renamed[0]
        found.append((3 + min(len(renamed), 5), f"moved {len(renamed)} file(s), e.g. {f['previous_filename'].rsplit('/', 1)[-1]} → {f['filename'].rsplit('/', 1)[-1]}"))
    if removed:
        found.append((3 + min(len(removed), 5), f"deleted {', '.join(f['filename'].rsplit('/', 1)[-1].removesuffix('.java') for f in removed[:3])}" + (" …" if len(removed) > 3 else "")))
    if pr["deletions"] > pr["additions"] * 1.5 and pr["deletions"] > 50:
        found.append((4, f"net −{pr['deletions'] - pr['additions']} lines"))
    if any(f["filename"].endswith("module-info.java") for f in files):
        found.append((4, "module boundary changed"))
    added = "\n".join(l for f in files if f["filename"].endswith(".java") for l in f.get("patch", "").splitlines() if l.startswith("+"))
    hits = {}
    for w, rx, label in DETECTORS:
        for m in rx.finditer(added):
            text = label.format(*m.groups("")) if "{" in label else label
            hits[text] = w
            break
    found += [(w, t) for t, w in hits.items()]
    return sorted(found, reverse=True)[:4]


def pr_stats(c, cached):
    if c["id"] in cached and "refactorings" in cached[c["id"]]:
        return cached[c["id"]]
    pr, _ = get(f"/repos/{c['repo']}/pulls/{c['number']}")
    files, _ = get(f"/repos/{c['repo']}/pulls/{c['number']}/files", {"per_page": 100})
    comps = {}
    for f in files:
        comps[component(c["repo"], f["filename"])] = comps.get(component(c["repo"], f["filename"]), 0) + f["changes"]
    return {"additions": pr["additions"], "deletions": pr["deletions"], "changed_files": pr["changed_files"], "components": comps,
            "refactorings": refactorings(pr, files, c["repo"])}


def leaderboard(cards, events, private):
    score = {p: {"merged": 0, "reviews": 0, "other": 0} for p in PARTICIPANTS}
    for counts in private.values():
        for p, n in counts["by"].items():
            score[p]["other"] += n
    for c in cards:
        if c["column"] == "done" and c["type"] == "pr" and c["author"] in score:
            score[c["author"]]["merged"] += 1
    for e in events:
        s = score.get(e["actor"])
        if s is None:
            continue
        if e.get("self"):
            continue
        if e["type"] == "PullRequestReviewEvent":
            s["reviews"] += 1
        elif e["type"] in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "IssuesEvent", "PushEvent"):
            s["other"] += 1
    return [{"login": p, "points": v["merged"] * 3 + v["reviews"] * 2 + v["other"], **v} for p, v in score.items()]


def milestones(previous):
    """Milestone progress; the closed count when first seen (usually JabCon start) is kept as the baseline."""
    result = []
    for ref in CONFIG.get("milestones", []):
        owner, repo, number = ref.split("/")
        try:
            m, _ = get(f"/repos/{owner}/{repo}/milestones/{number}", token=MILESTONE_TOKEN)
        except urllib.error.HTTPError as e:
            print(f"::warning::milestone {ref} skipped ({e.code}; private repo? set the BOARD_TOKEN secret)")
            continue
        baseline = next((p["baseline"] for p in previous if p["ref"] == ref), m["closed_issues"])
        result.append({"ref": ref, "repo": f"{owner}/{repo}", "title": m["title"], "url": m["html_url"],
                       "open": m["open_issues"], "closed": m["closed_issues"], "baseline": min(baseline, m["closed_issues"])})
    return result


def private_activity():
    """Counts only (no titles, no numbers): data.json is public, the repos are not."""
    result = {}
    for repo in CONFIG.get("private_repos", []):
        counts = {"opened": 0, "closed": 0, "comments": 0, "by": {p: 0 for p in PARTICIPANTS}}
        try:
            events, _ = get(f"/repos/{repo}/events", {"per_page": 100}, token=MILESTONE_TOKEN)
        except urllib.error.HTTPError as e:
            print(f"::warning::private repo {repo} skipped ({e.code}; set the BOARD_TOKEN secret)")
            continue
        for e in events:
            if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) < START:
                continue
            action = e.get("payload", {}).get("action")
            kind = {("IssuesEvent", "opened"): "opened", ("IssuesEvent", "closed"): "closed", ("IssueCommentEvent", "created"): "comments"}.get((e["type"], action))
            if kind is None:
                continue
            counts[kind] += 1
            if e["actor"]["login"] in counts["by"]:
                counts["by"][e["actor"]["login"]] += 1
        result[repo] = counts
    return result


def focus_progress():
    """Open vs. closed-since-start counts for the focus label, drawn like a milestone."""
    if not FOCUS:
        return None
    open_count = get("/search/issues", {"q": f"{FOCUS_Q} is:open", "per_page": 1})[0]["total_count"]
    closed = get("/search/issues", {"q": f"{FOCUS_Q} is:closed closed:>={START_DATE}", "per_page": 1})[0]["total_count"]
    return {"label": FOCUS, "open": open_count, "closed": closed,
            "url": f"https://github.com/issues?q={urllib.parse.quote(FOCUS_Q + ' is:open')}"}


def main():
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else "data.json"
    now = datetime.now(timezone.utc)
    if "--force" not in args and not (START <= now <= END):
        print(f"outside JabCon window ({START} .. {END}), nothing to do")
        return
    cached, previous_milestones, previous_events = {}, [], []
    if os.path.exists(out):
        try:
            previous = json.load(open(out))
            cached = {c["id"]: c["stats"] for c in previous["cards"] if c.get("stats")}
            previous_milestones = previous.get("milestones", [])
            previous_events = previous.get("all_events", [])
            PR_AUTHORS.update(previous.get("pr_authors", {}))
        except (ValueError, KeyError):
            pass
    cards = collect_cards()
    events = collect_events(previous_events)
    for c in cards:
        if c["column"] == "done" and c["type"] == "pr":
            c["stats"] = pr_stats(c, cached)
    totals = {"additions": 0, "deletions": 0, "changed_files": 0, "components": {}}
    for c in cards:
        for k in ("additions", "deletions", "changed_files"):
            totals[k] += c.get("stats", {}).get(k, 0)
        for comp, n in c.get("stats", {}).get("components", {}).items():
            totals["components"][comp] = totals["components"].get(comp, 0) + n
    private = private_activity()
    nerdy = sorted(({"weight": w, "text": t, "repo": c["repo"], "number": c["number"], "author": c["author"], "url": c["url"]}
                    for c in cards for w, t in c.get("stats", {}).get("refactorings", [])), key=lambda r: -r["weight"])[:5]
    data = {
        "refactorings": nerdy,
        "milestones": milestones(previous_milestones),
        "focus": focus_progress(),
        "private_activity": private,
        "generated_at": now.isoformat(timespec="seconds"),
        "config": CONFIG,
        "cards": cards,
        "events": events[:200],
        "all_events": events,
        "pr_authors": PR_AUTHORS,
        "stats": totals,
        "leaderboard": sorted(leaderboard(cards, events, private), key=lambda l: -l["points"]),
    }
    with open(out, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {out}: {len(cards)} cards, {len(events)} events")


if __name__ == "__main__":
    main()
