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
assert ("a", "Closer") in got and ("a", "Night owl") in got, got
assert ("a", "Chatterbox") in got and ("b", "Chatterbox") in got, "tied on comments"
assert ("b", "Night owl") not in got, got
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
