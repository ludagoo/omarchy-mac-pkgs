#!/usr/bin/env python3
"""The root invariant (smartroom-release check-root) and every place that refuses on it:
build-release, stage, and the trial's health-run. One set of cases for every caller
(fw check-image, installer desk-check and smartroomos-integrity run this same file)."""
import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_release import CMDLINE, TOOL, MiniWorld, World, plant_system, sr


def fake_root(test) -> Path:
    """A clean root, as the runner sees it (the runner plays root through root_ids)."""
    root = Path(tempfile.mkdtemp(prefix="srel-root-"))
    test.addCleanup(shutil.rmtree, root, True)
    root.chmod(0o755)
    for d in ("usr/bin", "usr/lib/systemd/system", "usr/share", "etc/systemd/system", "home/smartroomcontroller",
              "opt/smartroom/logs", "var/lib/private/speakersafetyd", "tmp", "var/tmp", "proc", ".snapshots/1"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "usr/sbin").symlink_to("bin")
    (root / "usr/bin/sudo").write_text("#!/bin/sh\n")
    (root / "etc/pacman.conf").write_text("[options]\n")
    plant_system(root)
    return root


class Ids:
    """root_ids for a fake root: the runner is root, plus planted owners."""

    def __init__(self, owners=None):
        self.owners = owners or {}

    def __call__(self, rel, uid, gid):
        if rel in self.owners:
            return self.owners[rel]
        return (0 if uid == os.getuid() else uid), (0 if gid == os.getgid() else gid)


def rules(report):
    return {(f["rule"], f["path"]) for f in report.findings}


class Invariant(unittest.TestCase):
    def check(self, root, owners=None):
        return sr.check_root_tree(str(root), Ids(owners))

    def test_a_clean_root_passes(self):
        root = fake_root(self)
        report = self.check(root, {
            "home/smartroomcontroller": (1000, 1000),           # homes are the users'
            "opt/smartroom": (1000, 1000),                      # the Room Controller's own directory
            "opt/smartroom/logs": (1000, 1000),
            "var/lib/private/speakersafetyd": (61234, 61234),   # a DynamicUser state dir
            ".snapshots/1": (1000, 1000),                       # snapper history is not walked
        })
        self.assertTrue(report.ok, report.text())
        self.assertEqual(report.rc_uid, 1000)

    def test_a_system_file_owned_by_uid_1000_fails(self):
        root = fake_root(self)
        report = self.check(root, {"usr/bin/sudo": (1000, 1000)})
        self.assertFalse(report.ok)
        self.assertIn(("rc-owner", "/usr/bin/sudo"), rules(report))

    def test_any_login_id_fails_not_only_the_room_controller(self):
        root = fake_root(self)
        report = self.check(root, {"etc/pacman.conf": (0, 1001), "usr/share": (2000, 0)})
        self.assertIn(("login-owner", "/etc/pacman.conf"), rules(report))
        self.assertIn(("login-owner", "/usr/share"), rules(report))

    def test_nobody_is_not_a_login(self):
        root = fake_root(self)
        self.assertTrue(self.check(root, {"etc/pacman.conf": (65534, 65534)}).ok)

    def test_sudoers_owned_by_1000_fails(self):
        root = fake_root(self)
        report = self.check(root, {"etc/sudoers.d/smartroomcontroller": (1000, 1000)})
        self.assertIn(("system-dir", "/etc/sudoers.d/smartroomcontroller"), rules(report))
        self.assertIn(("rc-owner", "/etc/sudoers.d/smartroomcontroller"), rules(report))

    def test_sudoers_mode_0666_fails(self):
        root = fake_root(self)
        (root / "etc/sudoers.d/smartroomcontroller").chmod(0o666)
        report = self.check(root)
        self.assertEqual(rules(report), {("system-dir", "/etc/sudoers.d/smartroomcontroller")})

    def test_etc_owned_by_the_room_controller_fails_whatever_its_number(self):
        root = fake_root(self)
        (root / "etc/passwd").write_text("root:x:0:0::/root:/bin/bash\nsmartroomcontroller:x:977:977::/h:/bin/sh\n")
        (root / "etc/group").write_text("root:x:0:\nsmartroomcontroller:x:977:\n")
        report = self.check(root, {"etc": (977, 977)})
        self.assertEqual(report.rc_uid, 977)
        self.assertIn(("rc-owner", "/etc"), rules(report))
        self.assertIn(("system-dir", "/etc"), rules(report))

    def test_top_system_directories_must_be_root_and_not_writable(self):
        root = fake_root(self)
        (root / "usr/share").chmod(0o775)
        report = self.check(root, {"": (0, 10), "usr/lib": (0, 0)})
        self.assertIn(("system-dir", "/"), rules(report))
        self.assertIn(("system-dir", "/usr/share"), rules(report))
        self.assertNotIn(("system-dir", "/usr/sbin"), rules(report))   # a symlink's mode is not a mode

    def test_a_deeper_group_writable_dir_is_not_a_system_dir(self):
        root = fake_root(self)
        (root / "usr/share/polkit").mkdir()
        (root / "usr/share/polkit").chmod(0o770)
        self.assertTrue(self.check(root, {"usr/share/polkit": (0, 102)}).ok)

    def test_visudo_failure_fails(self):
        root = fake_root(self)
        (root / "etc/sudoers.d/broken").write_text("this is not sudoers syntax (\n")
        (root / "etc/sudoers.d/broken").chmod(0o440)
        report = self.check(root)
        self.assertEqual({r for r, _ in rules(report)}, {"visudo"})

    def test_no_sudoers_fails(self):
        root = fake_root(self)
        (root / "etc/sudoers").unlink()
        self.assertIn(("sudoers-missing", "/etc/sudoers"), rules(self.check(root)))

    def test_exempt_trees_are_exempt_only_below_them(self):
        root = fake_root(self)
        report = self.check(root, {"home": (1000, 1000), "tmp": (1000, 1000),
                                   "var/lib/private/speakersafetyd": (1000, 1000)})
        self.assertEqual(rules(report), {("rc-owner", "/home"), ("rc-owner", "/tmp"),
                                         ("rc-owner", "/var/lib/private/speakersafetyd")})

    def test_json_names_the_rule_path_and_owner(self):
        root = fake_root(self)
        doc = self.check(root, {"etc/sudoers.d": (1000, 1000)}).as_dict()
        self.assertFalse(doc["ok"])
        self.assertEqual(doc["rules"], {"rc-owner": 1, "system-dir": 1})
        self.assertEqual({f["owner"] for f in doc["findings"]}, {"1000:1000"})


