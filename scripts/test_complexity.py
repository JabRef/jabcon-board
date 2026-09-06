#!/usr/bin/env python3
"""Self-check for the diff complexity: python3 scripts/test_complexity.py"""
from collect import complexity, review_points

java = {"filename": "a/B.java", "patch": "@@ -1 +1,3 @@\n+if (a && b) {\n-for (;;) {}\n+  for (X x : xs) { }\n+}"}
assert complexity([java]) == 4, complexity([java])  # if, &&, for; the removed line does not count
assert complexity([{"filename": "README.md", "patch": "+if this or that"}]) == 1
assert complexity([{"filename": "a/B.java", "status": "renamed"}]) == 1  # no patch
assert [review_points(c) for c in (None, 1, 2, 3, 19, 20)] == [2, 1, 1, 2, 2, 3]
print("ok")
