#!/bin/bash
# Product files must not carry one site's rooms, addresses or domains.
# The whole tree is scanned: the published tree is the whole tree.
# Strict: any hit fails, with its file and line. SITE_LINT_STRICT=0 reports only.
# Patterns and allow-globs (each with a reason): .site-lint.json at the repo root.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../.." && pwd)
python3 "$here/site_lint.py" --self-test
out=$(cd "$root" && env -u SITE_LINT_STRICT python3 "$here/site_lint.py") \
  || { printf '%s\n' "$out"; echo "not ok - site lint: hits remain" >&2; exit 1; }
printf '%s\n' "$out"
grep -q '^site-lint: files=0 lines=0 strict=1$' <<<"$out" \
  || { echo "not ok - site lint must run strict with no hits" >&2; exit 1; }
python3 - "$root/.site-lint.json" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
# An allowed path needs a reason, and a change here.
assert (cfg.get("allow") or []) == [], cfg.get("allow")
assert cfg.get("roots") == ["."], cfg.get("roots")
PY
echo "ok - site lint"