def stream_bytes(commands):
    """A btrfs send stream (protocol 1) from (command, [(attr, bytes)]) pairs."""
    out = [b"btrfs-stream\0", struct.pack("<I", 1)]
    for cmd, attrs in commands:
        payload = b"".join(struct.pack("<HH", a, len(v)) + v for a, v in attrs)
        out.append(struct.pack("<IHI", len(payload), cmd, 0) + payload)
    out.append(struct.pack("<IHI", 0, 21, 0))
    return b"".join(out)


def p(path):
    return (15, path.encode())


def u64(attr, n):
    return (attr, struct.pack("<Q", n))


def root_stream(owner_of_sudoers_d=0, sudoers_mode=0o440):
    """mkdir/mkfile under orphan names then rename, as btrfs send writes them."""
    cmds = [(1, [p("@r-test")])]
    for d in ("etc", "usr", "usr/bin", "etc/sudoers.d", "home", "home/smartroomcontroller"):
        cmds += [(4, [p("o%d-1-0" % len(cmds))]), (9, [p("o%d-1-0" % len(cmds)), (16, d.encode())])]
        cmds += [(19, [p(d), u64(6, 0), u64(7, 0)]), (18, [p(d), u64(5, 0o755)])]
    files = {"etc/sudoers": SUDO, "etc/sudoers.d/rc": RC, "etc/passwd": PASSWD, "etc/group": GROUP}
    for path, data in files.items():
        orphan = "o%d-2-0" % len(cmds)
        cmds += [(3, [p(orphan)]), (9, [p(orphan), (16, path.encode())]),
                 (15, [p(path), u64(18, 0), (19, data)]),
                 (19, [p(path), u64(6, 0), u64(7, 0)]), (18, [p(path), u64(5, 0o644)])]
    cmds += [(18, [p("etc/sudoers"), u64(5, 0o440)]), (18, [p("etc/sudoers.d/rc"), u64(5, sudoers_mode)]),
             (19, [p("etc/sudoers.d"), u64(6, owner_of_sudoers_d), u64(7, owner_of_sudoers_d)]),
             (19, [p("home/smartroomcontroller"), u64(6, 1000), u64(7, 1000)])]
    return stream_bytes(cmds)


SUDO = b"root ALL=(ALL:ALL) ALL\n@includedir /etc/sudoers.d\n"
RC = b"smartroomcontroller ALL=(root) NOPASSWD: /usr/bin/true\n"
PASSWD = b"root:x:0:0::/root:/bin/bash\nsmartroomcontroller:x:1000:1000::/home/smartroomcontroller:/bin/bash\n"
GROUP = b"root:x:0:\nsmartroomcontroller:x:1000:\n"


