#!/bin/bash
# Room browser package (chromium-smartroom 158) on the Studio, as srbuild.
#   prep:  download, extract, prepare() (patches, unbundling, cargo fetch).
#          No compiling, so it may run next to another build (nice 19).
#   build: build() and package() on the prepared tree (makepkg -e),
#          nice 10, ninja -j8, only when no other srbuild ninja/make runs.
set -euo pipefail
phase=$1
D=/var/lib/srbuild/room-158/pkg
LOG=/var/lib/srbuild/work/room-158-makepkg.log
exec >>"$LOG" 2>&1
printf "\nSTART %s %s\n" "$phase" "$(date -Is)"
T=/var/lib/srbuild/.rustup/toolchains/1.99.0-aarch64-unknown-linux-gnu
export PATH="$T/bin:/usr/bin:/bin"
export RUSTUP_TOOLCHAIN=1.99.0-aarch64-unknown-linux-gnu
export RUSTUP_AUTO_INSTALL=0
export SR_RUST_SYSROOT=$T
export NINJAFLAGS=-j8
export MAKEFLAGS=-j8
cd "$D"
case $phase in
  prep)
    nice -n 19 makepkg --nobuild --nodeps --noconfirm
    ;;
  build)
    if pgrep -u srbuild -f 'ninja|make ' >/dev/null; then
      echo "FAILED busy"; exit 1
    fi
    nice -n 10 makepkg -e --nodeps --noconfirm --force
    ;;
  *) echo "usage: $0 prep|build"; exit 2 ;;
esac
echo "${phase^^}_OK $(date -Is)"
