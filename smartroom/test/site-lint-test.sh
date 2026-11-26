#!/bin/bash
# Product files must not carry one install's rooms, addresses or domains.
# The whole tree is scanned: the published tree is the whole tree.
# The install's patterns are not kept here: SITE_LINT_PATTERNS=<file> names
# them. Without it the lint prints one line and passes.
# Strict: any hit fails, with its file and line. SITE_LINT_STRICT=0 reports only.
# .site-lint.json at the repo root: roots and allow-globs (each with a reason), never patterns.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../.." && pwd)
lint=$here/site_lint.py
notice='site-lint: site patterns not given (SITE_LINT_PATTERNS is not set); nothing checked'
fail() { echo "not ok - $*" >&2; exit 1; }

python3 "$lint" --self-test

# This repo, with the caller's SITE_LINT_PATTERNS if one is set.
out=$(cd "$root" && env -u SITE_LINT_STRICT python3 "$lint") \
  || { printf '%s\n' "$out"; fail "site lint: hits remain"; }
printf '%s\n' "$out"
given=${SITE_LINT_PATTERNS:-}
if [[ -n ${given// /} ]]; then
  grep -qx 'site-lint: files=0 lines=0 strict=1' <<<"$out" || fail "site lint must run strict with no hits"
else
  [[ $out == "$notice" ]] || fail "without SITE_LINT_PATTERNS the lint must print one notice line"
fi
python3 - "$root/.site-lint.json" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
# The patterns are the install's own; an allowed path needs a reason, and a change here.
assert "patterns" not in cfg, "patterns belong to the install (SITE_LINT_PATTERNS)"
assert (cfg.get("allow") or []) == [], cfg.get("allow")
assert cfg.get("roots") == ["."], cfg.get("roots")
PY

# A planted hit: found with a pattern file, passed with the notice without one.
w=$(mktemp -d "${TMPDIR:-/tmp}/site-lint-XXXXXX")
trap 'rm -rf "$w"' EXIT
mkdir "$w/tree"
printf '%s\n' '{"roots": ["."], "allow": []}' >"$w/tree/.site-lint.json"
printf '%s\n' 'room-101 example.org' >"$w/tree/clean.txt"
printf '%s\n' 'ok' 'server at campus.example' >"$w/tree/planted.txt"
printf '%s\n' '{"ignoreCase": true, "patterns": [{"id": "planted-domain", "regex": "campus\\.example"}]}' >"$w/patterns.json"
code=0
out=$(cd "$w/tree" && env -u SITE_LINT_STRICT SITE_LINT_PATTERNS="$w/patterns.json" python3 "$lint" 2>/dev/null) || code=$?
[[ $code == 1 ]] || fail "a planted hit must fail strict mode, got $code"
grep -q 'hit planted.txt:2: planted-domain' <<<"$out" || fail "the planted hit must be named by file and line: $out"
grep -q 'campus\.example' <<<"$out" && fail "hits must not print the matched text"
out=$(cd "$w/tree" && env -u SITE_LINT_STRICT -u SITE_LINT_PATTERNS python3 "$lint") \
  || fail "without SITE_LINT_PATTERNS the lint must pass"
[[ $out == "$notice" ]] || fail "without SITE_LINT_PATTERNS want the notice, got: $out"
code=0
(cd "$w/tree" && SITE_LINT_PATTERNS="$w/missing.json" python3 "$lint" >/dev/null 2>&1) || code=$?
[[ $code != 0 ]] || fail "a missing pattern file must fail"

# --files: what a test uses on one file or its own output. Always strict; one skip line without patterns.
printf '%s\n' 'room-101' >"$w/out.txt"
code=0
out=$(SITE_LINT_STRICT=0 SITE_LINT_PATTERNS="$w/patterns.json" python3 "$lint" --files "$w/out.txt" "$w/tree/planted.txt" 2>/dev/null) || code=$?
[[ $code == 1 ]] || fail "--files must fail a hit even with SITE_LINT_STRICT=0, got $code"
grep -qF "hit $w/tree/planted.txt:2: planted-domain" <<<"$out" || fail "--files must name the hit by file and line: $out"
out=$(env -u SITE_LINT_PATTERNS python3 "$lint" --files "$w/tree/planted.txt") || fail "--files without SITE_LINT_PATTERNS must pass"
grep -q 'skipped$' <<<"$out" || fail "--files without SITE_LINT_PATTERNS must say it skipped: $out"
code=0
(env -u SITE_LINT_PATTERNS python3 "$lint" --files "$w/none.txt" >/dev/null 2>&1) || code=$?
[[ $code != 0 ]] || fail "--files must fail on a missing path"
echo "ok - site lint"