class Stream(unittest.TestCase):
    def write(self, data, zst=True):
        d = Path(tempfile.mkdtemp(prefix="srel-stream-"))
        self.addCleanup(shutil.rmtree, d, True)
        path = d / ("root.btrfs.zst" if zst else "root.btrfs")
        if zst:
            data = subprocess.run(["zstd", "-q", "-c"], input=data, capture_output=True, check=True).stdout
        path.write_bytes(data)
        return path

    def test_a_good_stream_passes(self):
        report = sr.check_root(self.write(root_stream()))
        self.assertTrue(report.ok, report.text())
        self.assertIn("@r-test", report.root)

    def test_sudoers_d_owned_by_1000_in_a_stream_fails(self):
        report = sr.check_root(self.write(root_stream(owner_of_sudoers_d=1000), zst=False))
        self.assertIn(("rc-owner", "/etc/sudoers.d"), rules(report))
        self.assertIn(("system-dir", "/etc/sudoers.d"), rules(report))

    def test_a_world_writable_sudoers_file_in_a_stream_fails(self):
        report = sr.check_root(self.write(root_stream(sudoers_mode=0o666)))
        self.assertEqual(rules(report), {("system-dir", "/etc/sudoers.d/rc")})

    def test_a_truncated_stream_is_an_error_not_a_pass(self):
        data = root_stream()[:-10]
        with self.assertRaises(sr.Fail):
            sr.check_root(self.write(data, zst=False))

    def test_the_cli_exits_1_with_json(self):
        path = self.write(root_stream(owner_of_sudoers_d=1000))
        done = subprocess.run(["python3", "-I", str(TOOL), "check-root", "--json", str(path)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertFalse(json.loads(done.stdout)["ok"])


@unittest.skipUnless(shutil.which("unshare") and subprocess.run(
    ["unshare", "--map-auto", "--map-root-user", "true"], capture_output=True).returncode == 0,
    "no user namespace with a uid range (unshare --map-auto)")
class RealOwners(unittest.TestCase):
    """The CLI on a tree with real owners (root and 1000 inside a user namespace)."""

    def run_ns(self, script):
        root = fake_root(self)
        done = subprocess.run(["unshare", "--map-auto", "--map-root-user", "bash", "-c",
                               script + f'\npython3 -I "{TOOL}" check-root --json "$0"', str(root)],
                              capture_output=True, text=True)
        return done.returncode, json.loads(done.stdout or "{}"), done.stderr

    def test_clean_and_bad(self):
        code, doc, err = self.run_ns('chown -R 0:0 "$0"; chown -R 1000:1000 "$0/home/smartroomcontroller" "$0/opt/smartroom"')
        self.assertEqual(code, 0, (doc, err))
        code, doc, err = self.run_ns('chown -R 0:0 "$0"; chown 1000:1000 "$0/etc" "$0/etc/sudoers.d/smartroomcontroller"')
        self.assertEqual(code, 1, err)
        self.assertEqual({(f["rule"], f["path"]) for f in doc["findings"]},
                         {("rc-owner", "/etc"), ("system-dir", "/etc"),
                          ("rc-owner", "/etc/sudoers.d/smartroomcontroller"),
                          ("system-dir", "/etc/sudoers.d/smartroomcontroller")})


class BuildRefuses(unittest.TestCase):
    def test_build_release_refuses_a_bad_root_and_leaves_nothing_signed(self):
        a = World(self)
        (a.prefix / "top/@/usr/lib").mkdir(parents=True)
        out = a.tmp / "out"
        out.mkdir()
        (out / "manifest.json").write_text("{}")              # an older build's files
        (out / "manifest.json.sig").write_text("old signature")
        a.host.owners = {"etc/sudoers.d": (1000, 1000)}
        code, _, err = a.run("build-release", "--id", "2026.11.30-1", "--out", str(out), "--sign-key", "X" * 40)
        self.assertEqual(code, 1)
        self.assertIn("refused", err)
        self.assertIn("/etc/sudoers.d", err)
        self.assertEqual(sorted(x.name for x in out.iterdir()), [])
        self.assertFalse(list((a.prefix / "top").glob("@build-*")))

    def test_build_release_from_an_image_root(self):
        a = World(self)
        image = a.tmp / "image-top"
        root = image / "@"
        (root / "usr/lib").mkdir(parents=True)
        (root / "usr/lib/marker").write_text("from the image\n")
        (root / "etc/default").mkdir(parents=True)
        (root / "etc/fstab").write_text("UUID=aa  /  btrfs  noatime,subvol=@  0 0\n")
        (root / "etc/default/limine").write_text(f'KERNEL_CMDLINE[default]="{CMDLINE}"\n')
        plant_system(root)
        (a.tmp / "uki.efi").write_bytes(b"uki-image")
        (a.tmp / "boot.bin").write_bytes(b"stage2-image")
        out = a.tmp / "out"
        args = ["build-release", "--id", "2026.11.30-img", "--out", str(out), "--source-path", str(root),
                "--line", "studio", "--uki-from", str(a.tmp / "uki.efi"), "--boot-from", str(a.tmp / "boot.bin"),
                "--source-info", "firmware=abc123", "--source-info", "pkgs=def456"]
        code, _, err = a.run(*args)
        self.assertEqual(code, 0, err)
        m = json.loads((out / "manifest.json").read_text())
        self.assertEqual((m["line"], m["source"]), ("studio", {"firmware": "abc123", "pkgs": "def456"}))
        self.assertFalse(list(image.glob("@build-*")))
        b = World(self)
        code, _, err = b.run("update", str(out), "--unsigned")
        self.assertEqual(code, 0, err)
        # the same image root with a bad owner: refused
        a.host.owners = {"usr/lib/marker": (1000, 1000)}
        code, _, err = a.run(*args)
        self.assertEqual(code, 1)
        self.assertFalse((out / "manifest.json").exists())
        self.assertFalse((out / "root.btrfs.zst").exists())

    def test_source_path_needs_the_boot_files(self):
        a = World(self)
        code, _, err = a.run("build-release", "--id", "x-1", "--out", str(a.tmp / "o"),
                             "--source-path", str(a.tmp), "--line", "studio")
        self.assertEqual(code, 1)
        self.assertIn("--uki-from", err)


class StageRefuses(unittest.TestCase):
    def test_a_release_root_with_bad_owners_is_never_armed(self):
        w = World(self)
        w.host.owners = {"usr/lib/marker": (1000, 1000)}
        code, _, err = w.run("update", str(w.release()), "--unsigned")
        self.assertEqual(code, 1)
        self.assertIn("/usr/lib/marker", err)
        self.assertFalse((w.prefix / "top/@r-2026.11.21-1").exists())
        self.assertFalse((w.esp / "aura-try").exists())
        st = w.state()
        self.assertIsNone(st.get("trial"))
        self.assertEqual((st["last_result"]["result"], st["last_result"]["reason"]), ("refused", "unsafe-root"))


class TrialRefuses(unittest.TestCase):
    def armed(self, world):
        code, _, err = world.run("update", str(world.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        world.trial_boot()

    def test_a_trial_root_that_fails_the_invariant_rolls_back_at_once(self):
        w = World(self)
        self.armed(w)
        w.host.owners = {"etc": (1000, 1000)}
        start = w.host.clock
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(w.host.reboots, 1)
        self.assertLess(w.host.clock - start, 300)            # no five-minute wait first
        st = w.state()
        self.assertIsNone(st["trial"])
        self.assertEqual(st["configured"]["release"], sr.INSTALLED)
        self.assertEqual((st["last_result"]["result"], st["last_result"]["reason"]), ("rolled-back", "unsafe-root"))
        self.assertIn("/etc", st["last_result"]["message"])
        self.assertEqual(st["last_result"]["findings"][0]["path"], "/etc")
        # ops reads status --json: the reason is there
        code, out, _ = w.run("status", "--json")
        self.assertIn("unsafe-root", out)
        # the room boots the configured release again; it stays there
        w.back_on_configured()
        w.host.owners = {}
        code, _, _ = w.run("health-run")
        self.assertEqual((code, w.host.reboots), (0, 1))
        self.assertEqual(w.state()["configured"]["release"], sr.INSTALLED)

    def test_a_root_spoiled_during_the_health_window_is_not_kept(self):
        w = World(self)
        self.armed(w)
        real = w.host.check_root
        calls = []

        def second_fails(path):
            calls.append(path)
            if len(calls) == 2:
                w.host.owners = {"etc/sudoers": (1000, 1000)}
            return real(path)

        w.host.check_root = second_fails
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(w.state()["last_result"]["reason"], "unsafe-root")
        self.assertEqual(w.state()["configured"]["release"], sr.INSTALLED)

    def test_a_good_trial_is_still_kept(self):
        w = World(self)
        self.armed(w)
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 0)
        self.assertEqual(w.state()["configured"]["release"], "2026.11.21-1")

    def test_the_mini_line_refuses_the_same_way(self):
        w = MiniWorld(self)
        code, _, err = w.run("update", str(w.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        w.trial_boot()
        w.host.owners = {"etc/sudoers.d/smartroomcontroller": (1000, 1000)}
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(w.state()["last_result"]["reason"], "unsafe-root")
        self.assertIsNone(w.state()["trial"])


if __name__ == "__main__":
    unittest.main()
