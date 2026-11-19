# SmartRoom carry on omarchy-mac-pkgs

`smartroom/edge` (this branch) is `smartroom/main` at `9540b55` plus the edge
boot packages and an offline `aura-try` prototype. `smartroom/main` stays the
stable line. Do not merge this branch back into `smartroom/main`.

`omarchy-apple-silicon-boot-check` already accepts `aura` as the bootloader
for `linux-aurora` (it refuses a root that has both `aura` and
`m1n1-aurora`). No change to that check was required. The edge image installs
`aura` from `smartroom/pkgbuilds/aura` (ludagoo/aura `ave/t6021-fw`: aura
main plus the hand-off of both t6021 encoders' firmware) and `linux-aurora`
7.3 from `smartroom/pkgbuilds/linux-aurora` (ludagoo/linux `ave/t6021-j475c`:
the Aurora encoder stack on aurora-silicon `integration/aurora`, J475c
auxiliary DMA blocks left disabled). Each commit is named once, as `_commit`
at the top of its PKGBUILD; the aura qualification record gets it from there.
Both are signed into the SmartRoom repo in place of the channel packages.
The kernel is not the omarchy-pkgs#3025 pin `4454eda`: cherry-picking the
encoder commits onto that tip conflicted in the ave driver, so the package
builds the ludagoo tree, which has those commits and, in its base, the
AQC113 own-address filter, and does not have the pin's M3/Neo carry.

`smartroom/aura-try/` is the first rollback prototype from the design in
`~/smartroom-rollback/DESIGN.md`. It arms a marker, checks health on a fake
clock, marks good by write-beside, and rolls back by leaving the configured
file alone. `smartroom/aura-try/test-all.sh` runs offline. It does not touch
a real EFI partition and it does not reboot.

`user4k.patch` in the omarchy-mac-boot recipe is the stable line's (see
Base): the upstream console change, its cases after upstream's M4 cases,
and one more that checks user4k leaves `panic=10` on the default command line.
The Limine boot test reports an Asahi kernel for the one console-leaf call
that has no boot-update environment; Aurora's user4k cases stay in the
console test.

`omarchy-apple-silicon-boot-check` still requires a blake2 hash on a Limine
entry. It skips that compare only when the last `ENABLE_VERIFICATION` is
`no` (packaged conf, then drop-ins, then `/etc/default/limine`) and the path
is exactly `boot():/EFI/Linux/omarchy_<kernel>.efi`. SmartRoom's drop-in is
what sets `no`. The UKI must still exist and carry the installed kernel, and
a hash that is present is still compared. An entry with no hash and no `no`
still fails.

`smartroom/main` is what a stable SmartRoom Firmware boot package builds from:
omacom's `main` (mirrored here as `main`, fast-forward only) plus the small
patches below, rebased, never merged. Rooms run no desktop, so the only
change to Omarchy's boot logic is what a headless room needs; everything else
is copied unchanged.

## Base

