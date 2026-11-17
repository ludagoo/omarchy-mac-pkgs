# smartroom-omarchy-helpers

SmartRoom Firmware only (ludagoo fork). Not an Omarchy package.

`omarchy-mac-boot` depends on `omarchy`, the full desktop. SmartRoom rooms
run no desktop, so our build of `omarchy-mac-boot` depends on this package
instead. It holds only the runtime files the boot package, the image builder
and the image's first boot read, **copied unchanged** from omacom/omarchy at
the tag in `SOURCE` (`FILES` lists each one and why). It conflicts with
`omarchy` and `omarchy-settings`, which own the same paths.

- Commands omarchy-mac-boot runs: `omarchy-hw-platform`,
  `omarchy-hw-aarch64-apple`, `omarchy-hw-apple-silicon`, `omarchy-cmd-present`.
- The image build's Limine activation and the first boot's deferred hardware
  setup: `omarchy-lifecycle-dispatch`, `omarchy-provision-hardware`, its two
  helpers, `install/hardware/platform-setup.sh` and its unit.
- From omarchy-settings: the Limine menu template, the Apple pacman templates
  (stable) and the mkinitcpio module drop-ins. Not the HOOKS baseline
  (`00-omarchy-hooks.conf`), which names `plymouth` on a Mac: without it the
  hook list is Omarchy's exactly, minus `plymouth` (rooms have no splash).

Update: `./sync-from-runtime ~/src/omarchy vX.Y.Z`, review the diff, bump
`version`, run `test/all` with `OMARCHY_TEST_RUNTIME` set.
