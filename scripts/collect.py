#!/usr/bin/env python3
"""Aggregate the participants' public GitHub activity into data.json for the board.

Usage: GITHUB_TOKEN=... python scripts/collect.py [--force] [--out data.json]
Outside the JabCon window the script exits without writing unless --force is given.
Stats for merged PRs are reused from an existing output file (merged PRs never change).
"""
import base64
from collections import Counter
import email.utils
import gzip
import hashlib
import json
import mailbox
import os
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header

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
# [impl->req~private-counts-only~1] private repos never yield cards, whatever the token can see
EXCLUDE = {r.lower() for r in CONFIG.get("exclude_repos", []) + CONFIG.get("private_repos", [])}
FOCUS = CONFIG.get("focus_label", "")
FOCUS_Q = f'org:{CONFIG["org"]} label:"{FOCUS}"' if FOCUS else ""
MILESTONE_REFS = set(CONFIG.get("milestones", []))
BOT_SUFFIX = "[bot]"
# work an automation does under a human account (Crowdin's translation PRs and the branch they live on)
# [impl->req~automation-excluded~1]
EXCLUDE_TITLE = re.compile("|".join(CONFIG.get("exclude_titles") or ["(?!)"]), re.I)
EXCLUDE_BRANCH = set(CONFIG.get("exclude_branches", []))
AUTOMATED = set()  # (repo, number) of the items skipped above, so their events go too
# list address -> the repo whose repo_factor and link a post to it uses
MAILING_LISTS = CONFIG.get("mailing_lists", {})
MAIL_ARCHIVE = "https://mail.openjdk.org/archives/list/{}/"
PR_AUTHORS = {}  # "owner/repo#n" -> login, loaded from the previous data.json
# a comment signed by the robot or naming Claude is the assistant talking, not the participant
# [impl->req~no-ai-comment-points~1]
AI_COMMENT = re.compile(r"\U0001f916|\bclaude\b", re.I)


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


def get_all(path, params=None, token=None):
    """Fetch every page of a GitHub list endpoint."""
    params = dict(params or {})
    per_page = params.get("per_page", 100)
    items = []
    page = 1
    while True:
        page_items, _ = get(path, {**params, "page": page, "per_page": per_page}, token)
        items.extend(page_items)
        if len(page_items) < per_page:
            break
        page += 1
    return items


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
        "created_at": item.get("created_at"),  # how old the item is, for the necromancer award
        "updated_at": item["updated_at"],
        "closed_at": item.get("closed_at"),
        "state_reason": item.get("state_reason"),  # issues: completed | not_planned | duplicate | reopened
        "merged_at": (item.get("pull_request") or {}).get("merged_at"),
        "column": column,
        # [impl->req~column-order~2] JabCon item: focus label or one of the configured milestones
        "focus": (bool(FOCUS) and FOCUS in [l["name"] for l in item.get("labels", [])])
                 or f"{repo_of(item)}/{(item.get('milestone') or {}).get('number')}" in MILESTONE_REFS,
    }


# [impl->req~bots-excluded~1]
def keep(item):
    if EXCLUDE_TITLE.search(item["title"]):
        AUTOMATED.add((repo_of(item), item["number"]))
        return False
    return repo_of(item).lower() not in EXCLUDE and not item["user"]["login"].endswith(BOT_SUFFIX)


# [impl->req~one-column-per-item~1]
# [impl->req~in-progress-recent~1]
# [impl->req~backlog-jabcon-only~1]
def collect_cards(milestones):
    """Search per column, then dedupe so each item lives in exactly one column (done > progress > backlog)."""
    columns = [
        ("done", f"{FOCUS_Q} is:closed closed:>={START_DATE}"),
        ("done", f"is:pr is:merged merged:>={START_DATE} {qualifiers('involves')}"),
        ("done", f"is:pr is:closed is:unmerged closed:>={START_DATE} {qualifiers('involves')}"),
        ("done", f"is:issue is:closed closed:>={START_DATE} {qualifiers('involves')}"),
        ("progress", f"is:pr is:open updated:>={START_DATE} {qualifiers('author')}"),
        ("progress", f"is:pr is:open updated:>={START_DATE} {qualifiers('reviewed-by')}"),
        ("backlog", f"{FOCUS_Q} is:open"),
    ] + [("backlog", f'repo:{m["repo"]} milestone:"{m["title"]}" is:open') for m in milestones if m["repo"].lower() not in EXCLUDE]
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


