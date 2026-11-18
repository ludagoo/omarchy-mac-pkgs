#!/bin/bash
# Offline tests for the aura-try prototype. No ESP, no reboot, a fake clock.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tool=$here/aura-try
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
esp=$work/esp
mkdir -p "$esp/m1n1" "$esp/trial"
printf 'previous-boot\n' >"$esp/m1n1/boot.bin"
printf 'new-boot\n' >"$esp/trial/boot.bin"
good=$(sha256sum "$esp/trial/boot.bin" | awk '{print $1}')
bad=0000000000000000000000000000000000000000000000000000000000000000

# A bad checksum writes nothing.
if "$tool" arm --esp "$esp" --trial-path trial/boot.bin --configured m1n1/boot.bin \
  --release new --previous old --file "trial/boot.bin=$bad" >/dev/null 2>"$work/err"; then
  echo "arm accepted a bad checksum" >&2
  exit 1
fi
[[ ! -e $esp/aura-try ]] || { echo "a failed check armed the marker" >&2; exit 1; }
grep -q checksum "$work/err"

"$tool" arm --esp "$esp" --trial-path trial/boot.bin --configured m1n1/boot.bin \
  --release new --previous old --file "trial/boot.bin=$good" >"$work/arm.out"
[[ $(cat "$esp/aura-try") == $'armed\ntrial/boot.bin\n' ]] || { echo "marker bytes" >&2; cat "$esp/aura-try"; exit 1; }
cmp "$esp/m1n1/boot.bin" <(printf 'previous-boot\n')

# Four quiet minutes is not enough. A gap resets the five minutes. A window
# that would finish after the 15 minute limit does not count.
start=1000
if "$tool" health --esp "$esp" --boot-started "$start" --now $((start + 240)) \
  --sample "$start,1,1,1" >/dev/null; then
  echo "four minutes was accepted" >&2
  exit 1
fi
if "$tool" health --esp "$esp" --boot-started "$start" --now $((start + 700)) \
  --sample "$start,1,1,1" --sample $((start + 200)),0,1,1 --sample $((start + 450)),1,1,1 >/dev/null; then
  echo "a broken quiet window was accepted" >&2
  exit 1
fi
if "$tool" health --esp "$esp" --boot-started "$start" --now $((start + 900)) \
  --sample $((start + 700)),1,1,1 >/dev/null; then
  echo "a window past 15 minutes was accepted" >&2
  exit 1
fi
"$tool" health --esp "$esp" --boot-started "$start" --now $((start + 800)) \
  --sample "$start,1,1,1" >/dev/null

# mark-good is refused before a passing health check. Reset by a fresh arm
# after proving the refusal on a copy that has not passed.
fresh=$work/fresh
mkdir -p "$fresh/m1n1" "$fresh/trial"
printf 'previous-boot\n' >"$fresh/m1n1/boot.bin"
printf 'new-boot\n' >"$fresh/trial/boot.bin"
"$tool" arm --esp "$fresh" --trial-path trial/boot.bin --configured m1n1/boot.bin \
  --release new --previous old --file "trial/boot.bin=$good" >/dev/null
if "$tool" mark-good --esp "$fresh" --now $((start + 800)) >/dev/null 2>&1; then
  echo "mark-good ran without a health pass" >&2
  exit 1
fi
cmp "$fresh/m1n1/boot.bin" <(printf 'previous-boot\n')

"$tool" mark-good --esp "$esp" --now $((start + 800)) >/dev/null
cmp "$esp/m1n1/boot.bin" <(printf 'new-boot\n')
cmp "$esp/m1n1/boot.bin.previous" <(printf 'previous-boot\n')
[[ ! -e $esp/aura-try ]] || { echo "marker survived mark-good" >&2; exit 1; }

# Rollback leaves the configured bytes alone.
rb=$work/rb
mkdir -p "$rb/m1n1" "$rb/trial"
printf 'previous-boot\n' >"$rb/m1n1/boot.bin"
printf 'new-boot\n' >"$rb/trial/boot.bin"
"$tool" arm --esp "$rb" --trial-path trial/boot.bin --configured m1n1/boot.bin \
  --release new --previous old --file "trial/boot.bin=$good" >/dev/null
"$tool" rollback --esp "$rb" --now $((start + 900)) --reason health-timeout >/dev/null
cmp "$rb/m1n1/boot.bin" <(printf 'previous-boot\n')
report=$("$tool" report --esp "$rb")
grep -qx 'release=old' <<<"$report"
grep -qx 'boot=configured' <<<"$report"
grep -qx 'previous=old' <<<"$report"
grep -q 'event rolled-back .*reason=health-timeout' <<<"$report"
grep -q 'event armed ' <<<"$report"
grep -q 'event files-checked ' <<<"$report"
grep -q 'event started ' <<<"$report"

good_report=$("$tool" report --esp "$esp")
grep -qx 'release=new' <<<"$good_report"
grep -qx 'boot=configured' <<<"$good_report"
grep -q 'event marked-good ' <<<"$good_report"
echo "ok - aura-try arm, health, mark-good, rollback, report"
