#!/usr/bin/env python3
"""Self-check for the AI credit mining: python3 scripts/test_ai_models.py"""
from collect import ai_models

claude_code = """Fix the parser

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
🤖 Generated with [Claude Code](https://claude.com/claude-code)"""

assert ai_models([claude_code]) == ["Claude Opus 5"], ai_models([claude_code])
assert ai_models(["x\n\nCo-authored-by: Copilot <copilot@github.com>"]) == ["Copilot"]
assert ai_models([claude_code, "y\n\nCo-authored-by: Copilot <x@y>"]) == ["Claude Opus 5", "Copilot"]
assert ai_models(["Generated with [Claude Code](https://claude.com/claude-code)"]) == ["Claude Code"]
assert ai_models(["Rewrite the copilot integration docs"]) == []  # prose, not a trailer
print("ok")