# [impl->req~events-accumulate~1]
# [impl->req~no-self-review-points~1]
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
                    # [impl->req~no-ai-comment-points~1] a comment the assistant wrote scores nothing
                    "ai": bool(AI_COMMENT.search((payload.get("comment") or payload.get("review") or {}).get("body") or "")),
                    "review_id": (payload.get("review") or {}).get("id") or (payload.get("comment") or {}).get("pull_request_review_id"),
                    "before": payload.get("before"), "head": payload.get("head"),
                    # resolved once below and cached in data.json
                    "commits": seen.get(e["id"], {}).get("commits"), "sync": seen.get(e["id"], {}).get("sync"),
                }
            if len(data) < 100 or datetime.fromisoformat(data[-1]["created_at"].replace("Z", "+00:00")) < START:
                break
    # [impl->req~automation-excluded~1] the automation's own PRs and pushes are not the participant's work
    events = [e for e in seen.values()
              if (e["repo"], e.get("number")) not in AUTOMATED
              and (e["type"] != "PushEvent" or ((e.get("summary") or " ").split()[-1] not in EXCLUDE_BRANCH))]
    # events cached before the rule existed have no full body left; their stored excerpt is all there is to check
    # [impl->req~no-ai-comment-points~1]
    for e in events:
        e.setdefault("ai", bool(AI_COMMENT.search(e.get("excerpt") or "")))
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
    # the public feed carries no commit list: resolve the push once; a push to a repo outside the org without a
    # commit by the actor (fork sync) scores nothing; in the org that shape is a squash merge, which keeps its point
    # [impl->req~no-fork-sync-points~1]
    for e in events:
        if e["type"] == "PushEvent" and e.get("commits") is None and e.get("before"):
            try:
                cmp, _ = get(f"/repos/{e['repo']}/compare/{e['before']}...{e['head']}")
                e["commits"] = cmp["total_commits"]
                # [impl->req~bonus-points~19] the old head is no ancestor of the new one: history was rewritten
                e["forced"] = cmp["status"] in ("diverged", "behind")
                e["sync"] = (not e["repo"].startswith(CONFIG["org"] + "/")
                             and not any((c.get("author") or {}).get("login") == e["actor"] for c in cmp["commits"]))
            except urllib.error.HTTPError:  # new branch: before is all zeros
                e["commits"], e["sync"] = 0, False
            branch = e["summary"].removeprefix("pushed to ")
            e["summary"] = f"synced {branch}" if e["sync"] else f"pushed {e['commits']} commit(s) to {branch}"
    # a review made of inline comments only has an empty body: borrow the first inline comment's excerpt
    first_comment = {}
    for e in reversed(events):
        if e["type"] == "PullRequestReviewCommentEvent" and e.get("review_id") and e.get("excerpt"):
            first_comment.setdefault(e["review_id"], e["excerpt"])
    for e in events:
        if e["type"] == "PullRequestReviewEvent" and not e.get("excerpt"):
            e["excerpt"] = first_comment.get(e.get("review_id"), "")
    return events


def header(msg, name):
    return " ".join(str(make_header(decode_header(msg.get(name, "")))).split())


def plain_text(msg):
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True) or b""
            return body.decode(part.get_content_charset() or "utf-8", "replace")
    return ""


