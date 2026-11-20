# omarchy-chromium 148 with V4L2 (not shipped)

The earlier room browser attempt, kept so the studio-build tree it came from
can be rebuilt. No image ever shipped it: the stable image installs Omarchy's
`omarchy-chromium-bin`, and the edge image installs `chromium-smartroom` 158
(`../pkgbuilds/chromium-smartroom`), which replaces it.

It is ludagoo/omarchy-chromium `smartroom/v4l2` at `fec767d97b68` ("Keep
VA-API Fourcc conversion when V4L2 is also enabled", pushed) plus what was
left uncommitted in studio-build's `~/fw-build/omarchy-chromium` on
2026-11-19:

- `PKGBUILD.arm64.diff`: `package()` enters `$srcdir/chromium-$pkgver`.
- `009-glibc-2.43-sys-seccomp.patch`, `010-rust-1.99-qr-code.patch`: build
  fixes for glibc 2.43 and Rust 1.99.
- Downloads, not kept here: `chromium-148.0.7778.96-lite.tar.xz`
  (sha256 `694d4e0269e11056c6dff748da7e8354bfbf90da7ce8f7467a0acfe2994a8688`)
  and `chromium-launcher-8.tar.gz`
  (sha256 `213e50f48b67feb4441078d50b0fd431df34323be15be97c55302d3fdac4483a`).
