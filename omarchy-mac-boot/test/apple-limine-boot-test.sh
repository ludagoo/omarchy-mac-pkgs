#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

leaf="$ROOT/setup/limine-boot.sh"
test_tmp=$(mktemp -d)
trap 'rm -rf "$test_tmp"' EXIT

# Minimal shared menu fixture; the production template is owned by omarchy-settings.
mkdir -p "$test_tmp/runtime/default/limine"
printf 'timeout: 1\nquiet: yes\ninterface_branding: Omarchy Bootloader\n' >"$test_tmp/runtime/default/limine/limine.conf"
stub_bin="$test_tmp/bin"
calls="$test_tmp/calls"
esp="$test_tmp/esp"
etc="$test_tmp/etc"
mkdir -p "$stub_bin" "$esp/EFI/BOOT" "$etc" "$test_tmp/share/limine" "$test_tmp/boot/grub"

printf '#!/bin/bash\nexec "$@"\n' >"$stub_bin/sudo"
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/omarchy-hw-apple-silicon"
printf '#!/bin/bash\necho linux-aurora\n' >"$stub_bin/omarchy-mac-kernel"
printf '#!/bin/bash\necho "systemctl $*" >>"$TEST_CALLS"\n' >"$stub_bin/systemctl"
printf '#!/bin/bash\necho "limine-snapper-sync $*" >>"$TEST_CALLS"\n' >"$stub_bin/limine-snapper-sync"
cat >"$stub_bin/findmnt" <<'SH'
#!/bin/bash
case "$*" in
  "-no TARGET $TEST_ESP") echo "$TEST_ESP" ;;
  "-no UUID /") echo mounted-root ;;
  *) exit 1 ;;
