#!/bin/bash
# The omarchy-mac-boot recipe, offline: user4k.patch must apply to this tree's
# omarchy-mac-boot the way PKGBUILD's prepare() applies it (patch -Np2 in a
# copy), PKGBUILD must pin the patch's sha256, and the patched copy must still
# pass its own apple-grub-console test (what PKGBUILD's check() would run).
# A patch that stops applying is only seen at package build time otherwise.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../../.." && pwd)
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
fail() { echo "not ok - $*" >&2; exit 1; }

want=$(sed -n "s/^ *'\([0-9a-f]\{64\}\)')\$/\1/p" "$here/PKGBUILD" | head -n1)
got=$(sha256sum "$here/user4k.patch" | awk '{print $1}')
[[ -n $want && $want == "$got" ]] || fail "PKGBUILD pins user4k.patch as '$want' but the file is $got"
echo "ok - PKGBUILD pins the sha256 of user4k.patch"

cp -a "$repo/omarchy-mac-boot" "$t/boot"
patch -d "$t/boot" -Np2 <"$here/user4k.patch" >"$t/patch.out" 2>&1 \
  || fail "user4k.patch does not apply to omarchy-mac-boot as prepare() applies it: $(cat "$t/patch.out")"
! grep -q 'FAILED\|rejects' "$t/patch.out" || fail "user4k.patch left rejects: $(cat "$t/patch.out")"
echo "ok - user4k.patch applies to omarchy-mac-boot (patch -Np2), no hunk fails"

(cd "$t/boot/test" && bash apple-grub-console-test.sh >"$t/test.out" 2>&1) \
  || fail "the patched apple-grub-console-test.sh fails: $(tail -5 "$t/test.out")"
echo "ok - the patched apple-grub-console-test.sh passes"
