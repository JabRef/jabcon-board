#!/usr/bin/env python3
"""Self-check for the nerd corner records: python3 scripts/test_records.py"""
import collect
from collect import get_all, module_changes, refactorings, superlatives, records

module_patch = "@@ -1,2 +1,3 @@\n+    module(\"example\", \"example.module\")\n-    module(\"old\", \"old.module\")\n"
module_facts = refactorings({"additions": 1, "deletions": 1}, [{"filename": "build.gradle.kts", "status": "modified", "patch": module_patch}], "o/r")
assert module_facts == [(4, "module metadata changed (+1 / −1)")], module_facts

multiline = [
    {"filename": "build.gradle.kts", "status": "modified", "patch": "@@ -1,3 +1,4 @@\n module(\n-    \"old\",\n+    \"new\",\n     \"example.module\"\n )\n"},
    {"filename": "pom.xml", "status": "modified", "patch": "@@ -1,2 +1,3 @@\n-<module>old</module>\n+<module>\n+  new\n+</module>\n"},
    {"filename": "src/module-info.java", "status": "modified", "patch": "@@ -1,2 +1,2 @@\n-module old.name {\n+module new.name {\n"},
]
assert module_changes(multiline) == (3, 3), module_changes(multiline)

calls = []
def fake_get(path, params=None, token=None):
    calls.append(params["page"])
    return ([{"page": params["page"]}] if params["page"] < 3 else []), {}
original_get = collect.get
collect.get = fake_get
try:
    assert get_all("/items", {"per_page": 1}) == [{"page": 1}, {"page": 2}]
finally:
    collect.get = original_get
assert calls == [1, 2, 3], calls

patch = ("@@ -1 +1,9 @@\n"
         "+    public void anExtraordinarilyLongMethodName(int x) {\n"
         "+        if (x > 0) {\n"
         "+            System.out.println(x);\n"
         "+        }\n"
         "+    }\n"
         "+    private int two() {\n"
         "+    }\n"
         "-    private int gone() {\n")
sup = superlatives([{"filename": "src/A.java", "patch": patch},
                    {"filename": "CHANGELOG.md", "patch": "@@ -1 +1,2 @@\n+- We fixed a thing\n+not an entry\n"}])
assert sup["identifier"] == "anExtraordinarilyLongMethodName", sup
assert sup["longest_method"] == ("anExtraordinarilyLongMethodName", 5), sup
assert sup["shortest_method"] == ("two", 2), sup
assert sup["changelog"] == "We fixed a thing", sup
assert superlatives([{"filename": "README.md", "patch": "+short\n"}]) == {}

cards = [{"repo": "o/r", "number": 1, "author": "a", "url": "u", "stats": {"additions": 5, "deletions": 90, "complexity": 3, "sup": sup}},
         {"repo": "o/r", "number": 2, "author": "b", "url": "u", "stats": {"additions": 500, "deletions": 1, "complexity": 1, "sup": {}}},
         {"repo": "o/r", "number": 3}]
by_title = {r["title"]: r for r in records(cards)}
assert by_title["Most code written"]["number"] == 2
assert by_title["Most code deleted"]["number"] == 1
assert by_title["Shortest method"]["text"] == "two(), 2 lines", by_title
assert "Wordiest changelog entry" in by_title
assert records([{"stats": {}}]) == []
print("ok")
