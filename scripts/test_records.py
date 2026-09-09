#!/usr/bin/env python3
"""Self-check for the nerd corner records: python3 scripts/test_records.py"""
import collect
from collect import declarations, get_all, module_changes, pick_nerdy, refactorings, superlatives, records

module_patch = "@@ -1,2 +1,3 @@\n+    module(\"example\", \"example.module\")\n-    module(\"old\", \"old.module\")\n"
module_facts = refactorings({"additions": 1, "deletions": 1}, [{"filename": "build.gradle.kts", "status": "modified", "patch": module_patch}], "o/r")
assert module_facts == [(4, "module metadata changed (+1 / −1)")], module_facts

multiline = [
    {"filename": "build.gradle.kts", "status": "modified", "patch": "@@ -1,3 +1,4 @@\n module(\n-    \"old\",\n+    \"new\",\n     \"example.module\"\n )\n"},
    {"filename": "pom.xml", "status": "modified", "patch": "@@ -1,2 +1,3 @@\n-<module>old</module>\n+<module>\n+  new\n+</module>\n"},
    {"filename": "src/module-info.java", "status": "modified", "patch": "@@ -1,2 +1,2 @@\n-module old.name {\n+module new.name {\n"},
]
assert module_changes(multiline) == (3, 3), module_changes(multiline)
assert declarations("open module example.module { }", "src/module-info.java") == ["open module example.module {"]
assert declarations("<modules><module>core</module></modules><!-- <module>fake</module> -->", "pom.xml") == ["<module>core</module>"]
assert declarations('module("example", "https://example.test/path") // module("fake")', "build.gradle.kts")

split_files = [{"filename": "build.gradle.kts", "status": "modified", "patch": "@@ -20,3 +20,3 @@\n-    \"old\",\n+    \"new\",\n"}]
old_source = "module(\n    \"old\",\n    \"example.module\"\n)\n"
new_source = "module(\n    \"new\",\n    \"example.module\"\n)\n"
original_source_at = collect.source_at
collect.source_at = lambda repo, path, ref: old_source if ref == "base" else new_source
try:
    assert module_changes(split_files, "o/r", "base", "head") == (1, 1)
finally:
    collect.source_at = original_source_at

renamed = [{"filename": "build.gradle.kts", "previous_filename": "old/pom.xml", "status": "renamed"}]
collect.source_at = lambda repo, path, ref: (
    "<module>old</module>" if path == "old/pom.xml" else 'module("new", "example.module")'
)
try:
    assert module_changes(renamed, "o/r", "base", "head") == (1, 1)
finally:
    collect.source_at = original_source_at

assert declarations('''
// module("fake")
val sample = "module(\\"fake\\")"
val text = """
module("fake")
"""
''', "build.gradle.kts") == []
assert declarations('module("example", "example.module")', "build.gradle.kts")

calls = []
def fake_get(path, params=None, token=None):
    calls.append(params["page"])
    return ([{"page": params["page"]}] if params["page"] <= 100 else []), {}
original_get = collect.get
collect.get = fake_get
try:
    assert len(get_all("/items", {"per_page": 1})) == 100
finally:
    collect.get = original_get
assert calls[-1] == 101, calls[-3:]

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

# [impl->req~nerd-variety~1] the corner never repeats a fact, and no one contributor fills it
facts = [{"weight": w, "text": t, "author": a} for w, t, a in
         [(9, "deleted A", "x"), (8, "deleted B", "x"), (7, "deleted C", "x"), (6, "virtual threads", "y"),
          (5, "virtual threads", "z"), (4, "records", "z")]]
picked = pick_nerdy(facts)
assert [r["text"] for r in picked] == ["deleted A", "deleted B", "virtual threads", "records"], picked
