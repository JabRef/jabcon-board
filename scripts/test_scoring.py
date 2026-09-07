#!/usr/bin/env python3
"""Self-check for the leaderboard scoring: python3 scripts/test_scoring.py"""
import collect

collect.PARTICIPANTS = ["a"]
events = [{"actor": "a", "type": "IssuesEvent", "action": action, "repo": "x/y", "number": 1}
          for action in ("labeled", "unlabeled", "opened", "closed")]
assert collect.leaderboard([], events, {})[0]["points"] == 2, "only opened / closed score"
print("ok")
