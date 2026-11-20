#!/bin/bash
# The chromium-smartroom recipe in this repo is the one that built the package
# the edge image ships: PKGBUILD's sha256 is BUILT's pkgbuild_sha256 (the
# package's .BUILDINFO), and every local source file matches its sha256sums
# entry. Offline, no makepkg.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
recipe=${CHROMIUM_SMARTROOM_RECIPE:-$here/../pkgbuilds/chromium-smartroom}
fail() { echo "FAIL: $*" >&2; exit 1; }

built() { sed -n "s/^$1=//p" "$recipe/BUILT"; }
[[ -f $recipe/PKGBUILD && -f $recipe/BUILT ]] || fail "no chromium-smartroom recipe at $recipe"
want=$(built pkgbuild_sha256)
[[ $want =~ ^[0-9a-f]{64}$ ]] || fail "BUILT has no pkgbuild_sha256"
got=$(sha256sum "$recipe/PKGBUILD" | cut -d' ' -f1)
[[ $got == "$want" ]] ||
  fail "PKGBUILD is $got, the shipped package was built from $want: rebuild, then update BUILT and the installer's room/prebuilt.sha256"
[[ $(built package_sha256) =~ ^[0-9a-f]{64}$ ]] || fail "BUILT has no package_sha256"
[[ $(built package) == chromium-smartroom-*-aarch64.pkg.tar.* ]] || fail "BUILT names no chromium-smartroom package"
echo "ok - PKGBUILD is the recipe of $(built package)"

# Local sources (no "::" rename and no URL) against their sums, in order.
mapfile -t lines < <(cd "$recipe" && bash -c 'source ./PKGBUILD >/dev/null 2>&1
  for i in "${!source[@]}"; do printf "%s %s\n" "${sha256sums[i]}" "${source[i]}"; done')
((${#lines[@]} > 20)) || fail "PKGBUILD lists too few sources"
local_sources=0
for line in "${lines[@]}"; do
  sum=${line%% *} src=${line#* }
  [[ $src != *::* && $src != *://* ]] || continue
  [[ -f $recipe/$src ]] || fail "source $src is not in the recipe"
  [[ $(sha256sum "$recipe/$src" | cut -d' ' -f1) == "$sum" ]] || fail "$src does not match its sha256sums entry"
  local_sources=$((local_sources + 1))
done
((local_sources > 20)) || fail "only $local_sources local sources checked"
echo "ok - all $local_sources local sources match PKGBUILD's sha256sums"

# Every patch file in the recipe is a source: nothing applied by hand.
for patch in "$recipe"/*.patch; do
  printf '%s\n' "${lines[@]}" | grep -Fq " ${patch##*/}" || fail "${patch##*/} is in the recipe but not a source"
done
echo "ok - every patch in the recipe is a PKGBUILD source"

# The shipped package's own name and replacements.
grep -Fxq "conflicts=('chromium' 'omarchy-chromium-bin')" "$recipe/PKGBUILD" ||
  fail "chromium-smartroom must conflict with chromium and omarchy-chromium-bin"
grep -Fxq 'provides=("chromium=$pkgver")' "$recipe/PKGBUILD" || fail "chromium-smartroom must provide chromium"
echo "ok - chromium-smartroom provides chromium and replaces omarchy-chromium-bin"

# A copied or edited PKGBUILD fails the first check.
scratch=$(mktemp -d); trap 'rm -rf "$scratch"' EXIT
cp -a "$recipe/." "$scratch/"
printf '# edited\n' >>"$scratch/PKGBUILD"
if CHROMIUM_SMARTROOM_RECIPE=$scratch bash "${BASH_SOURCE[0]}" >/dev/null 2>&1; then
  fail "an edited PKGBUILD passes"
fi
echo "ok - an edited PKGBUILD fails"
