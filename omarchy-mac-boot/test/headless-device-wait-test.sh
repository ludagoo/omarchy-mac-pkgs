#!/bin/bash
# A headless, unencrypted room does not wait for its root device for ever: the
# fstab option is x-systemd.device-timeout=60, so a missing disk ends in the
# emergency target (which a room's initrd hook turns into a reboot). Encrypted
# and non-headless Macs keep the wait without a timeout.
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

test_tmp=$(mktemp -d)
trap 'rm -rf "$test_tmp"' EXIT
mkdir -p "$test_tmp/bin"
printf '#!/bin/bash\nexec "$@"\n' >"$test_tmp/bin/sudo"
printf '#!/bin/bash\nexit 0\n' >"$test_tmp/bin/omarchy-hw-apple-silicon"
printf '#!/bin/bash\nexit 1\n' >"$test_tmp/bin/omarchy-mac-limine-active"
for name in grub-probe grub-mkconfig update-grub omarchy-mac-boot-update; do
  printf '#!/bin/bash\nexit 0\n' >"$test_tmp/bin/$name"
done
chmod +x "$test_tmp/bin"/*
export PATH="$test_tmp/bin:$ROOT/bin:$PATH"
export OMARCHY_GRUB_DEFAULT="$test_tmp/grub" OMARCHY_GRUB_CONSOLE_PENDING="$test_tmp/state/pending"
export OMARCHY_MKINITCPIO_CONF_DIR="$test_tmp/mkinitcpio.conf.d" OMARCHY_MKINITCPIO_PRESET_DIR="$test_tmp/presets"
export OMARCHY_MKINITCPIO_KERNEL=linux-asahi
export OMARCHY_MAC_HEADLESS_MARKER="$test_tmp/headless"
export OMARCHY_MKINITCPIO_CONF="$ROOT/test/fixtures/mkinitcpio/systemd.conf"
run() { bash -e -c 'source "$1"' _ "$ROOT/setup/grub-console.sh"; }
cmdline() { sed -n 's/^GRUB_CMDLINE_LINUX="\(.*\)"$/\1/p' "$test_tmp/grub" | tail -n 1; }
seed() { printf 'GRUB_CMDLINE_LINUX="%s"\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n' "$1" >"$test_tmp/grub"; }

# Not headless: the endless wait, as upstream.
rm -f "$test_tmp/headless"
seed 'rootflags=subvol=@'
run
[[ $(cmdline) == 'rootflags=subvol=@,x-systemd.device-timeout=0' ]] || fail "non-headless keeps the endless wait: $(cmdline)"
pass "a Mac that is not headless keeps the root wait without a timeout"

# Headless, unencrypted: 60 s.
: >"$test_tmp/headless"
seed 'rootflags=subvol=@'
run
[[ $(cmdline) == 'rootflags=subvol=@,x-systemd.device-timeout=60' ]] || fail "headless gets a finite wait: $(cmdline)"
run
[[ $(cmdline) == 'rootflags=subvol=@,x-systemd.device-timeout=60' ]] || fail "idempotent: $(cmdline)"
pass "a headless unencrypted room waits 60 s for its root device, once"

# An older room had the endless wait written: it becomes 60 s.
seed 'zswap.enabled=0 rootflags=subvol=@,x-systemd.device-timeout=0'
run
[[ $(cmdline) == 'zswap.enabled=0 rootflags=subvol=@,x-systemd.device-timeout=60' ]] || fail "an earlier endless wait is replaced: $(cmdline)"
seed 'rootflags=x-systemd.device-timeout=0'
run
[[ $(cmdline) == 'rootflags=x-systemd.device-timeout=60' ]] || fail "a rootflags= with only the old wait: $(cmdline)"
pass "an endless wait from an earlier run is replaced"

# Headless but encrypted: someone has to unlock it, so no timeout.
seed 'rd.luks.uuid=luks-id rootflags=subvol=@'
run
[[ $(cmdline) == 'rd.luks.uuid=luks-id rootflags=subvol=@,x-systemd.device-timeout=0' ]] || fail "encrypted keeps the endless wait: $(cmdline)"
pass "an encrypted root keeps the wait without a timeout"

# The timeout can be set for a test or a site.
seed 'rootflags=subvol=@'
OMARCHY_MAC_HEADLESS_DEVICE_TIMEOUT=30 run
[[ $(cmdline) == 'rootflags=subvol=@,x-systemd.device-timeout=30' ]] || fail "timeout override: $(cmdline)"
echo "PASS headless-device-wait"
