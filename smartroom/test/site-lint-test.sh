#!/bin/bash
# Product files under smartroom/ must not carry one site's rooms, addresses
# or domains. Report-only until the cleanup lands. SITE_LINT_STRICT=1 fails
# on any hit. Patterns and allow-globs: .site-lint.json at the repo root.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../.." && pwd)
python3 "$here/site_lint.py" --self-test
( cd "$root" && python3 "$here/site_lint.py" )
echo "ok - site lint"
