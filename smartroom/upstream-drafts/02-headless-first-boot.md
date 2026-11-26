# Draft PR to omacom/omarchy-mac-pkgs (the operator sends it; not opened)

Branch: cut from omacom `main`, cherry-pick "omarchy-mac-boot: first boot for headless images".

**Title:** omarchy-mac-boot: first boot for headless images

An image with no owner at a display (a server, a room controller) cannot finish first boot today: it stops when the runtime's owner provisioning is missing, and any failure takes tty1 with a `gum choose` prompt nobody will answer.

An image that ships `/etc/omarchy-mac-boot/headless` now consumes `install.conf`, makes the keyring and runs the deferred hardware setup exactly as before, but stages no owner provisioning, enables no display manager, and on a failure exits instead of waiting on tty1 (`pending` stays, so the next boot retries). Without the file nothing changes.

Tests: `test/mac-first-boot-test.sh` adds the headless hand-off and the headless failure; the full `omarchy-mac-boot/test/all` passes.

Assisted-by: Claude:claude-opus-5-5
