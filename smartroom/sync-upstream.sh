#!/usr/bin/env bash
# Sync this SmartRoom fork with its omacom upstream.
#
#   smartroom/sync-upstream.sh          check only: fast-forward main, show what smartroom/main lacks
#   smartroom/sync-upstream.sh --rebase also rebase smartroom/main onto the new main (local only)
#   smartroom/sync-upstream.sh --push   after --rebase: tag the old tip sr/prev-<date> and force-push
#
# main is an exact mirror of omacom's main: fast-forward only, never commit to it.
# smartroom/main is main + the carry listed in CARRY.md, rebased, never merged.
set -euo pipefail

repo=$(basename "$(git rev-parse --show-toplevel)")
upstream_url="https://github.com/omacom/$repo.git"
rebase=0 push=0
for a in "$@"; do
  case $a in
    --rebase) rebase=1 ;;
    --push) rebase=1 push=1 ;;
    *) echo "usage: $0 [--rebase|--push]" >&2; exit 2 ;;
  esac
done

git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$upstream_url"
git fetch -q upstream main
git fetch -q origin main smartroom/main

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

old_base=$(git merge-base origin/smartroom/main upstream/main)
behind=$(git rev-list --count "$old_base..upstream/main")
echo "smartroom/main is based on $(git rev-parse --short "$old_base"), $behind upstream commits behind"
echo "carry:"; git log --oneline "$old_base..origin/smartroom/main"
(( behind > 0 )) || exit 0
(( rebase )) || { echo "run with --rebase to rebase the carry"; exit 0; }

git switch -q -C smartroom/main origin/smartroom/main
git rebase --onto upstream/main "$old_base"
git range-diff "$old_base..origin/smartroom/main" "upstream/main..smartroom/main" || true
(( push )) || { echo "rebased locally; review the range-diff, then run with --push"; exit 0; }

tag="sr/prev-$(date +%F)"
git tag -f "$tag" origin/smartroom/main
git push origin "refs/tags/$tag"
git push --force-with-lease=smartroom/main:origin/smartroom/main origin smartroom/main
echo "pushed smartroom/main; old tip kept as $tag"
