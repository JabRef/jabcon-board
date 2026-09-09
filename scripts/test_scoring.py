#!/usr/bin/env python3
"""Self-check for the leaderboard scoring: python3 scripts/test_scoring.py"""
import collect

collect.PARTICIPANTS = ["a"]
events = [{"actor": "a", "type": "IssuesEvent", "action": action, "repo": "x/y", "number": 1}
          for action in ("labeled", "unlabeled", "opened", "closed")]
assert collect.leaderboard([], events, {})[0]["points"] == 2, "only opened / closed score"
events = [{"actor": "a", "type": "MailEvent", "repo": "openjdk/jfx", "number": None}]
collect.CONFIG["repo_factors"] = {"openjdk/jfx": 6}
assert collect.leaderboard([], events, {})[0]["points"] == 6, "a mailing list post scores like a comment"
print("ok")

# bonus round: the top of each category gets +100, ties share it
collect.PARTICIPANTS = ["a", "b"]
cards = [{"column": "done", "type": "pr", "author": "a", "repo": "x/y", "number": 1}]
events = [{"actor": "a", "type": "IssueCommentEvent", "repo": "x/y", "number": 1, "created_at": "2026-09-05T23:30:00Z"},
          {"actor": "b", "type": "IssueCommentEvent", "repo": "x/z", "number": 2, "created_at": "2026-09-05T12:00:00Z"}]
got = {(b["login"], b["title"]) for b in collect.bonuses(cards, events)}
assert ("a", "Closer") in got and ("b", "Closer") not in got, got
assert ("a", "Chatterbox") in got and ("b", "Chatterbox") in got, "tied on comments"
# no award may rank a person by when they work or by how they wrote the code [impl->req~no-behaviour-profiling~1]
assert not [t for t, *_ in collect.BONUS_KINDS if t in ("Night owl", "Early bird", "Always on", "Weekend warrior", "Handmade")]
assert all(b["points"] == 100 for b in collect.bonuses(cards, events))
print("ok")

# AI-assisted merged PRs count a quarter
collect.PARTICIPANTS = ["a"]
pr = {"column": "done", "type": "pr", "author": "a", "repo": "x/y", "number": 1, "focus": False}
assert collect.leaderboard([pr], [], {})[0]["points"] == 3
assert collect.leaderboard([{**pr, "stats": {"ai": ["Claude Opus 5"]}}], [], {})[0]["points"] == 1  # 3 * 0.25, rounded
print("ok")

# newcomer: the most recent first contribution wins
collect.PARTICIPANTS = ["a", "b"]
joined = {"a": "2020-01-01T00:00:00Z", "b": "2026-08-30T00:00:00Z"}
got = [b for b in collect.bonuses([], [], joined) if b["title"] == "Newcomer"]
assert [b["login"] for b in got] == ["b"] and got[0]["text"].endswith("2026-08-30"), got
assert not [b for b in collect.bonuses([], [], {"a": None}) if b["title"] == "Newcomer"]
print("ok")

# a comment written by the assistant scores nothing and feeds no bonus
collect.PARTICIPANTS = ["a"]
ai = {"actor": "a", "type": "IssueCommentEvent", "repo": "x/y", "number": 1, "ai": True, "created_at": "2026-09-05T12:00:00Z"}
assert collect.leaderboard([], [ai], {})[0]["points"] == 0
assert not [b for b in collect.bonuses([], [ai]) if b["title"] == "Chatterbox"]
assert collect.AI_COMMENT.search("Nice, \U0001f916 generated") and collect.AI_COMMENT.search("thanks, Claude!")
assert not collect.AI_COMMENT.search("looks good to me")
print("ok")

# a sticker's "since" survives the next run; a new one gets the run's time
from datetime import datetime, timezone
old = {"leaderboard": [{"login": "a", "bonuses": [{"login": "a", "title": "Closer", "since": "2026-09-05T10:00:00+00:00"}]}]}
now = datetime(2026, 9, 8, tzinfo=timezone.utc)
got = collect.stamp([{"login": "a", "title": "Closer"}, {"login": "b", "title": "Closer"}], old, now)
assert [b["since"] for b in got] == ["2026-09-05T10:00:00+00:00", "2026-09-08T00:00:00+00:00"]
assert collect.stamp([{"login": "a", "title": "X"}], None, now)[0]["since"].startswith("2026-09-08")
unstamped = {"leaderboard": [{"login": "a", "bonuses": [{"login": "a", "title": "Closer"}]}]}
assert collect.stamp([{"login": "a", "title": "Closer"}], unstamped, now)[0]["since"] == collect.START.isoformat(timespec="seconds")
print("ok")

# necromancer: the oldest item somebody else opened, woken by an event
collect.PARTICIPANTS = ["a", "b"]
old = {"repo": "x/y", "number": 1, "type": "issue", "column": "backlog", "author": "z", "url": "u1",
       "created_at": "2015-01-01T00:00:00Z", "labels": []}
new = {**old, "number": 2, "url": "u2", "created_at": "2026-01-01T00:00:00Z"}
events = [{"actor": "a", "type": "IssueCommentEvent", "repo": "x/y", "number": 1, "created_at": "2026-09-05T12:00:00Z"},
          {"actor": "b", "type": "IssueCommentEvent", "repo": "x/y", "number": 2, "created_at": "2026-09-05T12:00:00Z"}]
got = [b for b in collect.bonuses([old, new], events) if b["title"] == "Necromancer"]
assert [b["login"] for b in got] == ["a"] and got[0]["url"] == "u1", got
assert "y#1" in got[0]["text"], got
# one's own old issue is not necromancy
assert not [b for b in collect.bonuses([{**old, "author": "a"}], events[:1]) if b["title"] == "Necromancer"]
print("ok")
