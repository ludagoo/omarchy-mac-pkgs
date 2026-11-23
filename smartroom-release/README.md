# smartroom-release

Update a SmartRoom room (Apple Silicon Studio or Intel Mini) to a new release as
a trial. The room keeps the new release only if it proves healthy. If it does not,
the room comes back on the previous release by itself, with nobody there.

Design: `~/smartroom-rollback/DESIGN.md` (decisions 1 to 6). One tool on both
lines (WS6 Studio, WS12 Mini). The Mini's older pacman/snapshot update path is
left in place for factory restore; Room Controller status/list/restore go through
this tool.

**Studio:** aura-try + Limine one-shot (U-Boot efivars) + Apple watchdog.  
**Mini:** Limine one-shot (NVRAM) + iTCO_wdt/softdog; health service feeds
`/dev/watchdog`. Keep the last 5 good releases on disk.

**Old Mini migrate:** `smartroom-release migrate-check` then `migrate RELEASE`
(or `bin/smartroom-release-migrate-bootstrap` over SSH). Installs the release
beside the live `@`, arms a trial, keeps `@` until `confirm-migration`.

## What a release is

One tested image: a btrfs root and the boot files that start it.

Studio:
```
manifest.json / manifest.json.sig / root.btrfs.zst
m1n1/boot.bin
EFI/Linux/omarchy_linux-aurora.efi
```

Mini (`"line": "mini"` in the manifest; UKI only):
```
manifest.json / manifest.json.sig / root.btrfs.zst
EFI/Linux/smartroomos_linux-t2.efi
```

```json
{"schema": 1, "id": "2026.11.21-1", "created": "2026-11-21T00:00:00Z", "parent": null,
 "root": {"file": "root.btrfs.zst", "sha256": "...", "size": 123},
 "boot": [{"role": "stage2", "path": "m1n1/boot.bin", "sha256": "...", "size": 123},
          {"role": "uki", "path": "EFI/Linux/omarchy_linux-aurora.efi", "sha256": "...", "size": 123}]}
```

Paths in a manifest must be relative and stay inside the release. The signature
is required (key: `/usr/share/smartroomos/release-keyring.gpg`); `--unsigned`
exists for development and is recorded in the state. A URL must be https.

Make one from a room that runs the image you want to ship:
`smartroom-release build-release --id ID --out DIR [--sign-key FPR]`. It snapshots
the root, sends it, and copies the room's `m1n1/boot.bin` and UKI.

## Commands

```
smartroom-release status [--json]       what runs, what is configured, the trial, the last result
smartroom-release list [--json]
smartroom-release update RELEASE [--reboot] [--unsigned]   stage + arm   (RELEASE: directory or https URL)
smartroom-release stage RELEASE         write the release beside the running one; arm nothing
smartroom-release arm [--reboot]        arm the staged release
smartroom-release rollback [--reboot]   trial of the previous release
smartroom-release discard               drop a staged or armed (not yet booted) trial
smartroom-release restore N --no-reboot --json   the Room Controller's call (see below)
smartroom-release health-run            the boot service (not run by hand)
```

## What it writes

Nothing the room boots from today is touched until the trial has passed.

