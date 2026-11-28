#!/usr/bin/env bash
# Sync this SmartRoom fork with its omacom upstream (CARRY.md, "Syncing").
#
#   smartroom/sync-upstream.sh          fast-forward the main mirror, show what smartroom/edge lacks
#   smartroom/sync-upstream.sh --merge  also merge upstream main into a local sync/upstream-<date>
#                                       branch made from smartroom/edge, to test and review
#
# main is an exact mirror of omacom's main: fast-forward only, never commit to it.
# smartroom/edge is our line (upstream plus the carry in CARRY.md). It takes
# upstream by a reviewed merge, never by a rebase or a force-push.
set -euo pipefail

repo=$(basename "$(git rev-parse --show-toplevel)")
upstream_url="https://github.com/omacom/$repo.git"
merge=0
for a in "$@"; do
  case $a in
    --merge) merge=1 ;;
    *) echo "usage: $0 [--merge]" >&2; exit 2 ;;
  esac
done

git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$upstream_url"
git fetch -q upstream main
git fetch -q origin main smartroom/edge

# 1. Fast-forward the mirror. Refuses anything but a fast-forward.
if git merge-base --is-ancestor origin/main upstream/main; then
  if [[ $(git rev-parse origin/main) != $(git rev-parse upstream/main) ]]; then
    git push origin upstream/main:refs/heads/main
    echo "main fast-forwarded to $(git rev-parse --short upstream/main)"
  else
    echo "main already at upstream $(git rev-parse --short upstream/main)"
  fi
else
  echo "main has diverged from omacom/$repo main; fix by hand (never force main)" >&2
  exit 1
fi

# 2. How far behind the line is, and what it carries.
behind=$(git rev-list --count origin/smartroom/edge..upstream/main)
carry=$(git rev-list --count --no-merges upstream/main..origin/smartroom/edge)
echo "smartroom/edge lacks $behind upstream commits and carries $carry of its own"
(( behind > 0 )) || exit 0
(( merge )) || { echo "run with --merge to try the merge on a local branch"; exit 0; }

# 3. A local branch to test; it reaches smartroom/edge only as a reviewed --no-ff merge.
branch="sync/upstream-$(date +%F)"
git switch -q -C "$branch" origin/smartroom/edge
if git merge --no-ff -q -m "Merge upstream omacom/$repo main $(git rev-parse --short upstream/main)" upstream/main; then
  echo "merged on $branch: run bin/test-ci.sh, then build a dev release before it goes to smartroom/edge"
else
  echo "conflicts on $branch: keep every SmartRoom hunk (CARRY.md lists them), then commit and test" >&2
  exit 1
fi