| | |
| --- | --- |
| Base commit | `95b0dd9776c7e24e687b62665d152e885a453777` (omacom/omarchy-mac-pkgs main, "Merge pull request #164 … docs/manual-hardware-truth") |
| Last sync | 2026-11-20 (from `63a6941`, 23 commits: the M4 display switches in `setup/grub-console.sh`, `update-verify`'s owner-managed boot chains, the Limine sync skip after a snapper cleanup, the integration fixtures). Sync at least once a month and whenever omacom touches a file this carry patches. |
| Stable channel today | `omarchy-mac-boot 20261104-1` = omarchy-mac-pkgs `7e50e937` + `user4k.patch` (omacom/omarchy-pkgs recipe). Our base is newer than that pin: it also has the changes listed under "Last sync". `user4k.patch` (omacom/omarchy-mac-pkgs#46, still open) is carried onto our base: the same `grub-console.sh` change, its test cases after upstream's M4 cases. |

## Carried patches

| # | What | Why | Upstream PR candidate? | Drop when |
| --- | --- | --- | --- | --- |
| 1 | `CARRY.md`, `smartroom/sync-upstream.sh`, `smartroom/upstream-drafts/` | This file, the sync script, and the PR texts for #2 and #3 (drafts; Lucas sends them to omacom) | No (ours) | Never |
| 2 | `omarchy-mac-boot/setup/limine-boot.sh`: keep a `TARGET_OS_NAME` the image (or an admin) already set in `/etc/default/limine`, default `Omarchy`; key the menu entry by that name. `test/apple-limine-boot-test.sh`, `test/apple-grub-console-test.sh`, `test/mac-limine-cmdline-test.sh`: the image's checksum drop-in and `panic=10` survive that first-boot rewrite | The Limine entry must say "SmartRoom Firmware"; without this, first boot's setup-boot rewrites it to "Omarchy". The same rewrite keeps only `TARGET_OS_NAME`, so `ENABLE_VERIFICATION=no` has to live in a drop-in the leaf does not touch (`/etc/limine-entry-tool.d/`, loaded after `/etc/limine-entry-tool.conf`'s `yes` and before `/etc/default/limine`). `panic=10` is a word of `GRUB_CMDLINE_LINUX_DEFAULT`: the console leaf does not rewrite that line, and `omarchy-mac-limine-cmdline` copies it onto the UKI line. The leaf's own test runs both scripts on that built configuration and checks the drop-in still wins (the menu gets no checksum; without the drop-in the packaged `yes` puts one on) and that `panic=10` is on the derived UKI line | Yes: "let an image name its Limine entry" | omacom takes it, or adds another way to name the entry |
| 3 | `omarchy-mac-boot/.../omarchy-mac-first-boot`: a headless image (`/etc/omarchy-mac-boot/headless`) stages no owner provisioning, enables no display manager and never takes tty1 on a failure (the unit fails; the next boot retries) | Rooms have no person and no display; stock first boot hard-fails without the runtime's owner provisioning and otherwise waits on tty1 forever | Yes: "first boot for headless images" | omacom takes it |
| 4 | `smartroom-omarchy-helpers/`: a tiny package of the omacom/omarchy runtime files the boot package, the image builder and first boot read, **copied unchanged** (tag in `SOURCE`, list in `FILES`, `sync-from-runtime` to refresh) | Lets `omarchy-mac-boot` drop its `omarchy` dependency (the full desktop) without reimplementing anything. One omarchy-settings file is deliberately left out: the mkinitcpio HOOKS baseline `00-omarchy-hooks.conf`, which names `plymouth` on a Mac; without it mkinitcpio's default plus omarchy-mac-boot's 90-95 drop-ins give Omarchy's exact hook list minus `plymouth` (checked on the stock image) | No (ours) | omacom splits these helpers out of `omarchy` themselves |
| 5 | `smartroom/pkgbuilds/`: the omacom/omarchy-pkgs recipe for `omarchy-mac-boot`, unchanged except source (this fork), `depends` (`smartroom-omarchy-helpers` + `sudo` instead of `omarchy`; `asahi-scripts` as the stable 20261104-1 has it) and pkgver/_commit from the build; and the helpers' recipe | omacom builds its packages in omarchy-pkgs from omacom main; ours build from this fork | No (ours) | Never |
| 6 | `smartroom-boot-os/` and its recipe: `smartroom-boot-os macos\|firmware [--once] [--reboot]`, a thin wrapper around Omarchy's `aurora-bless` (depends on it) | Zoom-room Macs switch between SmartRoom Firmware and macOS (Zoom Rooms) from Linux with no macOS password. Omarchy already ships `aurora-bless` (its asahi-bless fork) in every Mac image for exactly this; the wrapper only picks the volume by name, clears a pending next start when setting a default, and reads the result back | No (ours) | Never |

Nothing else differs from omacom (#6 is a new package of ours beside theirs). In particular the initramfs, in-place
encryption (still switchable: `omarchy/install.conf` on the ESP, `encrypt=1`),
vendor firmware, Limine activation, snapshots and factory reset are
upstream's code.

### Why patch the boot package instead of installing `omarchy` and turning things off

Lucas's final model (2026-11-17): rooms never run `omarchy-update`; they take
our own fixed releases. So "an Omarchy update re-enables sddm" is not a risk,
and the deciding question is what keeps this fork easy to sync. Dropping one
dependency and adding a package of unchanged copies touches no upstream file
but the recipe; installing `omarchy` would put the whole desktop (hyprland
session, quickshell, uwsm, sddm, plymouth, owner provisioning, its
`omarchy-apply-system` defaults) on every room, and each would need its own
"turn it off" patch, all of which move with every Omarchy release.

## Branches

- `main`: an exact mirror of omacom's `main`. Fast-forward only, never commit to it.
- `smartroom/main`: `main` + the carry above. Rebased, never merged. Before
  force-pushing it, tag the old tip `sr/prev-<date>`; never delete `sr/*` tags.

## Syncing with upstream

```sh
smartroom/sync-upstream.sh            # fast-forward main, show how far behind the carry is
smartroom/sync-upstream.sh --rebase   # rebase smartroom/main locally, print the range-diff
smartroom/sync-upstream.sh --push     # tag sr/prev-<date> and force-push
```

After a sync: check that `smartroom/pkgbuilds/omarchy-mac-boot/user4k.patch`
still applies (`patch -d omarchy-mac-boot --dry-run -Np2 <…/user4k.patch`)
and run the console test on the patched copy, update "Base commit" and "Last
sync" above, run `omarchy-mac-boot/test/all` and
`OMARCHY_TEST_RUNTIME=<omarchy checkout at the tag in smartroom-omarchy-helpers/SOURCE> smartroom-omarchy-helpers/test/all`;
when omacom/omarchy-pkgs moves its `omarchy-mac-boot` recipe, diff it against
`smartroom/pkgbuilds/omarchy-mac-boot/PKGBUILD`; when the stable channel moves
to a new Omarchy release, run `smartroom-omarchy-helpers/sync-from-runtime`.
Then rebuild with ludagoo/omarchy-mac-installer `smartroom/build-packages`.

GitHub Actions are disabled on this fork (no inherited workflow can publish
anything); sync by hand with the script. `.github/workflows/smartroom-ci.yml`
(ours) runs every package's `test/all` and `smartroom/test/all` in upstream
`tests.yml`'s pinned Arch container on pushes to `smartroom/main`,
`smartroom/edge` and `fix/**`, read-only and without secrets;
`smartroom-omarchy-helpers` is compared with omacom/omarchy at its `SOURCE`
commit. It runs once Lucas enables Actions. To enable: turn Actions on, then
at once disable every inherited workflow except `SmartRoom checks`
(`gh workflow disable`), because their files on `main` would otherwise run on
upstream's triggers.

`omarchy-mac-first-boot` also populates the `smartroom` keyring when the
image ships `/usr/share/pacman/keyrings/smartroom.gpg`: a SmartRoom release
image (ludagoo/omarchy-mac-installer, PROGRAM decision 4) takes every package
from one repository signed with the SmartRoom package key, and each Mac's
first boot makes its keyring from that directory. Stock images ship no such
file and populate what they did before (`mac-first-boot-test.sh`,
`keyring-smartroom`).

## Rules

- Patches by an AI agent carry `Assisted-by: Claude:claude-opus-5-5` and no
  `Signed-off-by`. Upstream PRs go to omacom only (never AsahiLinux), and only
  as drafts Lucas reviews and sends.