# [impl->req~mailing-lists~1]
def mail_events():
    """Participants' posts to the configured mailing lists, read from the HyperKitty archive.

    Mails sent from an @openjdk.org address are the Skara bot mirroring GitHub PR activity that the events API
    already reports; counting them again would double every JavaFX review. Only real mail is left."""
    if not MAILING_LISTS:
        return []
    who = {}
    for p in PARTICIPANTS:
        u, _ = get(f"/users/{p}")
        if u.get("email"):
            who[u["email"].lower()] = p
        if u.get("name") and " " in u["name"]:  # a one-word display name ("Christoph") also matches strangers
            who[u["name"].lower()] = p
    events = []
    for addr, repo in MAILING_LISTS.items():
        window = {"start": START_DATE, "end": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")}
        url = MAIL_ARCHIVE.format(addr) + "export/jabcon.mbox.gz?" + urllib.parse.urlencode(window)
        req = urllib.request.Request(url, headers={"User-Agent": "jabcon-board"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = gzip.decompress(resp.read())
        except Exception as e:  # a mail archive being down must not cost the board its GitHub data
            print(f"mailing list {addr}: {e}", file=sys.stderr)
            continue
        with tempfile.NamedTemporaryFile(suffix=".mbox") as f:  # mailbox.mbox only reads from a path
            f.write(raw)
            f.flush()
            for m in mailbox.mbox(f.name):
                name, sender = email.utils.parseaddr(header(m, "From"))
                if sender.lower().endswith("@openjdk.org"):
                    continue
                login = who.get(sender.lower()) or who.get(name.lower())
                mid = (m.get("Message-ID") or "").strip().strip("<>")
                if not login or not mid:
                    continue
                try:
                    when = email.utils.parsedate_to_datetime(m.get("Date"))
                except (TypeError, ValueError):
                    continue
                if when < START:
                    continue
                # HyperKitty addresses a message by the base32 of the SHA-1 of its Message-ID
                hashid = base64.b32encode(hashlib.sha1(mid.encode()).digest()).decode()
                subject = re.sub(r"^(\[External\]\s*:\s*)+", "", header(m, "Subject"))
                # drop the quoted mail and the "On ... wrote:" line above it, so the excerpt is what was written now
                body = "\n".join(l for l in plain_text(m).splitlines() if not re.match(r"\s*On .*wrote:\s*$", l))
                events.append({
                    "id": "mail:" + hashid,
                    "type": "MailEvent",
                    "actor": login,
                    "repo": repo,
                    "created_at": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "summary": f"mailed {addr.split('@')[0]}: {subject}",
                    "url": MAIL_ARCHIVE.format(addr) + f"message/{hashid}/",
                    "excerpt": excerpt(body),
                    "number": None,
                })
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
        "PushEvent": f"pushed to {p.get('ref', '').removeprefix('refs/heads/')}",  # the public feed carries no commit list
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
MODULE_FILES = (".gradle", ".gradle.kts", "pom.xml", "module-info.java")
GRADLE_MODULE = re.compile(r"(?m)^[ \t]*module\s*\((?:[^()\"']|\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|\([^()]*\))*\)")
JAVA_MODULE = re.compile(r"(?m)^[ \t]*(?:open[ \t]+)?module[ \t]+[\w.]+\s*\{")
MAVEN_MODULE = re.compile(r"<module>\s*[^<]+?\s*</module>")


# Names of the AI assistants that sign commits; the first match on a trailer line wins, so keep the
# specific model names above the generic tool names.
# [impl->req~ai-models~1]
AI_MODELS = [re.compile(p, re.I) for p in [
    r"Claude (?:Opus|Sonnet|Haiku|Fable)[\w .]*",
    r"GPT-[\w.]+", r"Gemini [\w.]+", r"Devstral|Codestral|Qwen[\w.-]*|Llama[\w.-]*",
    r"Claude Code", r"Claude", r"GitHub Copilot", r"Copilot", r"Cursor", r"Codex", r"Gemini",
    r"Junie", r"Windsurf", r"Aider", r"Devin",
]]
AI_TRAILER = re.compile(r"\s*(co-authored-by\s*:|assisted-by\s*:|.*generated with)", re.I)


def ai_models(messages):
    """AI assistants credited in a PR's commit messages (co-author trailers, tool sign-off lines)."""
    found = set()
    for msg in messages:
        for line in msg.splitlines():
            if not AI_TRAILER.match(line):
                continue
            for rx in AI_MODELS:
                hit = rx.search(line)
                if hit:
                    found.add(hit.group(0).strip())
                    break
    # a Claude Code commit signs both the tool and the model; the model is the interesting half
    if any(f.lower().startswith(("claude opus", "claude sonnet", "claude haiku", "claude fable")) for f in found):
        found -= {"Claude", "Claude Code"}
    return sorted(found)


def refactorings(pr, files, repo):
    """Nerdy facts about a merged PR, mined from its patches. Returns [(weight, text)]."""
    # [impl->req~nerd-corner~6]
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
    module_added, module_removed = module_changes(files, repo, pr.get("base", {}).get("sha"), pr.get("head", {}).get("sha"))
    if module_added or module_removed:
        found.append((4, f"module metadata changed (+{module_added} / −{module_removed})"))
    elif any(f["filename"].endswith("module-info.java") for f in files):
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


def source_at(repo, path, ref):
    """Read a small source file at a PR ref; module descriptors are kept well below the API size limit."""
    data, _ = get(f"/repos/{repo}/contents/{urllib.parse.quote(path, safe='/')}", {"ref": ref})
    return base64.b64decode(data["content"]).decode()


def strip_comments(text):
    """Remove source comments without treating comment markers inside strings as comments."""
    out = []
    quote = None
    i = 0
    while i < len(text):
        if quote:
            out.append(text[i])
            if text[i] == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if text[i] == quote:
                quote = None
            i += 1
            continue
        if text.startswith("//", i):
            newline = text.find("\n", i + 2)
            i = len(text) if newline < 0 else newline
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            i = len(text) if end < 0 else end + 3
            continue
        if text[i] in "\"'":
            quote = text[i]
        out.append(text[i])
        i += 1
    return "".join(out)


def declarations(text, filename):
    """Extract normalized module declarations from one complete source file."""
    text = strip_comments(text)
    if filename.endswith((".gradle", ".gradle.kts")):
        text = re.sub(r'"""[\s\S]*?"""', "", text)
        text = re.sub(r"'''[\s\S]*?'''", "", text)
    elif filename.endswith("pom.xml"):
        text = re.sub(r"<!\[CDATA\[[\s\S]*?\]\]>", "", text)
    pattern = GRADLE_MODULE if filename.endswith((".gradle", ".gradle.kts")) else MAVEN_MODULE if filename.endswith("pom.xml") else JAVA_MODULE
    return [re.sub(r"\s+", " ", match).strip() for match in pattern.findall(text)]


def module_changes(files, repo=None, base=None, head=None):
    """Return added and removed module declarations from complete files, or reconstructed patch hunks in tests."""
    added, removed = Counter(), Counter()
    for f in files:
        if not f["filename"].endswith(MODULE_FILES):
            continue
        old_text = new_text = None
        if repo and base and f["status"] != "added":
            old_text = source_at(repo, f.get("previous_filename", f["filename"]), base)
        if repo and head and f["status"] != "removed":
            new_text = source_at(repo, f["filename"], head)
        if old_text is not None or new_text is not None:
            old_filename = f.get("previous_filename", f["filename"])
            old_declarations = declarations(old_text or "", old_filename)
            new_declarations = declarations(new_text or "", f["filename"])
        else:
            old_declarations, new_declarations = patch_declarations(f.get("patch", ""), f["filename"])
        added.update(new_declarations)
        removed.update(old_declarations)
    return sum((added - removed).values()), sum((removed - added).values())


def patch_declarations(patch, filename):
    """Build the old and new views available in a patch, used when source refs are unavailable in unit tests."""
    new, old = [], []
    for line in patch.splitlines():
        if line.startswith(("@@", "+++", "---")):
            continue
        if line.startswith("+"):
            new.append(line[1:])
        elif line.startswith("-"):
            old.append(line[1:])
        elif line.startswith(" "):
            new.append(line[1:])
            old.append(line[1:])
    return declarations("\n".join(old), filename), declarations("\n".join(new), filename)


# [impl->req~scoring~9]
BRANCH = re.compile(r"\b(if|for|while|case|catch)\b|&&|\|\|")
CODE = (".java", ".kt", ".js", ".ts", ".py", ".sh", ".fxml")


def complexity(files):
    """Cyclomatic complexity of the added code, McCabe-style on the diff: 1 + branch points in added lines of source
    files. Docs, config and renames come out at 1. ponytail: regex on patch lines, no parser; comments and strings count"""
    added = (l for f in files if f["filename"].endswith(CODE) for l in f.get("patch", "").splitlines() if l.startswith("+"))
    return 1 + sum(len(BRANCH.findall(l)) for l in added)


# [impl->req~nerd-records~2]
IDENT = re.compile(r"\b[A-Za-z_$][A-Za-z0-9_$]{15,}\b")
METHOD = re.compile(r"^\+(\s*)(?:(?:public|private|protected|static|final|abstract|synchronized|default)\s+)+[\w.<>\[\],?\s]+?\s(\w+)\s*\([^;]*\)\s*(?:throws [\w., ]+)?\{\s*$")


def methods(patch):
    """(name, lines) of the methods opened in a patch's added lines. ponytail: brace at the signature's own
    indentation ends the method, no parser; one whose closing brace is outside the hunk is skipped."""
    lines = [l for l in patch.splitlines() if l[:1] in "+ "]  # removed lines are not part of the new file
    for i, l in enumerate(lines):
        m = l.startswith("+") and METHOD.match(l)
        if not m:
            continue
        for j in range(i + 1, len(lines)):
            if lines[j][1:] == m.group(1) + "}":
                yield m.group(2), j - i + 1
                break


def superlatives(files):
    """Records worth bragging about, mined from a PR's added lines: longest identifier, longest and shortest
    method, fattest changelog entry."""
    out = {}
    added = [l[1:] for f in files if f["filename"].endswith(CODE) for l in f.get("patch", "").splitlines() if l.startswith("+")]
    names = [i for l in added for i in IDENT.findall(l)]
    if names:
        out["identifier"] = max(names, key=len)
    found = [m for f in files if f["filename"].endswith(".java") for m in methods(f.get("patch", ""))]
    if found:
        out["longest_method"] = max(found, key=lambda m: m[1])
        out["shortest_method"] = min(found, key=lambda m: m[1])
    entries = [l[1:].strip().lstrip("-*").strip() for f in files if f["filename"].endswith("CHANGELOG.md")
               for l in f.get("patch", "").splitlines() if l.startswith("+") and l[1:].lstrip()[:1] in "-*"]
    if entries:
        out["changelog"] = max(entries, key=len)
    return out


def sup(s, key):
    return (s.get("sup") or {}).get(key)


# (title, what makes a winner - None if the PR does not qualify -, how to phrase it). Biggest wins, so the
# shortest method competes on a negated line count.
RECORD_KINDS = [
    ("Longest identifier", lambda s: len(sup(s, "identifier") or "") or None, lambda s: f"{sup(s, 'identifier')} ({len(sup(s, 'identifier'))} chars)", "\U0001f4cf"),
    ("Longest method", lambda s: (sup(s, "longest_method") or [0, 0])[1] or None, lambda s: f"{sup(s, 'longest_method')[0]}(), {sup(s, 'longest_method')[1]} lines", "\U0001f40d"),
    ("Shortest method", lambda s: -(sup(s, "shortest_method") or [0, 0])[1] or None, lambda s: f"{sup(s, 'shortest_method')[0]}(), {sup(s, 'shortest_method')[1]} lines", "\U0001f90f"),
    ("Most code written", lambda s: s.get("additions") or None, lambda s: f"+{s['additions']:,} lines", "\u270d\ufe0f"),
    ("Most code deleted", lambda s: s.get("deletions") or None, lambda s: f"\u2212{s['deletions']:,} lines", "\U0001f525"),
    ("Most tangled diff", lambda s: s.get("complexity") or None, lambda s: f"complexity {s['complexity']}", "\U0001f35d"),
    ("Wordiest changelog entry", lambda s: len(sup(s, "changelog") or "") or None, lambda s: f"{sup(s, 'changelog')[:40]} ({len(sup(s, 'changelog'))} chars)", "\U0001f4dc"),
]


def records(cards, exclude=()):
    """One record holder per category, across every PR that has stats. The excluded authors do not hold records - the
    board's own maintainer asked to be left out of the record bonus, so the runner-up collects it."""
    out = []
    for title, size, text, emoji in RECORD_KINDS:
        ranked = [(size(c["stats"]), c) for c in cards
                  if c.get("stats") and size(c["stats"]) is not None and c["author"] not in exclude]
        if ranked:
            c = max(ranked, key=lambda p: p[0])[1]
            out.append({"title": title, "text": text(c["stats"]), "emoji": emoji, "repo": c["repo"],
                        "number": c["number"], "author": c["author"], "url": c["url"]})
    return out


def review_points(cc):
    """Review of a trivial diff 1, complex diff 3, else (or unknown PR) 2."""
    return 2 if cc is None else 1 if cc <= 2 else 3 if cc >= 20 else 2


STATS_VERSION = 2


def pr_stats(c, cached):
    if c["id"] in cached and cached[c["id"]].get("stats_version") == STATS_VERSION and "ai" in cached[c["id"]] and "complexity" in cached[c["id"]] and "sup" in cached[c["id"]]:
        return cached[c["id"]]
    if c["column"] != "done":  # open PR under review: only its complexity, refetched when the PR changes
        if cached.get(c["id"], {}).get("updated_at") == c["updated_at"]:
            return cached[c["id"]]
        files = get_all(f"/repos/{c['repo']}/pulls/{c['number']}/files")
        return {"complexity": complexity(files), "updated_at": c["updated_at"]}
    pr, _ = get(f"/repos/{c['repo']}/pulls/{c['number']}")
    files = get_all(f"/repos/{c['repo']}/pulls/{c['number']}/files")
    commits = get_all(f"/repos/{c['repo']}/pulls/{c['number']}/commits")
    comps = {}
    for f in files:
        comps[component(c["repo"], f["filename"])] = comps.get(component(c["repo"], f["filename"]), 0) + f["changes"]
    return {"stats_version": STATS_VERSION, "additions": pr["additions"], "deletions": pr["deletions"], "changed_files": pr["changed_files"], "components": comps, "complexity": complexity(files),
            "refactorings": refactorings(pr, files, c["repo"]), "sup": superlatives(files),
            "ai": ai_models(cm["commit"]["message"] for cm in commits)}


def configured_nerd_prs():
    """Refactorings from explicitly linked upstream PRs that are not participant cards, such as bot PRs."""
    out = []
    for ref in CONFIG.get("nerd_prs", []):
        repo, number = ref.rsplit("#", 1)
        pr, _ = get(f"/repos/{repo}/pulls/{number}")
        files = get_all(f"/repos/{repo}/pulls/{number}/files")
        for weight, text in refactorings(pr, files, repo):
            out.append({"weight": weight, "text": text, "repo": repo, "number": int(number),
                        "author": pr["user"]["login"], "url": pr["html_url"]})
    return out


AI_FACTOR = 0.25  # writing it without an assistant is the harder craft, for now

# [impl->req~scoring~9]
def leaderboard(cards, events, private):
    """Merged PR 3, review 1..3 by the complexity of the reviewed diff, other (comment, issue, push, PR opened / closed unmerged) 1; tenfold on a JabCon item (focus label / milestone), times the configured
    repo_factors elsewhere (keys are repos or whole orgs, e.g. the JabRef org and upstream JavaFX work); a quarter of
    that for a merged PR whose commits credit an AI assistant."""
    score = {p: {"merged": 0, "reviews": 0, "other": 0, "milestone": 0, "boosted": 0, "ai": 0, "points": 0} for p in PARTICIPANTS}
    jabcon = {(c["repo"], c["number"]) for c in cards if c["focus"]}
    cc = {(c["repo"], c["number"]): c.get("stats", {}).get("complexity") for c in cards if c["type"] == "pr"}
    repo_factors = CONFIG.get("repo_factors", {})

    def factor(s, repo, number):
        f = 10 if (repo, number) in jabcon else repo_factors.get(repo) or repo_factors.get(repo.split("/")[0], 1)
        s["milestone"] += f == 10
        s["boosted"] += f != 10 and f != 1
        return f

    for counts in private.values():
        for p, n in counts["by"].items():
            score[p]["other"] += n
            score[p]["points"] += n
    for c in cards:
        if c["column"] == "done" and c["type"] == "pr" and c["author"] in score:
            s = score[c["author"]]
            s["merged"] += 1
            ai = bool(c.get("stats", {}).get("ai"))
            s["ai"] += ai
            s["points"] += 3 * factor(s, c["repo"], c["number"]) * (AI_FACTOR if ai else 1)
    for e in events:
        s = score.get(e["actor"])
        if s is None:
            continue
        if e.get("self") or e.get("sync") or e.get("ai"):
            continue
        if e["type"] == "PullRequestReviewEvent":
            s["reviews"] += 1
        elif e["type"] in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "PushEvent", "MailEvent") \
                or (e["type"] == "IssuesEvent" and e.get("action") not in ("labeled", "unlabeled")) \
                or (e["type"] == "PullRequestEvent" and (e.get("action") == "opened"
                                                        or (e.get("action") == "closed" and not e.get("merged")))):
            s["other"] += 1
        else:
            continue
        base = review_points(cc.get((e["repo"], e.get("number")))) if e["type"] == "PullRequestReviewEvent" else 1
        s["points"] += base * factor(s, e["repo"], e.get("number"))
    return [{"login": p, **v, "points": round(v["points"])} for p, v in score.items()]


# The second evaluation, like the bonus round in a game: +100 for each superlative the per-event points barely notice
# (breadth, chattiness, night shifts). Everybody tied for a category gets it.
# [impl->req~bonus-points~19]
BONUS = 100
REVIEW_FLOOR = 10  # fewer reviews than this and the review ratios say nothing
EVENT_FLOOR = 5  # same for the other ratios: one event out of two must not win a share
MERGED_FLOOR = 3  # one hand-written PR is not a habit
STRICT_FLOOR = 3  # a single "changes requested" is not a temperament
SMALL, MEDIUM = 50, 500  # changed lines; above that a PR is large
THANKS = re.compile(r"\bth(?:ank|x)", re.I)


def now_utc():
    return datetime.now(timezone.utc)


def search_url(query, sort=None, order=None):
    """Where a bonus comes from, as a GitHub issue search everybody can click."""
    q = {"q": query, "type": "issues", **({"s": sort, "o": order} if sort else {})}
    return "https://github.com/search?" + urllib.parse.urlencode(q)

# the repos JabRef builds on (config): a fix there ships to everybody, not just to JabRef
DEPENDENCIES = {r.lower() for r in CONFIG.get("dependency_repos", [])}
DEP_NAMES = {r.split("/")[1] for r in DEPENDENCIES}  # a fork of a dependency (Someone/jfx) is dependency work too
# (title, tally key, how to phrase the number, emoji)
BONUS_KINDS = [
    ("Chatterbox", "comments", "{} comments", "\U0001f4ac", f"org:{CONFIG['org']} commenter:{{}} updated:>={START_DATE}"),
    ("Busy bee", "touched", "touched {} PRs and issues", "\U0001f41d", f"involves:{{}} updated:>={START_DATE}"),
    ("Globetrotter", "repos", "worked on {} repositories", "\U0001f30d", None),
    ("Idea machine", "opened", "opened {} PRs", "\U0001f4a1", f"is:pr author:{{}} created:>={START_DATE}"),
    ("Gatekeeper", "reviews", "{} reviews", "\U0001f6e1\ufe0f", f"reviewed-by:{{}} updated:>={START_DATE}"),
    ("Closer", "merged", "{} merged PRs", "\U0001f3c1", f"is:pr author:{{}} is:merged merged:>={START_DATE}"),
    ("Night owl", "night", "{} events between 22:00 and 06:00", "\U0001f989", None),
    ("Early bird", "early", "{} events before 08:00", "\U0001f426", None),
    # upstream work is where the org's fixes land in somebody else's release
    ("Ambassador", "upstream", "{} events outside the " + CONFIG["org"] + " org", "\u2615", f"-org:{CONFIG['org']} involves:{{}} updated:>={START_DATE}"),
    ("Dependency whisperer", "dependency", "{} events in JabRef's dependencies", "\U0001f527", None),
    ("Jack of all trades", "diverse", "touched {} components, writing or reviewing", "\U0001f3a8", None),
    ("Component collector", "labelled", "{} \"component:\" labels written or reviewed", "\U0001f3f7\ufe0f", None),
    ("Reviewer's reviewer", "reviewshare", "{}% of everything they did was reviewing", "\U0001f50d", None),
    ("Actions over words", "terse", "{} reviews per comment written", "\U0001f910", None),
    ("Rubber stamp", "approvals", "{} approvals given", "\u2705", None),
    ("Janitor", "deleted", "{} branches cleaned up", "\U0001f9f9", None),
    ("Widest reach", "reach", "reviewed the PRs of {} different authors", "\U0001f91d", None),
    ("Socratic", "questions", "{} questions asked", "\u2753", None),
    ("Most gracious", "thanks", "said thank you {} times", "\U0001f64f", None),
    ("Always on", "hours", "active in {} of the 24 hours", "\U0001f570\ufe0f", None),
    ("Magnet", "magnet", "their PRs pulled {} reviews", "\U0001f9f2", None),
    ("First responder", "first", "first to review {} PRs", "\u26a1", None),
    ("All killer, no filler", "shipshare", "{}% of everything they did was landing a PR", "\U0001f680", None),
    ("Essayist", "essay", "{} characters per comment on average", "\U0001f4dd", None),
    ("Freight train", "freight", "{} commits per push", "\U0001f69a", None),
    ("Weekend warrior", "weekend", "{}% of their activity on a weekend", "\U0001f3d6\ufe0f", None),
    ("Reporter", "reported", "{} issues opened", "\U0001f41b", f"is:issue author:{{}} created:>={START_DATE}"),
    ("Handmade", "handmade", "{}% of their merged PRs written without an assistant", "\u270b", None),
    ("Hard to please", "strict", "{}% of their reviews asked for changes", "\U0001f6a7", None),
    ("Big picture", "issuey", "{}% of their activity went into issues, not code", "\U0001f52d", None),
    ("Featherweight", "small", "{} merged PRs of at most 50 changed lines", "\U0001fab6", None),
    ("Middleweight", "medium", "{} merged PRs between 50 and 500 changed lines", "\u2696\ufe0f", None),
    ("Heavyweight", "large", "{} merged PRs above 500 changed lines", "\U0001f418", None),
    ("Force of nature", "forced", "{} force pushes", "\U0001f4a5", None),
    ("Sounding board", "talky", "{}% of everything they did was talking it through", "\U0001f5e3\ufe0f", None),
    ("Exotic explorer", "exotic", "{} strange repositories nobody else touched", "\U0001f6f8", None),
]


# [impl->req~bonus-points~19]
def first_seen(previous):
    """Each participant's first issue or PR in the org. A fixed date, so it is reused from the previous data.json."""
    out = {p: previous[p] for p in PARTICIPANTS if p in (previous or {})}
    for p in PARTICIPANTS:
        if p in out:
            continue
        found, _ = get("/search/issues", {"q": f"org:{CONFIG['org']} author:{p}", "sort": "created", "order": "asc", "per_page": 1})
        out[p] = (found.get("items") or [{}])[0].get("created_at")
    return out


# [impl->req~bonus-points~19]
def bonuses(cards, events, joined=None):
    """One +100 award per category, shared by everyone tied for the top. Same events the leaderboard counts."""
    tally = {p: dict.fromkeys((k for _, k, *_ in BONUS_KINDS), 0) for p in PARTICIPANTS}
    logins = {p.lower() for p in PARTICIPANTS}
    touched = {p: set() for p in PARTICIPANTS}
    repos = {p: set() for p in PARTICIPANTS}
    exotic = {p: set() for p in PARTICIPANTS}
    comps = {p: set() for p in PARTICIPANTS}  # components written or reviewed: the breadth of the code itself
    labelled = {p: set() for p in PARTICIPANTS}  # the same breadth as the maintainers see it, in "component:" labels
    by_pr = {(c["repo"], c["number"]): set(c.get("stats", {}).get("components") or ()) for c in cards}
    labels_of = {(c["repo"], c["number"]): {l for l in c.get("labels") or () if l.startswith("component:")} for c in cards}
    hours = {p: set() for p in PARTICIPANTS}
    requested = {p: 0 for p in PARTICIPANTS}  # reviews that asked for changes
    issues = {(c["repo"], c["number"]) for c in cards if c["type"] == "issue"}
    on_issues = {p: 0 for p in PARTICIPANTS}  # shaping the work rather than writing it
    reach = {p: set() for p in PARTICIPANTS}  # the PR authors whose work they reviewed
    reviews_of = {}  # (repo, number) -> (first review's time, its author), for the first responder award
    scored = []  # the events that counted, for the tallies computed after the loop
    handmade = {p: [0, 0] for p in PARTICIPANTS}  # merged PRs, of them written without an assistant
    for c in cards:
        if c["column"] == "done" and c["type"] == "pr" and c["author"] in tally:
            tally[c["author"]]["merged"] += 1
            handmade[c["author"]][0] += 1
            handmade[c["author"]][1] += not (c.get("stats") or {}).get("ai")
            st = c.get("stats") or {}
            changed = st.get("additions", 0) + st.get("deletions", 0)
            if st:  # the same small / medium / large the "size:" labels talk about, but measured on every PR
                tally[c["author"]]["small" if changed <= SMALL else "medium" if changed <= MEDIUM else "large"] += 1
        if c["author"] in comps:
            comps[c["author"]] |= by_pr[(c["repo"], c["number"])]
            labelled[c["author"]] |= labels_of[(c["repo"], c["number"])]
    for e in events:
        t = tally.get(e["actor"])
        if t is None or e.get("self") or e.get("sync") or e.get("ai"):
            continue
        repos[e["actor"]].add(e["repo"])
        owner, name = e["repo"].lower().split("/")
        # a repo owned by a participant is their own fork, not a foreign codebase - unless it forks a dependency
        if owner != CONFIG["org"].lower() and (owner not in logins or name in DEP_NAMES):
            t["upstream"] += 1
            if e["repo"].lower() in DEPENDENCIES or name in DEP_NAMES:
                t["dependency"] += 1
            else:
                exotic[e["actor"]].add(e["repo"])
        if e.get("number"):
            touched[e["actor"]].add((e["repo"], e["number"]))
        hour = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).astimezone(START.tzinfo).hour
        t["night"] += hour >= 22 or hour < 6
        t["early"] += 6 <= hour < 8
        hours[e["actor"]].add(hour)
        on_issues[e["actor"]] += e["type"] == "IssuesEvent" or (e["repo"], e.get("number")) in issues
        scored.append(e)
        t["deleted"] += e["type"] == "DeleteEvent"
        t["forced"] += bool(e.get("forced"))
        # only the first line of a comment survives in the excerpt, so these two read what is visible on the board
        excerpt_ = e.get("excerpt") or ""
        if e["type"] in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "PullRequestReviewEvent"):
            t["questions"] += "?" in excerpt_
            t["thanks"] += bool(THANKS.search(excerpt_))
        if e["type"] in ("IssueCommentEvent", "PullRequestReviewCommentEvent"):
            t["comments"] += 1
        elif e["type"] == "PullRequestReviewEvent":
            t["reviews"] += 1
            t["approvals"] += "(approved)" in (e.get("summary") or "")
            requested[e["actor"]] += "changes_requested" in (e.get("summary") or "")
            author = PR_AUTHORS.get(f"{e['repo']}#{e.get('number')}")
            if author:
                reach[e["actor"]].add(author)
                if author in tally:
                    tally[author]["magnet"] += 1  # a review someone else gave to their PR
            key = (e["repo"], e.get("number"))
            if e["created_at"] < reviews_of.get(key, ("9",))[0]:
                reviews_of[key] = (e["created_at"], e["actor"])
            comps[e["actor"]] |= by_pr.get((e["repo"], e.get("number")), set())
            labelled[e["actor"]] |= labels_of.get((e["repo"], e.get("number")), set())
        elif e["type"] == "PullRequestEvent" and e.get("action") == "opened":
            t["opened"] += 1
        elif e["type"] == "IssuesEvent" and e.get("action") == "opened":
            t["reported"] += 1
    for p, t in tally.items():
        t["touched"], t["repos"], t["exotic"] = len(touched[p]), len(repos[p]), len(exotic[p])
        t["diverse"], t["labelled"] = len(comps[p]), len(labelled[p])
        t["hours"], t["reach"] = len(hours[p]), len(reach[p])
        mine = [e for e in scored if e["actor"] == p]
        # ratios need a body of work behind them, or one review out of two events wins the category
        if t["reviews"] >= REVIEW_FLOOR:
            t["reviewshare"] = round(100 * t["reviews"] / len(mine))
            t["terse"] = round(t["reviews"] / max(1, t["comments"]), 2)
        if len(mine) >= EVENT_FLOOR:
            t["shipshare"] = round(100 * t["merged"] / len(mine))
            t["issuey"] = round(100 * on_issues[p] / len(mine))
            t["talky"] = round(100 * t["comments"] / len(mine))
            weekend = sum(datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).weekday() >= 5 for e in mine)
            t["weekend"] = round(100 * weekend / len(mine))
        said = [e.get("excerpt") or "" for e in mine if e["type"] in ("IssueCommentEvent", "PullRequestReviewCommentEvent")]
        if len(said) >= EVENT_FLOOR:  # the excerpt is capped, so this measures who fills the first line, not essays
            t["essay"] = round(sum(len(x) for x in said) / len(said))
        if t["reviews"] >= STRICT_FLOOR:
            t["strict"] = round(100 * requested[p] / t["reviews"])
        merged, by_hand = handmade[p]
        if merged >= MERGED_FLOOR:
            t["handmade"] = round(100 * by_hand / merged)
        pushes = [e.get("commits") or 0 for e in mine if e["type"] == "PushEvent"]
        if len(pushes) >= EVENT_FLOOR:
            t["freight"] = round(sum(pushes) / len(pushes), 1)
    for _, (_, actor) in reviews_of.items():
        if actor in tally:
            tally[actor]["first"] += 1
    # awards the data cannot see (config): the jury's own +100
    out = [{**a, "points": BONUS} for a in CONFIG.get("honorary_awards", []) if a["login"] in tally]
    # every nerd corner record pays, minus the authors who asked to be left out (the runner-up then holds it)
    out += [{"login": r["author"], "title": r["title"], "text": r["text"], "emoji": r["emoji"], "points": BONUS,
             "url": r["url"]}
            for r in records(cards, exclude=CONFIG.get("record_bonus_exclude", [])) if r["author"] in tally]
    # the shortest way from "opened" to "merged"
    fast = [(datetime.fromisoformat(c["merged_at"].replace("Z", "+00:00"))
             - datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")), c)
            for c in cards if c.get("merged_at") and c.get("created_at") and c["author"] in tally]
    if fast:
        quickest = min(fast)[0]
        for delta, c in fast:
            if delta == quickest:
                mins = round(delta.total_seconds() / 60)
                when = f"{mins} minutes" if mins < 120 else f"{round(mins / 60)} hours"
                out.append({"login": c["author"], "title": "Speedrun", "emoji": "\U0001f3ce\ufe0f",
                            "text": f"{c['repo'].split('/')[-1]}#{c['number']} merged {when} after opening",
                            "points": BONUS, "url": c["url"]})
    # necromancy: bringing the oldest sleeping item back into the conversation
    born = {(c["repo"], c["number"]): c for c in cards if c.get("created_at")}
    woke = {}
    for e in scored:
        c = born.get((e["repo"], e.get("number")))
        if c and c["author"] != e["actor"] and c["created_at"] < woke.get(e["actor"], {"created_at": "9"})["created_at"]:
            woke[e["actor"]] = c
    if woke:
        oldest = min(c["created_at"] for c in woke.values())
        for p, c in woke.items():
            if c["created_at"] == oldest:
                days = (now_utc() - datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))).days
                out.append({"login": p, "title": "Necromancer", "emoji": "\U0001f9df",
                            "text": f"woke {c['repo'].split('/')[-1]}#{c['number']}, {days} days old",
                            "points": BONUS, "url": c["url"]})
    # the newest face in the org: whoever's first issue or PR here is the most recent
    dated = {p: d for p, d in (joined or {}).items() if d and p in tally}
    if dated:
        newest = max(dated.values())
        out += [{"login": p, "title": "Newcomer", "text": f"first {CONFIG['org']} contribution {newest[:10]}",
                 "emoji": "\U0001f423", "points": BONUS,
                 "url": search_url(f"org:{CONFIG['org']} author:{p}", sort="created", order="asc")}
                for p, d in dated.items() if d == newest]
    for title, key, phrase, emoji, query in BONUS_KINDS:
        best = max((t[key] for t in tally.values()), default=0)
        out += [{"login": p, "title": title, "text": phrase.format(best), "emoji": emoji, "points": BONUS,
                 "url": search_url(query.format(p)) if query else None}
                for p, t in tally.items() if best and t[key] == best]
    return out


