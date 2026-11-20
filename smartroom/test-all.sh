#!/bin/bash
# Every SmartRoom-only test in this fork (not upstream's package suites, which
# are omarchy-mac-boot/test/all and the other <package>/test/all): the recipe
# checks, smartroom-boot-os and, on the edge line, aura-try.
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/.." && pwd)
fail=0
for t in "$here/pkgbuilds/omarchy-mac-boot/recipe-test.sh" \
         "$repo/smartroom-boot-os/test/all" \
         "$here/aura-try/test-all.sh"; do
  [[ -f $t ]] || continue
  echo "== ${t#"$repo"/}"
  bash "$t" || { echo "FAIL ${t#"$repo"/}"; fail=1; }
done
(( fail == 0 )) && echo "all SmartRoom tests passed"
exit $fail
