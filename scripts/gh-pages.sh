#!/bin/sh
# gh-pages as a single commit: "prepare" checks the current content out into out/, "push" replaces the branch with one
# fresh commit of out/ (force-push), so the branch never accumulates stale data.json and video versions.
# Workflows own disjoint files (Board: site + data.json, Highlights: highlights.mp4); when another workflow pushed in
# the meantime, its files are taken over and the push is retried.
set -e
git config user.name github-actions
git config user.email github-actions@github.com
case "$1" in
  prepare)
    if git fetch -q origin gh-pages; then git worktree add -q out origin/gh-pages; else git worktree add -q --orphan -b gh-pages out; fi ;;
  push)
    cd out
    base=$(git rev-parse -q --verify origin/gh-pages || true)
    for i in 1 2 3; do
      git add -A
      [ -n "$base" ] && git diff --cached --quiet "$base" && exit 0
      commit=$(git commit-tree "$(git write-tree)" -m "Update board $(date -u +%FT%TZ)")
      git push -q --force-with-lease="gh-pages:$base" origin "$commit:refs/heads/gh-pages" && exit 0
      git fetch -q origin gh-pages
      new=$(git rev-parse origin/gh-pages)
      [ -n "$base" ] && git diff --name-only "$base" "$new" | xargs -r git checkout -q "$new" --
      base=$new
    done
    exit 1 ;;
  *) echo "usage: $0 prepare|push" >&2; exit 2 ;;
esac
