#!/bin/sh
# gh-pages as a single commit: "prepare" checks the current content out into out/, "push" replaces the branch with one
# fresh commit of out/ (force-push), so the branch never accumulates stale data.json and video versions.
set -e
git config user.name github-actions
git config user.email github-actions@github.com
case "$1" in
  prepare)
    if git fetch -q origin gh-pages; then git worktree add -q out origin/gh-pages; else git worktree add -q --orphan -b gh-pages out; fi ;;
  push)
    cd out
    git add -A
    git rev-parse -q --verify origin/gh-pages >/dev/null && git diff --cached --quiet origin/gh-pages && exit 0
    git push -q --force origin "$(git commit-tree "$(git write-tree)" -m "Update board $(date -u +%FT%TZ)")":refs/heads/gh-pages ;;
  *) echo "usage: $0 prepare|push" >&2; exit 2 ;;
esac
