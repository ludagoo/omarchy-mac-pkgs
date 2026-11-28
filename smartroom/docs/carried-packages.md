# Maintained process for SmartRoom carried packages

SmartRoom maintains its own edge-line packages (`linux-aurora`, `aura`,
`mesa-aurora`, the network camera module `v4l2loopback-aurora`, and the prebuilt room browser `chromium-smartroom`, alongside the
boot packages listed in `CARRY.md`) for as long as rooms require patches not yet
landed in Omarchy's published channel packages. Switching to an upstream Omarchy
package happens only once that channel package carries every required fix and
passes Studio qualification.

## 1. What we carry and why

| Package | Repo / Branch | Carried changes and why | Upstream PR links (drop condition) |
| --- | --- | --- | --- |
| `linux-aurora` (`linux-aurora-headers`) | `ludagoo/linux` (`smartroom/edge-kernel-3`) | `aurora-silicon/linux` `integration/aurora` + T6021 hardware video encoder stack (auxiliary DMA blocks disabled so VENC domains power down cleanly), J475c SMC sensor discovery + power rails, `apple-ave` `busy_ns`/`active_sessions`/`frames` sysfs counters, and J475c `dcpext2`/`dcpext3` wiring across all four rear USB-C ports (`status = "disabled"` until `aura` reserves firmware) for three simultaneous displays (HDMI projector + two USB-C TVs). Built here rather than cherry-picking onto the `omacom/omarchy-pkgs#3025` pin (`4454eda`) because the encoder stack conflicted in `ave`. | Encoder stack: [aurora-silicon/linux#2373](https://github.com/aurora-silicon/linux/pull/2373), [#2374](https://github.com/aurora-silicon/linux/pull/2374), [#2375](https://github.com/aurora-silicon/linux/pull/2375), [#2376](https://github.com/aurora-silicon/linux/pull/2376).<br>T602x disabled peripherals base: [aurora-silicon/linux#1149](https://github.com/aurora-silicon/linux/pull/1149) (merged).<br>Multi-display / dcpext2-3 / no-monitor: [omacom/linux-aurora#5](https://github.com/omacom/linux-aurora/pull/5), [#357](https://github.com/omacom/linux-aurora/pull/357), [#460](https://github.com/omacom/linux-aurora/pull/460), [#462](https://github.com/omacom/linux-aurora/pull/462), [#467](https://github.com/omacom/linux-aurora/pull/467), [aurora-silicon/linux#1684](https://github.com/aurora-silicon/linux/pull/1684), [#1771](https://github.com/aurora-silicon/linux/pull/1771), [#1812](https://github.com/aurora-silicon/linux/pull/1812), [#1871](https://github.com/aurora-silicon/linux/pull/1871).<br>Channel pin context: [omacom/omarchy-pkgs#3025](https://github.com/omacom/omarchy-pkgs/pull/3025). |
| `aura` | `ludagoo/aura` (`ave/t6021-fw`) | `aura` main plus preloaded T6021 encoder firmware hand-off to Linux; also executes `dt_reserve_dcpext_firmware()` on T6021 to reserve `dcpext0..3` ASC firmware, set `apple,firmware-compat`, and flip `m2_dcpext2`/`m2_dcpext3` to `okay`. Uses `smartroom/pkgbuilds/aura/build-qualification.json` and `validate-qualification.py`. | Upstream bootloader pin: [omacom/omarchy-pkgs#3025](https://github.com/omacom/omarchy-pkgs/pull/3025); `aurora-silicon/aura` encoder hand-off when upstreamed. |
| `mesa-aurora` (`vulkan-aurora`) | `omacom/mesa` (`carry/edgeB-7.3`) | Unchanged copy of the `omacom/omarchy-pkgs#3025` (`edgeB2`) recipe at `23791c134af`. The 7.3 kernel names the GPU DRM driver `"aurora"`, whereas the older published edge Mesa opened only `"asahi"` and broke EGL/Hyprland. | Channel pin: [omacom/omarchy-pkgs#3025](https://github.com/omacom/omarchy-pkgs/pull/3025); M3 carries noted in `smartroom/pkgbuilds/mesa-aurora/PKGBUILD` (`aurora-silicon/mesa` PRs `#415`, `#416`). Drop when Omarchy's edge channel ships this Mesa or newer. |
| `omarchy-mac-boot`, `smartroom-omarchy-helpers`, `smartroom-boot-os` | `ludagoo/omarchy-mac-pkgs` (`smartroom/edge`) | Headless boot flow (`TARGET_OS_NAME` preserved across first boot, no owner provisioning/TTY1 hang), extracted unchanged runtime helpers without desktop `omarchy`, and `aurora-bless` wrapper. | See `CARRY.md` table (`smartroom/upstream-drafts/`). |
| `chromium-smartroom` | Built on the aarch64 build host | Arch Linux ARM Chromium 158 with direct V4L2 hardware decode and encode (`omarchy-chromium-bin` replacement). Pinned by SHA-256 in `omarchy-mac-installer` (`smartroom/room/prebuilt.sha256`). | Maintained separately until upstream Chromium/Omarchy builds include V4L2 encode/decode parity. |
| `v4l2loopback-aurora` | Upstream [v4l2loopback](https://github.com/v4l2loopback/v4l2loopback) tag `v0.15.4` (sha256 pinned in `smartroom/pkgbuilds/v4l2loopback-aurora/PKGBUILD`), built against our `linux-aurora-headers` | The room's network camera: one loopback device (`/dev/video30`, "Network camera") that the Room Controller feeds from an RTSP camera with ffmpeg and Chromium lists as a webcam. A prebuilt module for exactly one `linux-aurora` build (no dkms on a room); its `depends` pins that kernel. | Not a patch: kept for as long as rooms have a network camera. Drop the per-kernel rebuild if the channel ever ships the module for our kernel. |

## 2. Reproducible builds

All aarch64 package builds run on a native aarch64 build host (never on an Intel Mini), with
15 GiB RAM (`OMARCHY_BUILD_JOBS=3` for `linux-aurora` and `aura`).

1. **Kernel (`linux-aurora`, `linux-aurora-headers`)**:
   - Before packaging, DT changes must pass `scripts/dtc/apple-dt-check.sh <BASE> HEAD <WORKDIR>` (`CHECK_DTBS=y` across all Apple DTBs plus `dt_binding_check`).
   - Push the target commit to `ludagoo/linux` so `_commit` in `smartroom/pkgbuilds/linux-aurora/PKGBUILD` is reachable by URL.
   - Bump `_aurorarel` (`0sredge<N>`, which sorts below `7.3.0.aurora<N>`) or `pkgrel` whenever `_commit` changes so `pacman` sees an upgrade and `uname -r` (`7.3.0-${_aurorarel}-${pkgrel}-ARCH`) tracks the build.
   - Build and sign with the SmartRoom package key (`SMARTROOM_PKG_KEY`):
     ```sh
     cd smartroom/pkgbuilds/linux-aurora
     OMARCHY_BUILD_JOBS=3 PKGDEST=/path/to/out PKGEXT='.pkg.tar.zst' \
       makepkg --force --cleanbuild --syncdeps --noconfirm --sign --key "$SMARTROOM_PKG_KEY"
     ```
   - `prepare()` verifies `HEAD == $_commit`, pins Rust 1.85.0 + LLVM 18, builds `aurora-bindgen`, enforces `-ARCH` kernelrelease, and records `/usr/share/doc/linux-aurora/smartroom-kernel-commit`.
   - Whenever `uname -r` changes (a new `_commit`, `_aurorarel` or `pkgrel`), rebuild `v4l2loopback-aurora`: copy linux-aurora's `_auroraver`, `_aurorarel` and `pkgrel` into `_auroraver`, `_aurorarel` and `_aurorapkgrel` in `smartroom/pkgbuilds/v4l2loopback-aurora/PKGBUILD` (`smartroom/test/v4l2loopback-aurora-recipe-test.sh` fails until they match). `smartroom/build-packages` in the installer builds it right after the kernel, against the `linux-aurora-headers` it just built (`AURORA_KERNEL_BUILD_DIR`, `LLVM=/usr/lib/llvm18/bin/`); its `check()` refuses a module whose `modinfo -F vermagic` is not the new release. A release image without it fails `desk-check` (network camera).
2. **Full local `smartroom` repository**:
   - In `ludagoo/omarchy-mac-installer` (`smartroom/edge`):
     ```sh
     SMARTROOM_PKG_KEY=<fpr> \
     SMARTROOM_EDGE_BOOT_PACKAGES=/path/to/prebuilts \
     SMARTROOM_ROOM_PACKAGES=/path/to/chromium-pkg \
       smartroom/build-packages OUT_PKGS <omarchy-mac-pkgs-commit>
     ```
   - Without `SMARTROOM_EDGE_BOOT_PACKAGES`, `smartroom/build-packages` compiles `aura`, `linux-aurora`, `v4l2loopback-aurora` (against the headers it just built), and `mesa-aurora` directly from their pinned PKGBUILDs; with it, that directory must also hold `v4l2loopback-aurora` for the same kernel into `OUT_PKGS/repo/smartroom.db` and records `omarchy_mac_pkgs_commit` in `OUT_PKGS/SOURCE`.

## 3. Re-syncing with upstream

1. **Packaging repo (`omarchy-mac-pkgs`)**:
   - Run `smartroom/sync-upstream.sh` to fast-forward the `main` mirror to `omacom/omarchy-mac-pkgs` and see what `smartroom/edge` lacks; `--merge` merges it into a local `sync/upstream-<date>` branch to test and review.
   - Diff upstream `omacom/omarchy-pkgs` PKGBUILDs (`linux-aurora`, `aura`, `mesa-aurora`, e.g., from PR `#3025`) against `smartroom/pkgbuilds/*` (`config`, `configure.sh`, `validate-config.py`, `bindgen-kernel.py`, `validate-qualification.py`).
2. **Kernel (`ludagoo/linux`)**:
   - Fetch the new `aurora-silicon/linux` `integration/aurora` (or `omacom/linux-aurora`) base, replay our carried series (`ave/t6021-j475c`, `smc/j475c-sensors`, `ave/usage-counter`, and `t6021-j475c` `dcpext2`/`dcpext3` DT wiring), dropping any commit whose upstream PR has merged.
   - Re-run `scripts/dtc/apple-dt-check.sh` and `make W=1`, push the rebased branch, update `_commit` and `_aurorarel` in `smartroom/pkgbuilds/linux-aurora/PKGBUILD`, and run `smartroom/test/linux-aurora-pkg-test.sh`.

## 4. Getting into a pinned release

1. All carried commits (`_commit` in `aura`, `linux-aurora`, `mesa-aurora` PKGBUILDs and SHA-256 pins in `smartroom/room/prebuilt.sha256`) are committed to `ludagoo/omarchy-mac-pkgs` and `ludagoo/omarchy-mac-installer` before building a release candidate.
2. Build or copy signed packages into `OUT_PKGS` via `smartroom/build-packages OUT_PKGS <commit>`.
3. Build the release image with pinned channel inputs (`image-builder/bin/mac-image-inputs resolve` or an existing pinned inputs file) rather than floating channel tips:
   ```sh
   smartroom/build-image --inputs INPUTS --recovery-app REC --cache CACHE \
     --packages OUT_PKGS --firmware <pinned-fw-commit> --keys AUTHORIZED_KEYS OUT_IMG
   ```
   `build-image` records `installer_fork`, `firmware_git`, `omarchy_mac_pkgs_commit`, and the active bootloader into `/usr/share/smartroom/build-info` inside the image.
4. Run `sudo smartroom/desk-check OUT_IMG/*.zip WORKDIR` and `bash smartroom/test/all` in `omarchy-mac-installer`; every check (kernel release, `smartroom-kernel-commit`, `build-qualification.json`, GPU/Mesa driver match, `dcpext2`/`dcpext3` DT wiring, AVE encoders/DMA blocks, SMC sensors, Limine zero-touch boot, Recovery branding) must pass before promoting the release.