esac
SH
# The Asahi update-grub writes its EFI image to TARGET from /etc/default/update-grub.
cat >"$stub_bin/update-grub" <<'SH'
#!/bin/bash
echo "update-grub" >>"$TEST_CALLS"
target=$(sed -n 's/^TARGET="\(.*\)"$/\1/p' "$TEST_UPDATE_GRUB_DEFAULT")
[[ -n $target ]] || target=$TEST_ESP/EFI/BOOT/BOOTAA64.EFI
printf 'GRUB image\n' >"$target"
# It also rewrites GRUB_DIR: config, environment and module directory.
mkdir -p "$TEST_GRUB_DIR/arm64-efi"
printf 'regenerated grub.cfg\n' >"$TEST_GRUB_DIR/grub.cfg"
printf 'regenerated core\n' >"$TEST_GRUB_DIR/arm64-efi/core.efi"
SH
# limine-update builds the UKI and writes the Omarchy block, keeping other top-level entries.
cat >"$stub_bin/limine-update" <<'SH'
#!/bin/bash
echo "limine-update" >>"$TEST_CALLS"
[[ -z ${FAIL_LIMINE_UPDATE:-} ]] || exit 1
mkdir -p "$TEST_ESP/EFI/Linux"
printf 'UKI\n' >"$TEST_ESP/EFI/Linux/omarchy_linux-aurora.efi"
# Same load order as limine-entry-tool (ConfigReader): packaged conf, then
# drop-ins in name order, then /etc/default/limine. The last ENABLE_VERIFICATION
# wins. yes appends a 128-hex blake2-shaped suffix; anything else leaves the
# path bare, which is what a room must boot.
if ! grep -q '^/+Omarchy' "$TEST_ESP/limine.conf"; then
  cmdline=$(sed -n 's/^KERNEL_CMDLINE\[default\]="\(.*\)"$/\1/p' "$TEST_LIMINE_DEFAULT")
  root=$(dirname "$TEST_LIMINE_DEFAULT")
  verify=
  take() {
    [[ -f $1 ]] || return 0
    local line
    line=$(sed -n 's/^ENABLE_VERIFICATION=//p' "$1" | tail -n 1)
    line=${line#\"}; line=${line%\"}
    [[ -n $line ]] && verify=$line
  }
  take "$root/limine-entry-tool.conf"
  if [[ -d $root/limine-entry-tool.d ]]; then
    for drop in "$root"/limine-entry-tool.d/*.conf; do
      take "$drop"
    done
  fi
  take "$TEST_LIMINE_DEFAULT"
  path=boot\(\):/EFI/Linux/omarchy_linux-aurora.efi
  if [[ $verify == yes ]]; then
    hash=$(printf '%128s' '')
    path="$path#${hash// /a}"
  fi
  printf '/+Omarchy\n  //linux-aurora\n  protocol: efi\n  path: %s\n  cmdline: %s\n' "$path" "$cmdline" >>"$TEST_ESP/limine.conf"
fi
SH
chmod +x "$stub_bin"/*
for name in omarchy-mac-limine-cmdline omarchy-mac-limine-deploy omarchy-mac-limine-active; do
  ln -s "$ROOT/bin/$name" "$stub_bin/$name"
done

# A Mac from today's image: GRUB and its tools are installed.
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/grub-probe"
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/grub-mkconfig"
chmod +x "$stub_bin/grub-probe" "$stub_bin/grub-mkconfig"

printf 'LIMINE v1\n' >"$test_tmp/share/limine/BOOTAA64.EFI"
printf 'GRUB image\n' >"$esp/EFI/BOOT/BOOTAA64.EFI"
printf 'GRUB_CMDLINE_LINUX=""\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash rootflags=x-systemd.device-timeout=0"\n' >"$etc/grub"
printf 'UUID=root-uuid / btrfs subvol=@ 0 0\n' >"$etc/fstab"
printf 'aaaabbbbccccddddeeeeffff00001111\n' >"$etc/machine-id"

run() {
  TEST_CALLS="$calls" TEST_ESP="$esp" TEST_UPDATE_GRUB_DEFAULT="$etc/update-grub" TEST_LIMINE_DEFAULT="$etc/limine" \
  TEST_GRUB_DIR="$test_tmp/boot/grub" OMARCHY_GRUB_DIR="$test_tmp/boot/grub" \
  OMARCHY_PATH="$test_tmp/runtime" OMARCHY_ESP="$esp" OMARCHY_LIMINE_EFI="$test_tmp/share/limine/BOOTAA64.EFI" \
  OMARCHY_GRUB_DEFAULT="$etc/grub" OMARCHY_UPDATE_GRUB_DEFAULT="$etc/update-grub" OMARCHY_LIMINE_DEFAULT="$etc/limine" \
  OMARCHY_GRUB_TARGET="$test_tmp/boot/grub/grub-aa64.efi" OMARCHY_LIMINE_BOOT_HOOKS_DIR="$etc/boot/hooks/pre.d" \
  OMARCHY_PACMAN_HOOKS_DIR="$etc/pacman.d/hooks" OMARCHY_SYSTEMD_DIR="$etc/systemd/system" \
  OMARCHY_LIMINE_GATE="$test_tmp/limine.enabled" OMARCHY_FSTAB="$etc/fstab" \
  OMARCHY_MACHINE_ID="$etc/machine-id" \
  OMARCHY_LIMINE_MENU_DEFAULTS="$ROOT/files/usr/lib/omarchy/mac-boot/limine-menu-defaults" \
  PATH="$stub_bin:$PATH" TEST_LEAF="$leaf" bash -c '
    trap "echo caller-trap >&2" ERR
    caller_trap=$(trap -p ERR)
    if [[ ${TEST_CONDITIONAL_SOURCE:-0} == 1 ]]; then
      source "$TEST_LEAF" || exit $?
    else
      source "$TEST_LEAF"
      status=$?
      (( status == 0 )) || exit "$status"
    fi
    [[ $(trap -p ERR) == "$caller_trap" ]] || exit 99
  '

}

# No gate: a GRUB Mac stays one.
: >"$calls"
run || fail "the leaf returns cleanly without the gate"
[[ ! -s $calls && ! -e $etc/limine && $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "GRUB image" ]] ||
  fail "without the gate nothing changes" "$(cat "$calls")"
pass "Limine is opt-in"

: >"$test_tmp/limine.enabled"

# No menu template: nothing happens at all. The checkout's own template is
# never moved; the leaf is pointed at a path that does not exist.
: >"$calls"
if OMARCHY_LIMINE_CONF_SOURCE="$test_tmp/missing.conf" run 2>"$test_tmp/err"; then
  fail "an opted-in image must fail without its menu template"
fi
[[ ! -s $calls && ! -e $etc/limine && $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "GRUB image" ]] ||
  fail "without the menu template nothing changes" "$(cat "$calls")"
grep -q 'menu template' "$test_tmp/err" || fail "the missing template is reported" "$(cat "$test_tmp/err")"
pass "no menu template, no activation"

# Writes through a linked destination would escape the rollback backup.
printf 'unmanaged defaults\n' >"$test_tmp/linked-defaults"
ln -s "$test_tmp/linked-defaults" "$etc/limine"
if run 2>"$test_tmp/err"; then fail "linked mutable destinations are rejected before writes"; fi
[[ $(cat "$test_tmp/linked-defaults") == "unmanaged defaults" && -L $etc/limine ]] || fail "refusal preserves the linked target"
rm "$etc/limine"
pass "activation refuses writes outside its rollback set"

# Installing the menu fails under the production shell flags. The scoped
# transaction restores the previous boot files and reports the failure.
: >"$calls"
cat >"$stub_bin/install" <<'SH'
#!/bin/bash
for arg in "$@"; do
  [[ $arg == "$TEST_ESP/limine.conf" ]] && exit 9
done
exec /usr/bin/install "$@"
SH
chmod +x "$stub_bin/install"
status=0
TEST_CALLS="$calls" TEST_ESP="$esp" TEST_UPDATE_GRUB_DEFAULT="$etc/update-grub" TEST_LIMINE_DEFAULT="$etc/limine" \
  TEST_GRUB_DIR="$test_tmp/boot/grub" OMARCHY_GRUB_DIR="$test_tmp/boot/grub" \
  OMARCHY_PATH="$test_tmp/runtime" OMARCHY_ESP="$esp" OMARCHY_LIMINE_EFI="$test_tmp/share/limine/BOOTAA64.EFI" \
  OMARCHY_GRUB_DEFAULT="$etc/grub" OMARCHY_UPDATE_GRUB_DEFAULT="$etc/update-grub" OMARCHY_LIMINE_DEFAULT="$etc/limine" \
  OMARCHY_GRUB_TARGET="$test_tmp/boot/grub/grub-aa64.efi" OMARCHY_LIMINE_BOOT_HOOKS_DIR="$etc/boot/hooks/pre.d" \
  OMARCHY_PACMAN_HOOKS_DIR="$etc/pacman.d/hooks" OMARCHY_SYSTEMD_DIR="$etc/systemd/system" \
  OMARCHY_LIMINE_GATE="$test_tmp/limine.enabled" OMARCHY_FSTAB="$etc/fstab" \
  PATH="$stub_bin:$PATH" bash -eE -c "source '$leaf'" 2>"$test_tmp/err" || status=$?
rm -f "$stub_bin/install"
(( status != 0 )) || fail "a menu write failure fails the leaf" "$(cat "$test_tmp/err")"
grep -q 'cannot install the Limine menu' "$test_tmp/err" || fail "the menu write failure is reported" "$(cat "$test_tmp/err")"
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "GRUB image" ]] || fail "a menu write failure leaves GRUB in the U-Boot slot"
[[ ! -e $etc/limine ]] || fail "a menu write failure removes the Limine defaults it created" "$(cat "$etc/limine" 2>&1)"
[[ ! -e $etc/update-grub ]] || fail "a menu write failure puts GRUB's update target back"
pass "a menu write failure rolls the activation back"

# limine-update fails: GRUB keeps the U-Boot slot and the caller sees failure.
: >"$calls"
if FAIL_LIMINE_UPDATE=1 run 2>"$test_tmp/err"; then fail "an opted-in build failure must fail the caller"; fi
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "GRUB image" ]] || fail "a failed UKI build leaves GRUB in the U-Boot slot"
[[ ! -e $etc/limine ]] || fail "a failed activation removes the Limine defaults it created"
[[ ! -e $etc/update-grub ]] || fail "a failed activation puts GRUB's update target back (none before)"
(( $(grep -c '^update-grub$' "$calls") == 1 )) || fail "rollback restores the loader without regenerating GRUB" "$(cat "$calls")"
grep -q 'restored the previous boot files' "$test_tmp/err" || fail "the failure is reported" "$(cat "$test_tmp/err")"
pass "GRUB keeps the slot until the Limine menu boots the kernel"

# The full activation.
: >"$calls"
run || fail "the leaf activates Limine"
grep -Fxq "TARGET=\"$test_tmp/boot/grub/grub-aa64.efi\"" "$etc/update-grub" || fail "update-grub is retargeted away from the U-Boot slot"
[[ $(cat "$test_tmp/boot/grub/grub-aa64.efi") == "GRUB image" ]] || fail "update-grub wrote its image to the unused target"
[[ ! -e $esp/EFI/BOOT/grub-aa64.efi ]] || fail "no GRUB image is left on the ESP"
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "LIMINE v1" ]] || fail "Limine takes the U-Boot slot"
grep -Fxq 'KERNEL_CMDLINE[default]="root=UUID=root-uuid rw rootflags=subvol=@,x-systemd.device-timeout=0 quiet splash"' "$etc/limine" ||
  fail "the Limine command line is derived from GRUB's defaults" "$(cat "$etc/limine")"
grep -Fxq 'BOOT_ORDER="linux-aurora, *, *fallback, Snapshots"' "$etc/limine" && grep -Fxq 'ENABLE_UKI=yes' "$etc/limine" ||
  fail "the Limine defaults name the kernel entry first and build a UKI"
[[ -L $etc/boot/hooks/pre.d/20-omarchy-mac-cmdline ]] || fail "the command line hook runs before every UKI rebuild"
[[ $(tr '\n' ' ' <"$calls") == "update-grub limine-update limine-snapper-sync "* ]] ||
  fail "GRUB is regenerated first, the UKI built before Limine is deployed, snapshots synced last" "$(cat "$calls")"
grep -Fxq 'timeout: 1' "$esp/limine.conf" && grep -Fxq 'quiet: yes' "$esp/limine.conf" &&
  grep -Fq 'interface_branding: Omarchy Bootloader' "$esp/limine.conf" ||
  fail "Omarchy's Limine menu with the template's timeout and quiet mode"
! grep -q '^/GRUB' "$esp/limine.conf" || fail "the menu has no GRUB entry" "$(cat "$esp/limine.conf")"
grep -Fq 'Exec = /usr/bin/omarchy-mac-limine-deploy' "$etc/pacman.d/hooks/81-omarchy-mac-limine-deploy.hook" ||
  fail "a pacman hook redeploys Limine when the package changes"
grep -q 'systemctl enable --now limine-snapper-sync.service' "$calls" || fail "limine-snapper-sync.service (the watcher that writes snapshot entries) is enabled and started"
pass "Limine is activated the way x86 boots"

# Idempotent, and the experiment's GRUB recovery entry and resync unit are removed.
{ cat "$esp/limine.conf"; printf '\n/GRUB (recovery)\n    protocol: efi_chainload\n    path: boot():/EFI/BOOT/grub-aa64.efi\n'; } >"$test_tmp/conf"
cp "$test_tmp/conf" "$esp/limine.conf"
mkdir -p "$etc/systemd/system" && : >"$etc/systemd/system/omarchy-mac-boot-sync.service"
run || fail "a second run succeeds"
! grep -q '^/GRUB' "$esp/limine.conf" || fail "a leftover GRUB recovery entry is removed" "$(cat "$esp/limine.conf")"
grep -q '^/+Omarchy$' "$esp/limine.conf" || fail "the Omarchy block survives the cleanup"
[[ ! -e $etc/systemd/system/omarchy-mac-boot-sync.service ]] || fail "the experiment's resync unit is removed"
(( $(grep -c '^timeout: ' "$esp/limine.conf") == 1 && $(grep -c '^quiet: ' "$esp/limine.conf") == 1 )) || fail "one timeout line and one quiet line"
pass "re-running the leaf changes nothing that was right and cleans the experiment up"

# A newer Limine package: the ESP follows, and GRUB's recovery image is never
# overwritten with the old Limine.
printf 'LIMINE v2\n' >"$test_tmp/share/limine/BOOTAA64.EFI"
run || fail "the leaf runs after a Limine upgrade"
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "LIMINE v2" ]] || fail "the ESP gets the new Limine"
[[ ! -e $esp/EFI/BOOT/grub-aa64.efi ]] || fail "no GRUB image appears on the ESP after a Limine upgrade"
pass "a Limine upgrade only replaces the U-Boot slot"

# A menu another identity wrote (the image's, or the one before a factory
# reset) starts over, and that identity's history goes with it. The staging
# directory the installer writes install.conf into is never touched.
mkdir -p "$esp/omarchy" "$esp/0123456789abcdef0123456789abcdef"
sed -i.bak '1i\
comment: machine-id=0123456789abcdef0123456789abcdef
' "$esp/limine.conf"
: >"$calls"
run || fail "the leaf runs against a menu from another identity"
! grep -q 'machine-id=0123456789abcdef' "$esp/limine.conf" || fail "the stale identity's entries are gone" "$(cat "$esp/limine.conf")"
[[ ! -d $esp/0123456789abcdef0123456789abcdef ]] || fail "the stale identity's history is removed"
[[ -d $esp/omarchy ]] || fail "the installer's staging directory survives"
grep -q '^/+Omarchy$' "$esp/limine.conf" || fail "the menu is rebuilt"
pass "a menu from another identity starts over"

# An image that never shipped GRUB: the leaf activates Limine with no
# update-grub to retarget and no GRUB image anywhere.
rm -f "$etc/update-grub" "$esp/limine.conf" "$test_tmp/boot/grub/grub-aa64.efi"
printf 'GRUB image\n' >"$esp/EFI/BOOT/BOOTAA64.EFI"
# asahi-scripts keeps update-grub for update-m1n1 even where GRUB is gone, and
# it fails without grub-probe: the leaf must read GRUB's own tools.
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/grub-probe"
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/grub-mkconfig"
chmod +x "$stub_bin/grub-probe" "$stub_bin/grub-mkconfig"
rm -f "$stub_bin/grub-probe" "$stub_bin/grub-mkconfig"
: >"$calls"
OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "the leaf activates Limine without GRUB installed"
[[ ! -e $etc/update-grub ]] || fail "nothing is retargeted when there is no update-grub"
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "LIMINE v2" ]] || fail "Limine takes the U-Boot slot without GRUB"
grep -q '^/+Omarchy$' "$esp/limine.conf" || fail "the menu is written without GRUB"
! grep -q '^update-grub$' "$calls" || fail "no GRUB regeneration is attempted" "$(cat "$calls")"
pass "an image without GRUB activates Limine on its own"

# A fresh image's first boot: deferred hardware setup rebuilds the boot image
# after its last step, so a menu that already boots the UKI keeps it and the
# leaf only asks for that rebuild. The image ships that menu with no identity,
# so the leaf keys its entry to this Mac for the entry tool to rebuild in place.
request="$test_tmp/boot-rebuild"
sed -i.bak '/^comment: machine-id=/d' "$esp/limine.conf"
cp "$esp/EFI/Linux/omarchy_linux-aurora.efi" "$test_tmp/image-uki"
cp "$esp/limine.conf" "$test_tmp/image-menu"
: >"$calls"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "the leaf finishes under deferred hardware setup"
[[ -f $request ]] || fail "the leaf asks for the rebuild after the last deferred step"
! grep -Eq '^(limine-update|update-grub)$' "$calls" || fail "no UKI build and no GRUB step in the leaf" "$(cat "$calls")"
cmp -s "$esp/EFI/Linux/omarchy_linux-aurora.efi" "$test_tmp/image-uki" || fail "the UKI the Mac boots stays in place until the rebuild"
diff <(sed '/^comment: machine-id=/d' "$esp/limine.conf") "$test_tmp/image-menu" >/dev/null ||
  fail "the menu the Mac boots stays in place until the rebuild" "$(cat "$esp/limine.conf")"
[[ $(grep -A1 '^/+Omarchy$' "$esp/limine.conf" | tail -n 1) == "comment: machine-id=$(cat "$etc/machine-id")" ]] ||
  fail "the image's entry is keyed to this Mac" "$(cat "$esp/limine.conf")"
[[ $(grep -c '^comment: machine-id=' "$esp/limine.conf") == 1 ]] || fail "the entry is keyed once" "$(cat "$esp/limine.conf")"
grep -q '^KERNEL_CMDLINE\[default\]="root=UUID=root-uuid ' "$etc/limine" || fail "the rebuild's command line is derived" "$(cat "$etc/limine")"
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "LIMINE v2" ]] || fail "Limine keeps the U-Boot slot"
pass "under deferred hardware setup the leaf keys the image's entry and leaves the one UKI build to the end"

# An image that names its own OS (TARGET_OS_NAME in /etc/default/limine) keeps
# that name, and its entry is the one keyed to this Mac.
cp "$esp/limine.conf" "$test_tmp/saved-menu"; cp "$etc/limine" "$test_tmp/saved-defaults"
sed 's|^/+Omarchy$|/+SmartRoom Firmware|' "$test_tmp/image-menu" >"$esp/limine.conf"
sed -i 's/^TARGET_OS_NAME=.*/TARGET_OS_NAME="SmartRoom Firmware"/' "$etc/limine"
rm -f "$request"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "a named image's leaf finishes"
grep -qx 'TARGET_OS_NAME="SmartRoom Firmware"' "$etc/limine" || fail "the image's OS name is kept" "$(cat "$etc/limine")"
[[ $(grep -A1 '^/+SmartRoom Firmware$' "$esp/limine.conf" | tail -n 1) == "comment: machine-id=$(cat "$etc/machine-id")" ]] ||
  fail "the named entry is keyed to this Mac" "$(cat "$esp/limine.conf")"
cp "$test_tmp/saved-menu" "$esp/limine.conf"; cp "$test_tmp/saved-defaults" "$etc/limine"; rm -f "$request"
pass "an image's own Limine OS name is kept and its entry keyed"

# A menu already keyed to this Mac is left as it is.
rm -f "$request"
cp "$esp/limine.conf" "$test_tmp/keyed-menu"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "the leaf reruns on a keyed menu"
cmp -s "$esp/limine.conf" "$test_tmp/keyed-menu" || fail "a keyed menu is not keyed again" "$(cat "$esp/limine.conf")"
[[ $(grep -c '^comment: machine-id=' "$esp/limine.conf") == 1 ]] || fail "a second run leaves one identity line" "$(cat "$esp/limine.conf")"
pass "a menu keyed to this Mac is not keyed again"

# An identity-less menu whose entry is not Omarchy's gets no identity line.
rm -f "$request"
sed 's|^/+Omarchy$|/+Renamed|' "$test_tmp/image-menu" >"$esp/limine.conf"
cp "$esp/limine.conf" "$test_tmp/renamed-menu"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "the leaf runs on a menu without an Omarchy entry"
! grep -q '^comment: machine-id=' "$esp/limine.conf" || fail "only the Omarchy entry is keyed" "$(cat "$esp/limine.conf")"
pass "a menu without an Omarchy entry is not keyed"

# Without a machine identity yet there is nothing to key the entry to.
rm -f "$request"
cp "$test_tmp/image-menu" "$esp/limine.conf"
cp "$etc/machine-id" "$test_tmp/machine-id"
: >"$etc/machine-id"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "the leaf runs without a machine identity"
! grep -q 'machine-id=' "$esp/limine.conf" || fail "no identity is invented" "$(cat "$esp/limine.conf")"
cp "$test_tmp/machine-id" "$etc/machine-id"
pass "an unset machine identity leaves the image's entry unkeyed"

# A menu that does not boot the UKI yet is built at once, request or not.
rm -f "$request"
cp "$test_tmp/runtime/default/limine/limine.conf" "$esp/limine.conf"
: >"$calls"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "the leaf builds a menu that boots nothing"
grep -qx 'limine-update' "$calls" && [[ ! -e $request ]] || fail "a menu without the UKI is built by the leaf" "$(cat "$calls")"
grep -q '^/+Omarchy$' "$esp/limine.conf" || fail "the built menu boots the UKI"
pass "a menu that boots nothing is never left to a later rebuild"

# A failed reactivation must restore an already-bootable Limine installation,
# not leave an empty cmdline and a rewritten menu for the next reboot.
cp "$etc/limine" "$test_tmp/prior-defaults"
cp "$esp/limine.conf" "$test_tmp/prior-menu"
cp "$esp/EFI/Linux/omarchy_linux-aurora.efi" "$test_tmp/prior-uki"
if FAIL_LIMINE_UPDATE=1 run; then fail "a failed reactivation returns nonzero"; fi
cmp -s "$etc/limine" "$test_tmp/prior-defaults" || fail "reactivation restores the previous defaults"
cmp -s "$esp/limine.conf" "$test_tmp/prior-menu" || fail "reactivation restores the previous menu"
cmp -s "$esp/EFI/Linux/omarchy_linux-aurora.efi" "$test_tmp/prior-uki" || fail "reactivation restores the previous UKI"
pass "failed reactivation preserves the bootable Limine state"

# Failed foreign-identity activation must retain both its history and the
# installer staging content. Cleanup belongs after a successful deployment.
foreign_id=0123456789abcdef0123456789abcdef
mkdir -p "$esp/$foreign_id" "$esp/omarchy"
printf 'history\n' >"$esp/$foreign_id/snapshot"
printf 'installer contract\n' >"$esp/omarchy/install.conf"
printf '\ncomment: machine-id=%s\n' "$foreign_id" >>"$esp/limine.conf"
if TEST_CONDITIONAL_SOURCE=1 FAIL_LIMINE_UPDATE=1 run; then fail "foreign-identity build failure is reported"; fi
[[ $(cat "$esp/$foreign_id/snapshot") == "history" ]] || fail "failed activation retains foreign history"
[[ $(cat "$esp/omarchy/install.conf") == "installer contract" ]] || fail "failed activation retains installer staging contents"
cp "$test_tmp/prior-menu" "$esp/limine.conf"
rm -rf "$esp/$foreign_id"
pass "failed replacement retains prior machine history and installer staging"

# Required hook installation happens before deployment. A failure must work
# even when the source itself is in a conditional (errexit is then ignored).
cp "$esp/EFI/BOOT/BOOTAA64.EFI" "$test_tmp/prior-loader"
cp "$etc/pacman.d/hooks/81-omarchy-mac-limine-deploy.hook" "$test_tmp/prior-deploy-hook"
cat >"$stub_bin/tee" <<'STUB'
#!/bin/bash
for arg in "$@"; do
  [[ $arg == */81-omarchy-mac-limine-deploy.hook ]] && exit 8
done
exec /usr/bin/tee "$@"
STUB
chmod +x "$stub_bin/tee"
if TEST_CONDITIONAL_SOURCE=1 run; then fail "required hook write failure is propagated inside a conditional source"; fi
rm -f "$stub_bin/tee"
for item in 'limine prior-defaults' 'pacman.d/hooks/81-omarchy-mac-limine-deploy.hook prior-deploy-hook'; do
  read -r target before <<<"$item"
  cmp -s "$etc/$target" "$test_tmp/$before" || fail "hook failure restores $target"
done
cmp -s "$esp/EFI/BOOT/BOOTAA64.EFI" "$test_tmp/prior-loader" || fail "hook failure never changes the EFI loader"
pass "required deploy hook fails before activation even inside a conditional source"

# A deploy failure after touching the slot still restores the exact prior
# loader, menu, UKI and defaults. Never reconstruct the old loader as GRUB.
rm "$stub_bin/omarchy-mac-limine-deploy"
cat >"$stub_bin/omarchy-mac-limine-deploy" <<'STUB'
#!/bin/bash
printf 'failed-deployment\n' >"$TEST_ESP/EFI/BOOT/BOOTAA64.EFI"
exit 6
STUB
chmod +x "$stub_bin/omarchy-mac-limine-deploy"
if TEST_CONDITIONAL_SOURCE=1 run; then fail "post-write deployment failure is propagated"; fi
rm "$stub_bin/omarchy-mac-limine-deploy"
ln -s "$ROOT/bin/omarchy-mac-limine-deploy" "$stub_bin/omarchy-mac-limine-deploy"
cmp -s "$esp/EFI/BOOT/BOOTAA64.EFI" "$test_tmp/prior-loader" || fail "post-write failure restores the exact loader"
cmp -s "$etc/limine" "$test_tmp/prior-defaults" || fail "post-write failure restores defaults"
cmp -s "$esp/limine.conf" "$test_tmp/prior-menu" || fail "post-write failure restores menu"
cmp -s "$esp/EFI/Linux/omarchy_linux-aurora.efi" "$test_tmp/prior-uki" || fail "post-write failure restores UKI"
pass "deployment rollback restores the existing Limine loader byte for byte"

# Existing GRUB target configuration and an old recovery image are restored
# verbatim, including a zero-byte file: rollback must not infer prior state
# from an empty command substitution or regenerate the loader.
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/grub-probe"
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/grub-mkconfig"
chmod +x "$stub_bin/grub-probe" "$stub_bin/grub-mkconfig"
: >"$etc/update-grub"
printf 'prior unused recovery\n' >"$test_tmp/boot/grub/grub-aa64.efi"
rm -rf "$test_tmp/boot/grub/arm64-efi"
printf 'prior grub.cfg\n' >"$test_tmp/boot/grub/grub.cfg"
printf 'prior env\n' >"$test_tmp/boot/grub/grubenv"
if FAIL_LIMINE_UPDATE=1 run; then fail "GRUB retarget followed by failed UKI reports failure"; fi
[[ $(cat "$test_tmp/boot/grub/grub.cfg") == "prior grub.cfg" ]] || fail "rollback restores GRUB's configuration"
[[ $(cat "$test_tmp/boot/grub/grubenv") == "prior env" ]] || fail "rollback keeps GRUB's environment"
[[ ! -e $test_tmp/boot/grub/arm64-efi ]] || fail "rollback removes modules the failed regeneration wrote"
[[ -f $etc/update-grub && ! -s $etc/update-grub ]] || fail "rollback preserves an existing empty update-grub configuration"
[[ $(cat "$test_tmp/boot/grub/grub-aa64.efi") == "prior unused recovery" ]] || fail "rollback restores the old recovery image"
cmp -s "$esp/EFI/BOOT/BOOTAA64.EFI" "$test_tmp/prior-loader" || fail "GRUB rollback preserves the actual previous EFI loader"
pass "rollback restores GRUB target configuration, GRUB directory and recovery image verbatim"

# A helper that returns success without deploying the packaged bytes does
# not satisfy activation; image and first-boot callers must see the failure.
printf 'previous-efi\n' >"$esp/EFI/BOOT/BOOTAA64.EFI"
rm "$stub_bin/omarchy-mac-limine-deploy"
printf '#!/bin/bash\nexit 0\n' >"$stub_bin/omarchy-mac-limine-deploy"
chmod +x "$stub_bin/omarchy-mac-limine-deploy"
if run; then fail "success without matching EFI bytes is refused"; fi
[[ $(cat "$esp/EFI/BOOT/BOOTAA64.EFI") == "previous-efi" ]] || fail "false-success rollback retains the prior loader"
pass "successful activation requires actual packaged EFI bytes"

# The image's built configuration, then the real first-boot leaf (which runs
# the real command-line helper and the real deploy). The case above left a
# deploy that succeeds without copying; put the real one back. /etc/limine-entry-tool.conf
# ships ENABLE_VERIFICATION=yes. The drop-in turns it off and sorts last. The
# leaf rewrites /etc/default/limine and does not mention the key, so the
# drop-in still wins and the menu gets no checksum. panic=10 is a word of
# GRUB_CMDLINE_LINUX_DEFAULT; the console leaf does not rewrite that line, and
# the helper copies it onto the UKI command line.
rm -f "$stub_bin/omarchy-mac-limine-deploy"
ln -s "$ROOT/bin/omarchy-mac-limine-deploy" "$stub_bin/omarchy-mac-limine-deploy"
unset FAIL_LIMINE_UPDATE || true
printf 'ENABLE_VERIFICATION=yes\n' >"$etc/limine-entry-tool.conf"
mkdir -p "$etc/limine-entry-tool.d"
printf '%s\n' '# first boot rewrites /etc/default/limine and keeps only TARGET_OS_NAME.' \
  'ENABLE_VERIFICATION=no' >"$etc/limine-entry-tool.d/zz-smartroom-firmware.conf"
cp "$etc/limine-entry-tool.d/zz-smartroom-firmware.conf" "$test_tmp/drop-in"
printf '%s\n' \
  'GRUB_VIDEO_BACKEND="efi_gop"' \
  'GRUB_CMDLINE_LINUX="zswap.enabled=0 rootfstype=btrfs rootflags=x-systemd.device-timeout=0"' \
  'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 systemd.show_status=false rd.udev.log_level=0 vt.global_cursor_default=0 plymouth.ignore-serial-consoles panic=10"' \
  >"$etc/grub"
printf 'TARGET_OS_NAME="SmartRoom Firmware"\nENABLE_UKI=yes\nCUSTOM_UKI_NAME="omarchy"\nFIND_BOOTLOADERS=no\nKERNEL_CMDLINE[default]=""\nESP_PATH="%s"\nBOOT_ORDER="linux-aurora, *, *fallback, Snapshots"\n' "$esp" >"$etc/limine"
mkdir -p "$esp/EFI/Linux"
printf 'UKI\n' >"$esp/EFI/Linux/omarchy_linux-aurora.efi"
cat >"$esp/limine.conf" <<'MENU'
timeout: 1
quiet: yes
interface_branding: Omarchy Bootloader
/+SmartRoom Firmware
  //linux-aurora
  protocol: efi
  path: boot():/EFI/Linux/omarchy_linux-aurora.efi
  cmdline: root=UUID=root-uuid rw quiet splash panic=10
MENU
cp "$esp/limine.conf" "$test_tmp/built-menu"
# Host copies of these would make the console leaf depend on the machine.
printf '#!/bin/bash\nprintf "systemd\\n"\n' >"$stub_bin/omarchy-mac-initramfs-hooks"
printf '#!/bin/bash\necho "omarchy-mac-boot-update" >>"$TEST_CALLS"\n' >"$stub_bin/omarchy-mac-boot-update"
chmod +x "$stub_bin/omarchy-mac-initramfs-hooks" "$stub_bin/omarchy-mac-boot-update"
# setup-boot runs the console leaf first. The device wait is already on the
# line, so this changes nothing and must not drop panic=10.
PATH="$stub_bin:$PATH" TEST_CALLS="$calls" OMARCHY_GRUB_DEFAULT="$etc/grub" \
  OMARCHY_GRUB_CONSOLE_PENDING="$test_tmp/no-such-pending" \
  bash -c 'source "$1"' _ "$ROOT/setup/grub-console.sh" || fail "the console leaf fails on the built configuration"
! grep -qx 'omarchy-mac-boot-update' "$calls" || fail "the console leaf regenerated boot files that were already right" "$(cat "$calls")"
grep -Fxq 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 systemd.show_status=false rd.udev.log_level=0 vt.global_cursor_default=0 plymouth.ignore-serial-consoles panic=10"' "$etc/grub" ||
  fail "the console leaf rewrote GRUB_CMDLINE_LINUX_DEFAULT" "$(cat "$etc/grub")"
# Deferred hardware setup: a menu that already boots the UKI is left in place.
request="$test_tmp/boot-rebuild"
rm -f "$request"
: >"$calls"
OMARCHY_IMAGE_BOOT_REBUILD="$request" OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run ||
  fail "first boot fails on the built configuration"
[[ -f $request ]] || fail "first boot defers the UKI rebuild"
! grep -qx 'limine-update' "$calls" || fail "first boot rebuilt the UKI itself" "$(cat "$calls")"
cmp -s "$etc/limine-entry-tool.d/zz-smartroom-firmware.conf" "$test_tmp/drop-in" ||
  fail "first boot rewrote the checksum drop-in"
! grep -q '^ENABLE_VERIFICATION=' "$etc/limine" || fail "first boot put ENABLE_VERIFICATION back into /etc/default/limine" "$(cat "$etc/limine")"
grep -qx 'TARGET_OS_NAME="SmartRoom Firmware"' "$etc/limine" || fail "first boot dropped the OS name" "$(cat "$etc/limine")"
grep -Eq 'KERNEL_CMDLINE\[default\]="[^"]*(^|[[:space:]])panic=10([[:space:]"]|$)' "$etc/limine" ||
  fail "the derived UKI command line lost panic=10" "$(grep KERNEL_CMDLINE "$etc/limine")"
! grep -qE '^ *[a-z_]*path: .*#[0-9a-f]{128}' "$esp/limine.conf" ||
  fail "first boot added a file checksum to the menu" "$(cat "$esp/limine.conf")"
pass "first boot keeps checksums off and panic=10 on the UKI command line"

# The same configuration when the menu does not boot yet: the leaf's own
# limine-update writes the entry, still with no checksum, and the UKI line
# carries panic=10.
rm -f "$request"
cp "$test_tmp/runtime/default/limine/limine.conf" "$esp/limine.conf"
rm -f "$esp/EFI/Linux/omarchy_linux-aurora.efi"
: >"$calls"
OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "a rebuild of the built configuration fails"
grep -qx 'limine-update' "$calls" || fail "a menu that boots nothing is built" "$(cat "$calls")"
! grep -qE '^ *[a-z_]*path: .*#[0-9a-f]{128}' "$esp/limine.conf" ||
  fail "the rebuilt menu carries a file checksum" "$(cat "$esp/limine.conf")"
grep -Eq '^ *cmdline:.*(^|[[:space:]])panic=10([[:space:]]|$)' "$esp/limine.conf" ||
  fail "the rebuilt UKI command line has no panic=10" "$(grep cmdline "$esp/limine.conf")"
pass "a rebuild of the built configuration writes no checksum and puts panic=10 on the UKI line"

# Without the drop-in the packaged default (yes) is in force, and the menu
# gets a checksum. This is how the stub shows it really consulted the setting.
rm -f "$etc/limine-entry-tool.d/zz-smartroom-firmware.conf"
cp "$test_tmp/runtime/default/limine/limine.conf" "$esp/limine.conf"
rm -f "$esp/EFI/Linux/omarchy_linux-aurora.efi"
OMARCHY_GRUB_PROBE=omarchy-test-absent-grub-probe run || fail "a rebuild with checksums on fails"
grep -qE '^ *[a-z_]*path: .*#[0-9a-f]{128}' "$esp/limine.conf" ||
  fail "checksums on, the menu should carry one" "$(cat "$esp/limine.conf")"
pass "with the drop-in gone, the packaged checksum default is on the menu"
