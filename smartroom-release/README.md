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

A release is made only by `smartroom-release build-release`, and only from a root that passes the root invariant (below). It writes nothing and signs nothing when the root fails, and it removes an older `manifest.json` and `.sig` from `--out` first.

- From an image (the Studio release build, installer `smartroom/release-pack`): `smartroom-release build-release --id ID --out DIR --source-path MOUNTED_IMAGE/@ --line studio --uki-from UKI --boot-from BOOT_BIN [--source-info firmware=COMMIT ...] [--sign-key FPR]`, as root on the build host.
- From a room that runs the image you want to ship: `smartroom-release build-release --id ID --out DIR [--sign-key FPR]`. It snapshots the root, sends it, and copies the room's `m1n1/boot.bin` and UKI.

Never assemble a release root by hand or by a job script (patching an older root, `rsync -a` from a checkout): on 2026-11-24 that shipped `2026.11.24-studio-edge` and `-edge-b` with about 200 system paths owned by the Room Controller user.

## The root invariant (`check-root`)

`smartroom-release check-root [ROOT] [--json]` checks a root directory, a `root.btrfs.zst` (read without privileges), or the running room (`/`). It fails on:

- `login-owner`: a path whose uid or gid is a login id (1000 and up, except 65534);
- `rc-owner`: a path owned by `smartroomcontroller`, looked up by name in the root's `/etc/passwd` and `/etc/group`;
- `system-owner`: a path under `/etc`, `/usr` or `/opt` whose owner is not root (system groups are fine);
- `system-dir`: `/`, `/etc`, `/usr`, any direct child of `/usr`, `/etc/sudoers`, `/etc/sudoers.d` or a file in it that is not `root:root`, or is writable by group or other;
- `sudoers-mode`: `/etc/sudoers` or a file in `/etc/sudoers.d` with a mode bit beyond `0440` (what plain `visudo -c` enforces);
- `sudoers-missing` and `visudo` (`visudo -c` on the root's sudoers and sudoers.d);
- `unreadable`: a path it cannot list or stat, or, in a stream, a sudoers, passwd or group file whose contents the stream does not carry (no data, a shared copy or an encoded write). An empty sudoers would pass `visudo`, and an empty passwd would hide the Room Controller user.

It stays on the root's own filesystem; on btrfs that is the root's own subvolume, exactly what a release contains. A directory on another filesystem or subvolume (`/boot`, the ESP, `@log`, `@home`, `/mnt`, `/media`, a USB stick) is neither judged nor walked; `other_filesystems` in the JSON lists it, and `smartroomos-integrity` shows it as information. A tech's uid-1000 USB stick never makes a room unsafe.

Exit codes: `0` the root passes, `1` it fails (unsafe), `3` the check itself could not run (a missing path, a bad stream, a crash). `3` is never a verdict on the root. The build side (`build-release`, `desk-check`, `check-image`, `release-pack`) refuses on any non-zero exit. A room never refuses a trial on `3`: `health-run` and the Mini's `smartroomos-boot-commit` log it, show it on ops (`status --json` `release.root_check`, integrity reason `root-check-error`) and treat it as not proven unsafe, because a tool bug must never strand a room. `stage` refuses on it (reason `root-check-error`), since nothing is armed yet.

The exceptions are in the code with their reasons (`ROOT_EXEMPT_TREES`): what is below `/home`, `/opt/smartroom` itself and below (the Room Controller's own directory), what is below `/tmp` and `/var/tmp`, and systemd DynamicUser ids under `/var/lib/private` and the like. `/proc`, `/sys`, `/dev`, `/run` and `.snapshots` are not walked. They were derived from the good root `2026.11.21-studio-ws14b` (86,739 paths, ok), the Mini image `2026.11.21-mini` (98,635 paths, ok) and the repaired Home Studio (87,632 paths, ok); `2026.11.24-studio-edge-b` fails with 207 problems.

Every place a root comes from runs it, and a root that fails is refused:

- `build-release`: before it sends or signs (reason code `unsafe-root`);
- `stage`/`update`: on the received root, before anything is armed (`last_result` `refused`, `unsafe-root`);
- `health-run`: on the running trial, at the start and again before mark-good. An update trial that fails is rolled back at once (no wait): reason `unsafe-root`, with the first paths in `last_result.findings`, for ops. The journal is flushed to disk before the rollback reboot, so the failed boot's log survives. A rollback or restore trial is refused on it only with `refuse_unsafe_rollback=yes` (below).

Any refusal of `stage`/`update` after it has moved the previous release's boot files off the ESP puts them back, so the room keeps its one fallback.

`check-kept [--json] [--max-age S]` runs the invariant on every kept root this room could roll back or restore to (not the running root, which integrity checks). The result is cached in `/var/lib/smartroomos/release-kept-roots.json` and shown, as information, in `status --json` (`keptRootsCheck`, and `rootCheck` on each release row); `status` never walks a root. `smartroomos-integrity`'s live check runs it at most every six hours. Rollback and restore do not refuse on it yet. When another `smartroom-release` holds the btrfs top level (an update receiving its root), `check-kept` does not wait: it prints `busy: true` with `ok: null`, caches nothing, and the next run checks.

Every command that uses the btrfs top level (`stage`, `rollback`, `restore`, prune, `discard`, `build-release`, `doctor`, `migrate-confirm`, `check-kept`) takes one exclusive lock first, a flock on `/run/smartroom-release/top.lock`. The holder mounts the top level at `/run/smartroom-release/top` and unmounts it when done, so no process unmounts it under another. A mount left by a killed holder is taken over and unmounted by the next one.

The firmware's `check-image`, the installer's `desk-check`, `smartroomos-integrity` and `smartroomos-release-sign` call this same command; the firmware's `overlay/usr/bin/smartroom-release` is a byte copy of this file.

## Room pages as a trial condition (written, off)

Waiting on the operator: should a trial also need "the room pages are up when a display is connected"? On `2026.11.24-studio-edge-c` the kiosk Chromium could not start (a missing library), and the trial still passed: health samples the Room Controller's connection, the network and the display count, and the Room Controller reported `chrome=yes` (installed, not running).

The condition is written and tested, and off: `require_room_pages=no` (default) in `/etc/smartroomos/release.conf`. A room page is a kiosk Chromium main process of the Room Controller user whose URL names a room role (`?role=presentationDisplay`). With `yes`, a sample whose room has a connected display (DRM) and no room page counts as not healthy, so a trial whose pages never start ends in `health-timeout` and rolls back (`last_result.room_pages_required`). `always` requires a page also without a DRM display: a test Studio's screens are Hyprland headless outputs, which DRM does not count, so `yes` would not have caught edge-c on the Home Studio, and `always` would have.

## Refusing a rollback to an unsafe root (written, off)

Waiting on the operator. Default `refuse_unsafe_rollback=no`: as before WS17, `rollback` and `restore` are never refused on the invariant. They arm a kept root without checking it, and their trial (kind `rollback`) checks the root at boot but does not roll back on it: the result goes in `status --json` (`release.root_check` with `ok: false`, `refused: false`, `kind`, `findings`, `note`), event `unsafe-rollback-kept` (once per trial), and the trial goes on to its health result. Integrity shows that record as information (`release_root_check`); its own check of the running root still reports `unsafe-root`. Update trials refuse an unsafe root whatever the switch says.

With `refuse_unsafe_rollback=yes` in `/etc/smartroomos/release.conf`, `rollback` and `restore` check the target first and refuse before anything is armed (`last_result` `refused`, `unsafe-root`, event `rollback-refused`), and a rollback trial whose root fails is sent back (`unsafe-root`), as an update trial is. A check that cannot run does not refuse. `check-kept` shows today which kept roots would be refused. The Mini's `smartroomos-boot-commit` does the same for a snapshot restore (`root_check_refused=no|yes` in its marker).

A rollback or restore that fails after moving the previous release's boot files off the ESP puts them back, as `stage` does.

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
smartroom-release check-root [ROOT] [--json]   the root invariant (exit 1 unsafe, 3 the check could not run)
smartroom-release check-kept [--json] [--max-age S]   the invariant on the kept rollback roots (information)
smartroom-release build-release ...     make a release (see above)
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
ran the trial image but Limine picked the configured entry), `unsafe-root` (the trial root
fails the root invariant; checked before the health wait and again before mark-good).

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
a real gpg key. `test/test_root_invariant.py` holds the invariant's cases (fake roots with
planted owners, synthetic btrfs send streams, real owners in a user namespace) and the
refusals of build-release, stage and the trial on both lines. The hardware cycle on a Studio is described in the ws6 report in the
firmware repo (`docs/update-rollback.md`).
