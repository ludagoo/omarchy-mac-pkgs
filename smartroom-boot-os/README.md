# smartroom-boot-os

SmartRoom Firmware only (ludagoo fork). Not an Omarchy package.

Switches a room Mac (Apple Silicon Studio or Intel T2 Mac mini) between
SmartRoom Firmware and macOS (which runs Zoom Rooms) from Linux, with no
macOS password:

```
sudo smartroom-boot-os macos --once --reboot   # macOS for one start, then back
sudo smartroom-boot-os macos                    # macOS from now on
sudo smartroom-boot-os firmware                 # SmartRoom Firmware from now on
sudo smartroom-boot-os status
```

- **Apple Silicon** (`aarch64`): thin wrapper around `aurora-bless` (`boot-volume`
  / `alt-boot-volume` NVRAM variables).
- **Intel T2 (`Macmini8,1`)** (`x86_64`): uses `efibootmgr` (`BootOrder` /
  `BootNext`), creates a missing `SmartRoom Firmware` entry pointing to
  `\EFI\BOOT\BOOTX64.EFI`, recreates a missing macOS `BootXXXX` load option
  from `/boot/smartroomos/macos-boot-device.bin` (staged by `mini-install`
  before `bless` overwrites `Boot0080`), and keeps Apple's
  `efi-boot-device{,-data}` / `efi-boot-next{,-data}` efivars aligned when
  present.

Going the other way (macOS to SmartRoom Firmware) is macOS's `bless` via
`smartroom/mac/smartroom-boot-os` in `ludagoo/omarchy-mac-installer`.

Tests: `test/all` (simulated `aurora-bless` and simulated `efibootmgr` +
`efivars`; no root, no Mac).
