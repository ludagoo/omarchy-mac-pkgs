# Draft PR to omacom/omarchy-mac-pkgs (Lucas sends it; not opened)

Branch: cut from omacom `main`, cherry-pick "omarchy-mac-boot: keep an image's own Limine OS name".

**Title:** omarchy-mac-boot: keep an image's own Limine OS name

`setup/limine-boot.sh` writes `TARGET_OS_NAME="Omarchy"` into `/etc/default/limine` on every activation, so an image built for another product name (a kiosk or appliance built on Omarchy's Mac boot chain) loses its menu entry name on the first boot's setup-boot.

This keeps a `TARGET_OS_NAME` that `/etc/default/limine` already holds (restricted to `[A-Za-z0-9 ._()-]{1,64}`), defaulting to `Omarchy`, and keys the image's entry by that name. Nothing changes for Omarchy images: they never set another name.

Tests: `test/apple-limine-boot-test.sh` adds "an image's own Limine OS name is kept and its entry keyed"; the full `omarchy-mac-boot/test/all` passes.

Assisted-by: Claude:claude-opus-5-5
