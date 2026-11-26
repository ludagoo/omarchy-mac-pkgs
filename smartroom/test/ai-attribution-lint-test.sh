#!/usr/bin/env bash
# The AI-attribution lint passes the tree and catches a stray trailer or tool name.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$here/ai_attribution_lint.py"
python3 "$here/ai_attribution_lint.py" --self-test
echo "ok - AI attribution lint"
