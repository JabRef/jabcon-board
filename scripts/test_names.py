#!/usr/bin/env python3
"""Self-check: no script reads a global that nothing defines (a NameError waiting for the one code path that runs it,
as `LEAD` was in highlights.py). Run: python3 scripts/test_names.py"""
import ast
import builtins
import pathlib

for path in sorted(pathlib.Path(__file__).parent.glob("*.py")):
    tree = ast.parse(path.read_text())
    defined = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            defined.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    # ponytail: names only, no scope analysis — a global shadowed by a local elsewhere still counts as defined
    assert not used - defined, f"{path.name}: undefined {sorted(used - defined)}"
print("ok")
