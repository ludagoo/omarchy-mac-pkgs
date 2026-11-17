# smartroom-boot-os

SmartRoom Firmware only (ludagoo fork). Not an Omarchy package.

Switches an Apple Silicon room Mac between SmartRoom Firmware and macOS (which
runs Zoom Rooms) from Linux, with no macOS password:

```
sudo smartroom-boot-os macos --once --reboot   # macOS for one start, then back
sudo smartroom-boot-os macos                    # macOS from now on
sudo smartroom-boot-os firmware                 # SmartRoom Firmware from now on
sudo smartroom-boot-os status
```

It is a thin wrapper around Omarchy's own tool for this, `aurora-bless`
(package `aurora-bless`, Omarchy's fork of Asahi's `asahi-bless`, already in
every Omarchy Mac image; the Omarchy installer's e2e runbook names it as the
way back to macOS from Linux). `aurora-bless` writes the Mac's `boot-volume`
NVRAM variable (`alt-boot-volume` for `--once`), which the boot picker reads.
The wrapper only picks the volume by name (the firmware is `TARGET_OS_NAME`
from `/etc/default/limine`; macOS is the one other startup volume, or
`SMARTROOM_BOOT_OS_MACOS`), clears a pending next-start choice when setting a
default, and reads the result back.

Going the other way (macOS to SmartRoom Firmware) is macOS's `bless`, which
needs a volume owner's password on Apple Silicon: see the installer fork's
`smartroom/docs/install-zoom-room.md`.

Tests: `test/all` (a simulated aurora-bless; no root, no Mac).