# [impl->req~milestones~2]
# [impl->req~sticker-since~1]
def stamp(awards, previous, now):
    """Each award keeps the time it was first seen (from the previous data.json), a new one gets this run's time."""
    # an award from before the stamps existed is old, not new: it dates from the start rather than from this run
    held = {(b["login"], b["title"]): b.get("since") or START.isoformat(timespec="seconds") for l in (previous or {}).get("leaderboard", []) for b in l.get("bonuses", [])}
    for b in awards:
        b["since"] = held.get((b["login"], b["title"])) or now.isoformat(timespec="seconds")
    return awards


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


# [impl->req~private-counts-only~1]
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


# [impl->req~jabcon-window~1]
def main():
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else "data.json"
    now = datetime.now(timezone.utc)
    if "--force" not in args and not (START <= now <= END):
        print(f"outside JabCon window ({START} .. {END}), nothing to do")
        return
    cached, previous_milestones, previous_events, previous_joined, previous = {}, [], [], {}, None
    if os.path.exists(out):
        try:
            previous = json.load(open(out))
            cached = {c["id"]: c["stats"] for c in previous["cards"] if c.get("stats")}
            previous_milestones = previous.get("milestones", [])
            previous_events = previous.get("all_events", [])
            PR_AUTHORS.update(previous.get("pr_authors", {}))
            previous_joined = previous.get("first_seen", {})
        except (ValueError, KeyError):
            pass
    ms = milestones(previous_milestones)
    cards = collect_cards(ms)
    # the archive export always covers the whole window, so stored mail events are replaced rather than kept
    events = collect_events([e for e in previous_events if e["type"] != "MailEvent"]) + mail_events()
    events.sort(key=lambda e: e["created_at"], reverse=True)
    for c in cards:
        if c["type"] == "pr" and c["column"] != "backlog":
            c["stats"] = pr_stats(c, cached)
    totals = {"additions": 0, "deletions": 0, "changed_files": 0, "components": {}}
    for c in cards:
        for k in ("additions", "deletions", "changed_files"):
            totals[k] += c.get("stats", {}).get(k, 0)
        for comp, n in c.get("stats", {}).get("components", {}).items():
            totals["components"][comp] = totals["components"].get(comp, 0) + n
    private = private_activity()
    nerdy = [{"weight": w, "text": t, "repo": c["repo"], "number": c["number"], "author": c["author"], "url": c["url"]}
             for c in cards for w, t in c.get("stats", {}).get("refactorings", [])]
    known = {(r["repo"], r["number"]) for r in nerdy}
    nerdy += [r for r in configured_nerd_prs() if (r["repo"], r["number"]) not in known]
    nerdy = sorted(nerdy, key=lambda r: -r["weight"])[:5]
    ai_used = {}
    for c in cards:
        for m in c.get("stats", {}).get("ai", []):
            ai_used[m] = ai_used.get(m, 0) + 1
    joined = first_seen(previous_joined)
    board = leaderboard(cards, events, private)
    by_login = {l["login"]: l for l in board}
    for b in stamp(bonuses(cards, events, joined), previous, now):
        l = by_login[b["login"]]
        l["points"] += b["points"]
        l.setdefault("bonuses", []).append(b)
    data = {
        "refactorings": nerdy,
        "records": records(cards),
        "ai_models": dict(sorted(ai_used.items(), key=lambda kv: -kv[1])),
        "milestones": ms,
        "focus": focus_progress(),
        "private_activity": private,
        "generated_at": now.isoformat(timespec="seconds"),
        "config": CONFIG,
        "cards": cards,
        "events": events[:200],
        "all_events": events,
        "pr_authors": PR_AUTHORS,
        "first_seen": joined,
        "stats": totals,
        "leaderboard": sorted(board, key=lambda l: -l["points"]),
    }
    with open(out, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {out}: {len(cards)} cards, {len(events)} events")


if __name__ == "__main__":
    main()
