#!/bin/bash
# The network camera module: pinned upstream source, built for exactly the
# linux-aurora this repo builds (same release values, exact depends), with LLVM 18,
# and the rebuild-per-kernel step documented.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../.." && pwd)
recipe=$root/smartroom/pkgbuilds/v4l2loopback-aurora/PKGBUILD
kernel=$root/smartroom/pkgbuilds/linux-aurora/PKGBUILD
doc=$root/smartroom/docs/carried-packages.md
fail() { echo "FAIL v4l2loopback-aurora: $*" >&2; exit 1; }
[[ -f $recipe ]] || fail "no recipe at smartroom/pkgbuilds/v4l2loopback-aurora"

kernel_values=$(bash -c 'source "$1"; printf "%s %s %s\n" "$_auroraver" "$_aurorarel" "$pkgrel"' _ "$kernel")
module_values=$(bash -c 'source "$1"; printf "%s %s %s\n" "$_auroraver" "$_aurorarel" "$_aurorapkgrel"' _ "$recipe")
[[ $module_values == "$kernel_values" ]] ||
  fail "kernel values $module_values are not linux-aurora's $kernel_values: rebuild the module for the new kernel"

(
  # shellcheck disable=SC1090
  source "$recipe"
  [[ $pkgname == v4l2loopback-aurora ]] || fail "pkgname $pkgname"
  [[ $_v4l2ver =~ ^0\.15\.[0-9]+$ ]] || fail "upstream version $_v4l2ver is not a 0.15.x tag"
  [[ ${#source[@]} == 1 && ${source[0]} == *"github.com/v4l2loopback/v4l2loopback/archive/refs/tags/v${_v4l2ver}.tar.gz" ]] ||
    fail "source is not the upstream v${_v4l2ver} tag: ${source[*]}"
  [[ ${sha256sums[0]} =~ ^[0-9a-f]{64}$ ]] || fail "source is not pinned by sha256"
  [[ $_kernver == "${_auroraver}-${_aurorarel}-${_aurorapkgrel}-ARCH" ]] || fail "kernel release $_kernver"
  [[ " ${depends[*]} " == *" linux-aurora=${_auroraver}.aurora${_aurorarel}-${_aurorapkgrel} "* ]] ||
    fail "depends does not pin the exact linux-aurora: ${depends[*]}"
  [[ " ${makedepends[*]} " == *" linux-aurora-headers=${_auroraver}.aurora${_aurorarel}-${_aurorapkgrel} "* ]] ||
    fail "makedepends does not pin the exact linux-aurora-headers: ${makedepends[*]}"
  for tool in clang18 llvm18 lld18; do
    [[ " ${makedepends[*]} " == *" $tool "* ]] || fail "makedepends lacks $tool (the kernel is built with LLVM 18)"
  done
  [[ $pkgver == "${_v4l2ver}_${_auroraver}.aurora${_aurorarel}.${_aurorapkgrel}" ]] || fail "pkgver $pkgver"
  [[ " ${conflicts[*]} " == *" v4l2loopback-dkms "* ]] || fail "must conflict with v4l2loopback-dkms"
  if command -v vercmp >/dev/null 2>&1; then
    # A new kernel or a new upstream release is an upgrade; the old test-only package is older.
    (( $(vercmp "${pkgver}-${pkgrel}" "0.15.4-1") > 0 )) || fail "$pkgver must sort above the test-only 0.15.4-1"
    (( $(vercmp "${pkgver}-${pkgrel}" "${_v4l2ver}_${_auroraver}.aurora0sredge99.1-1") < 0 )) ||
      fail "a later kernel build must sort above $pkgver"
  fi
)
AURORA_KERNEL_BUILD_DIR=/x bash -c 'source "$1"; [[ " ${makedepends[*]} " != *linux-aurora-headers* ]]' _ "$recipe" ||
  fail "with AURORA_KERNEL_BUILD_DIR the installed headers are not required"
grep -q 'LLVM="${AURORA_LLVM:-/usr/lib/llvm18/bin/}"' "$recipe" || fail "build does not use /usr/lib/llvm18/bin/"
grep -q 'modinfo -F vermagic' "$recipe" || fail "check() does not verify the module's vermagic"
grep -q 'extra/v4l2loopback.ko' "$recipe" || fail "module path is not usr/lib/modules/KVER/extra/v4l2loopback.ko"

grep -q '`v4l2loopback-aurora`' "$doc" || fail "carried-packages.md does not list v4l2loopback-aurora"
grep -q 'uname -r' "$doc" && grep -q 'v4l2loopback-aurora.*rebuild\|rebuild.*v4l2loopback-aurora' "$doc" ||
  fail "carried-packages.md does not say to rebuild v4l2loopback-aurora when uname -r changes"
echo "PASS v4l2loopback-aurora"