- `@r-<id>`: the new root, a writable snapshot of the received stream. The room's
  own identity (`release-carry.list`: machine-id, hostname, ssh host keys, network
  profiles, the Room Controller's config and state, the first-boot latch) is copied
  into it, and its fstab and `/etc/default/limine` are pointed at it.
- `m1n1/boot-trial.bin`, `EFI/Linux/omarchy_linux-aurora-trial.efi`: the new boot set,
  beside the configured `m1n1/boot.bin` and `omarchy_linux-aurora.efi`. Each is
  copied beside its name, read back against the manifest's sha256, then renamed.
- A second Limine entry, `SmartRoom Release Trial`, in `limine.conf`. The configured
  entry is not edited.
- `smartroom-release/state.json` on the ESP: the state machine and its event log.

## Arming a trial

Order matters, and the last step is the one that makes it live:

1. Limine's one-shot (`LoaderEntryOneShot`) names the trial entry. U-Boot keeps its
   variables in RAM, so `efi-vars-save` writes them to `ubootefi.var`; the tool reads
   that file back and arms nothing if the one-shot is not in it.
2. `aura-try` is written last: `armed\n<m1n1/boot-trial.bin>\n`. On the next boot aura
   stage 1 rewrites it to `spent`, reads it back, arms a 178 s hardware watchdog, sets
   `chosen/aurora,trial` in the device tree, and runs the trial stage 2. If that image
   cannot start, aura boots the configured image after 10 s. `spent` can never run twice.

The trial command line carries `panic=10` (the tool refuses a release without it), the
trial root, `smartroom.release=<id>` and `watchdog.handle_boot_enabled=0`, so the kernel
does not feed a running watchdog and the health service must.

## The health check

`smartroom-release-health.service` runs on every boot and exits at once unless this boot
is a trial. On a trial boot it opens `/dev/watchdog` and feeds it, then samples every
5 s. A sample is healthy when the Room Controller has an established connection to its
server, the default route is up, and at least as many displays are connected as before
the update. The trial passes after 5 quiet minutes of healthy samples that end within
15 minutes of the start (`/etc/smartroomos/release.conf`: `quiet_seconds`,
`limit_seconds`, `sample_seconds`, `min_displays`, `watchdog_device`, `keyring`,
`reboot_hook`).

On a pass it marks the release good in five resumable steps (`promoting` in the state):
keep the configured set as the previous one, point the configured Limine entry at the new
UKI and root (the one atomic switch), copy `boot.bin`, copy the UKI under its standard
name, point Limine at the standard name. A power cut at any step leaves an entry whose
UKI and root belong together; the next boot finishes the job.

On a miss it stops feeding the watchdog, removes the trial files and the marker, records
why, and reboots (hard reset if that fails). Every failure is a reboot: kernel panics
(`panic=10`), hangs (the hardware watchdog), a trial image that cannot start (aura), and
an unhealthy room (this service). The configured files were never changed, so the room
boots the previous release.

Reasons recorded: `health-timeout`, `lost-before-userspace` (the room came back on the
configured set before the service ever ran), `lost-after-userspace`, `trial-did-not-start`
(Limine ran the trial entry but aura did not run the trial image), `trial-incomplete` (aura
ran the trial image but Limine picked the configured entry).

## Room Controller contract

`status --json` has the shape of the old snapshot helper (`available`, `running`, `fallback`,
`trial`, `firmware`, `count`, `protected`, `esp`) plus a `release` block (running,
configured, previous, boot, last_result) and the last 20 events. `restore N --no-reboot
--json` arms a trial of the previous release and prints `{"accepted", "trialId",
"fallbackSnapshot", "rebootAt"}`; errors are `{"error": {"code", "message"}}`. The Room
Controller reboots the room itself after `restore`.

## Known gaps

- A Limine EFI update cannot be trialled: `BOOTAA64.EFI` is a fixed path in U-Boot.
  It is updated by a normal, careful install.
- After mark-good, the new release is the configured one. If it later fails to boot
  with no trial armed, `panic=10` reboots but there is no automatic return to the
  previous release; use `rollback` (or the macOS side of the Studio) until a boot
  counter is added.
- Releases are full streams. Incremental streams (`parent`) are in the manifest
  but not used yet.
- The ESP holds at most three boot sets (configured, previous, trial), about 230 MB.
- A bad boot image plus a bad kernel image in the same trial is untested: the
  unconsumed Limine one-shot could send the fallback boot into the trial entry without
  the trial watchdog. Release builds check both files, so this needs two faults at once.
- On a Studio whose startup volume is macOS (the home test Studio), a trial that dies
  before Linux starts resets into macOS, not into Linux. The room's own release is
  untouched; blessing SmartRoom Firmware once more returns it, and the tool then records
  the failure. A room whose startup volume is SmartRoom Firmware has not been tried on
  hardware, because the safety rules for the test Studio keep macOS as the default.

## Hardware results (home Studio, test settings: 60 s quiet, 240 s limit)

- Healthy update: trial boots with `aurora,trial` set, the one-shot is consumed and the
  deletion persists, the release becomes configured, the previous set is kept.
- `rollback`: a trial of the previous release, becomes configured again.
- Room not healthy: `health-timeout`, clean reboot back onto the configured release.
- Kernel and initrd that cannot start, and a garbage kernel image: reset, then
  `lost-before-userspace`, files and trial entry cleaned up.
- Garbage boot image: aura falls back, then `trial-did-not-start`, cleaned up.

## Tests

`test/all` runs the whole path on a directory tree with a fake `btrfs`, a fake clock and
a real gpg key. The hardware cycle on a Studio is described in the ws6 report in the
firmware repo (`docs/update-rollback.md`).
