#!/usr/bin/env bash
# Offline checks for the carried linux-aurora edge PKGBUILD and docs.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/../.." && pwd)
pkgdir=$root/smartroom/pkgbuilds/linux-aurora
pkgbuild=$pkgdir/PKGBUILD
carry=$root/CARRY.md
proc=$root/smartroom/docs/carried-packages.md

fail() { echo "FAIL linux-aurora-pkg: $*" >&2; exit 1; }

(
  # shellcheck disable=SC1090
  source "$pkgbuild"
  [[ $_commit =~ ^[0-9a-f]{40}$ ]] || fail "_commit is not a 40-hex hash: $_commit"
  [[ $_auroraver == 7.3.0 ]] || fail "unexpected _auroraver: $_auroraver"
  [[ $_aurorarel =~ ^0sredge[0-9]+$ ]] || fail "unexpected _aurorarel: $_aurorarel"
  [[ $pkgver == "${_auroraver}.aurora${_aurorarel}" ]] || fail "pkgver mismatch: $pkgver"
  [[ ${source[*]} == *"https://github.com/ludagoo/linux.git#commit=${_commit}"* ]] ||
    fail "source does not pin ludagoo/linux commit $_commit"
  grep -Fq "$_commit" "$carry" || fail "CARRY.md does not name $_commit"
  grep -Fq "${pkgver}-${pkgrel}" "$carry" || fail "CARRY.md does not name ${pkgver}-${pkgrel}"

  for i in "${!source[@]}"; do
    item=${source[$i]}
    sum=${sha256sums[$i]}
    if [[ $item == *::* ]]; then
      [[ $sum == SKIP ]] || fail "expected SKIP checksum for $item"
      continue
    fi
    [[ -f $pkgdir/$item ]] || fail "missing local source file: $item"
    got=$(sha256sum "$pkgdir/$item" | awk '{print $1}')
    [[ $got == "$sum" ]] || fail "sha256 mismatch for $item ($got != $sum)"
  done

  if command -v vercmp >/dev/null 2>&1; then
    (( $(vercmp "${pkgver}-${pkgrel}" "7.3.0.aurora0sredge3-1") > 0 )) ||
      fail "${pkgver}-${pkgrel} must sort above 7.3.0.aurora0sredge3-1"
    (( $(vercmp "${pkgver}-${pkgrel}" "7.3.0.aurora1-1") < 0 )) ||
      fail "${pkgver}-${pkgrel} must sort below 7.3.0.aurora1-1"
  fi
)

[[ -f $proc ]] || fail "missing process doc: $proc"
for link in \
  "https://github.com/aurora-silicon/linux/pull/2373" \
  "https://github.com/aurora-silicon/linux/pull/2376" \
  "https://github.com/aurora-silicon/linux/pull/1149" \
  "https://github.com/omacom/linux-aurora/pull/5" \
  "https://github.com/omacom/linux-aurora/pull/467" \
  "https://github.com/omacom/omarchy-pkgs/pull/3025"
do
  grep -Fq "$link" "$proc" || fail "carried-packages.md missing upstream PR link: $link"
done

echo "PASS linux-aurora-pkg"
