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
from unittest import mock

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

    def test_nobody_owns_nothing_outside_etc_usr_opt(self):
        root = fake_root(self)
        (root / "var/lib/nobody").mkdir(parents=True)
        self.assertTrue(self.check(root, {"var/lib/nobody": (65534, 65534)}).ok)

    def test_a_system_user_owns_nothing_under_etc_usr_opt(self):
        root = fake_root(self)
        (root / "var/lib/polkit").mkdir(parents=True)
        report = self.check(root, {"etc/pacman.conf": (102, 0), "usr/share": (65534, 0),
                                   "usr/bin/sudo": (0, 102),             # a system group is fine
                                   "var/lib/polkit": (102, 102)})        # outside etc/usr/opt is fine
        self.assertEqual(rules(report), {("system-owner", "/etc/pacman.conf"), ("system-owner", "/usr/share"),
                                         ("system-dir", "/usr/share")})

    def test_sudoers_owned_by_1000_fails(self):
        root = fake_root(self)
        report = self.check(root, {"etc/sudoers.d/smartroomcontroller": (1000, 1000)})
        self.assertIn(("system-dir", "/etc/sudoers.d/smartroomcontroller"), rules(report))
        self.assertIn(("rc-owner", "/etc/sudoers.d/smartroomcontroller"), rules(report))

    def test_sudoers_mode_0666_fails(self):
        root = fake_root(self)
        (root / "etc/sudoers.d/smartroomcontroller").chmod(0o666)
        report = self.check(root)
        self.assertEqual(rules(report), {("system-dir", "/etc/sudoers.d/smartroomcontroller"),
                                         ("sudoers-mode", "/etc/sudoers.d/smartroomcontroller")})

    def test_a_sudoers_file_is_0440_as_plain_visudo_c_requires(self):
        root = fake_root(self)
        (root / "etc/sudoers.d/smartroomcontroller").chmod(0o644)     # readable by every user
        (root / "etc/sudoers").chmod(0o640)
        report = self.check(root)
        self.assertEqual(rules(report), {("sudoers-mode", "/etc/sudoers.d/smartroomcontroller"),
                                         ("sudoers-mode", "/etc/sudoers")})
        (root / "etc/sudoers.d/smartroomcontroller").chmod(0o400)     # stricter is fine
        (root / "etc/sudoers").chmod(0o440)
        self.assertTrue(self.check(root).ok)
        (root / "etc/sudoers.d").chmod(0o750)                          # the directory is not a sudoers file
        self.assertTrue(self.check(root).ok)

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


def root_stream(owner_of_sudoers_d=0, sudoers_mode=0o440, no_data=(), shared=(), omit=()):
    """mkdir/mkfile under orphan names then rename, as btrfs send writes them.
    no_data: files sent without a write; shared: files whose contents arrive as a
    clone (shared copy) instead; omit: files not in the stream."""
    cmds = [(1, [p("@r-test")])]
    for d in ("etc", "usr", "usr/bin", "etc/sudoers.d", "home", "home/smartroomcontroller"):
        cmds += [(4, [p("o%d-1-0" % len(cmds))]), (9, [p("o%d-1-0" % len(cmds)), (16, d.encode())])]
        cmds += [(19, [p(d), u64(6, 0), u64(7, 0)]), (18, [p(d), u64(5, 0o755)])]
    files = {"etc/sudoers": SUDO, "etc/sudoers.d/rc": RC, "etc/passwd": PASSWD, "etc/group": GROUP}
    for path, data in files.items():
        if path in omit:
            continue
        orphan = "o%d-2-0" % len(cmds)
        cmds += [(3, [p(orphan)]), (9, [p(orphan), (16, path.encode())])]
        if path in shared:
            cmds += [(16, [p(path), u64(18, 0), u64(8, len(data))])]
        elif path not in no_data:
            cmds += [(15, [p(path), u64(18, 0), (19, data)])]
        cmds += [(19, [p(path), u64(6, 0), u64(7, 0)]), (18, [p(path), u64(5, 0o644)])]
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
        self.assertEqual(rules(report), {("system-dir", "/etc/sudoers.d/rc"), ("sudoers-mode", "/etc/sudoers.d/rc")})

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
        # Inside the namespace the tree belongs to sub-ids: remove it from there first.
        self.addCleanup(subprocess.run, ["unshare", "--map-auto", "--map-root-user", "rm", "-rf", str(root)],
                        capture_output=True)
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


class Boundary(unittest.TestCase):
    """The check stays on the root's own filesystem, and a walk error is a finding, not a crash."""

    def scandir_with(self, root, other=(), list_error=(), stat_error=()):
        real = os.scandir

        class Entry:
            def __init__(self, entry, rel):
                self.entry, self.name, self.rel = entry, entry.name, rel

            def stat(self, follow_symlinks=True):
                if self.rel in stat_error:
                    raise OSError(5, "Input/output error")
                s = self.entry.stat(follow_symlinks=follow_symlinks)
                if self.rel in other:
                    fields = list(s[:10])
                    fields[2] = s.st_dev + 1           # st_dev: another filesystem
                    fields[4] = fields[5] = 1000        # a tech's USB stick, uid 1000
                    return os.stat_result(fields)
                return s

        class It:
            def __new__(cls, path):
                if not isinstance(path, str) or not (path == root or path.startswith(root + "/")):
                    return real(path)                  # not the walk (visudo's scratch cleanup)
                return super().__new__(cls)

            def __init__(self, path):
                rel = os.path.relpath(path, root)
                self.rel = "" if rel == "." else rel
                if self.rel in list_error:
                    raise OSError(5, "Input/output error")
                self.it = real(path)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.it.close()

            def __iter__(self):
                return self

            def __next__(self):
                e = next(self.it)
                return Entry(e, e.name if not self.rel else f"{self.rel}/{e.name}")

        return mock.patch.object(sr.os, "scandir", It)

    def test_other_filesystems_are_listed_not_judged_or_walked(self):
        root = fake_root(self)
        for d in ("media/usb/inner", "var/log/journal", "boot/efi"):
            (root / d).mkdir(parents=True)
        with self.scandir_with(str(root), other=("media/usb", "var/log", "boot/efi")):
            report = sr.check_root_tree(str(root), Ids({"media/usb/inner": (1000, 1000)}))
        self.assertTrue(report.ok, report.text())
        self.assertEqual({o["path"] for o in report.other_fs}, {"/media/usb", "/var/log", "/boot/efi"})
        self.assertEqual(report.as_dict()["other_filesystems"][0]["owner"], "1000:1000")
        self.assertIn("not checked (other filesystems)", report.text())
        # the same tree on one filesystem: its uid-1000 directory fails
        report = sr.check_root_tree(str(root), Ids({"media/usb/inner": (1000, 1000)}))
        self.assertIn(("rc-owner", "/media/usb/inner"), rules(report))

    def test_a_walk_error_is_unreadable_not_a_crash(self):
        root = fake_root(self)
        with self.scandir_with(str(root), list_error=("usr/share",), stat_error=("etc/pacman.conf",)):
            report = sr.check_root_tree(str(root), Ids())
        self.assertEqual(rules(report), {("unreadable", "/usr/share"), ("unreadable", "/etc/pacman.conf")})

    @unittest.skipUnless(shutil.which("unshare") and subprocess.run(
        ["unshare", "--map-auto", "--map-root-user", "--mount", "true"], capture_output=True).returncode == 0,
        "no user and mount namespace")
    def test_a_real_mount_inside_the_root_is_not_walked(self):
        root = fake_root(self)
        (root / "media").mkdir()
        self.addCleanup(subprocess.run, ["unshare", "--map-auto", "--map-root-user", "rm", "-rf", str(root)],
                        capture_output=True)
        script = ('chown -R 0:0 "$0"; chown -R 1000:1000 "$0/home/smartroomcontroller" "$0/opt/smartroom"; '
                  'mount -t tmpfs stick "$0/media" && mkdir "$0/media/usb" && chown 1000:1000 "$0/media" "$0/media/usb" && '
                  f'python3 -I "{TOOL}" check-root --json "$0"')
        done = subprocess.run(["unshare", "--map-auto", "--map-root-user", "--mount", "bash", "-c", script, str(root)],
                              capture_output=True, text=True)
        doc = json.loads(done.stdout or "{}")
        self.assertEqual(done.returncode, 0, (doc, done.stderr))
        self.assertEqual([o["path"] for o in doc["other_filesystems"]], ["/media"])


class StreamContents(unittest.TestCase):
    """A stream whose sudoers, passwd or group contents the reader cannot see is unreadable."""

    def check(self, **kw):
        d = Path(tempfile.mkdtemp(prefix="srel-stream-"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / "root.btrfs").write_bytes(root_stream(**kw))
        return sr.check_root(d / "root.btrfs")

    def test_sudoers_without_contents_is_unreadable_not_an_empty_pass(self):
        self.assertIn(("unreadable", "/etc/sudoers"), rules(self.check(no_data=("etc/sudoers",))))

    def test_passwd_or_group_as_a_shared_copy_is_unreadable(self):
        report = self.check(shared=("etc/passwd",))
        self.assertIn(("unreadable", "/etc/passwd"), rules(report))
        self.assertIn(("unreadable", "/etc/group"), rules(self.check(shared=("etc/group",))))

    def test_a_sudoers_d_file_as_a_shared_copy_is_unreadable(self):
        self.assertIn(("unreadable", "/etc/sudoers.d/rc"), rules(self.check(shared=("etc/sudoers.d/rc",))))

    def test_a_stream_without_passwd_is_unreadable(self):
        self.assertIn(("unreadable", "/etc/passwd"), rules(self.check(omit=("etc/passwd",))))

    def test_an_empty_sudoers_d_file_is_fine(self):
        self.assertTrue(self.check(no_data=("etc/sudoers.d/rc",)).ok)


class CheckFailed(unittest.TestCase):
    """check-root exits 3 when the check could not run: never the "unsafe" exit 1."""

    def test_a_missing_path_or_a_truncated_stream_exits_3(self):
        d = Path(tempfile.mkdtemp(prefix="srel-cf-"))
        self.addCleanup(shutil.rmtree, d, True)
        (d / "root.btrfs").write_bytes(root_stream()[:-10])
        for target in (d / "nothing-here", d / "root.btrfs"):
            done = subprocess.run(["python3", "-I", str(TOOL), "check-root", "--json", str(target)],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, sr.CHECK_ROOT_ERROR, done.stderr)
            self.assertIsNone(json.loads(done.stdout)["ok"])

    def test_a_crash_in_the_check_exits_3(self):
        w = World(self)

        def boom(_path):
            raise RuntimeError("a bug in the walk")

        w.host.check_root = boom
        code, out, err = w.run("check-root", "--json")
        self.assertEqual(code, sr.CHECK_ROOT_ERROR)
        self.assertIn("a bug in the walk", out + err)


class TrialCheckCrash(unittest.TestCase):
    """A crash of the check on the trial root is not an unsafe root: logged, shown, not refused."""

    def armed(self, world):
        code, _, err = world.run("update", str(world.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        world.trial_boot()

    def crash(self, world, exc):
        def boom(_path):
            raise exc
        world.host.check_root = boom

    def test_studio_a_crashing_check_neither_refuses_nor_strands_the_trial(self):
        for exc in (RuntimeError("a bug"), PermissionError(13, "Permission denied"), sr.Fail("no zstd")):
            w = World(self)
            self.armed(w)
            self.crash(w, exc)
            code, _, err = w.run("health-run")
            self.assertEqual(code, 0, err)
            st = w.state()
            self.assertIsNone(st["trial"])                                    # never left "booting"
            self.assertEqual(st["configured"]["release"], "2026.11.21-1")     # promoted on health
            self.assertEqual(w.host.reboots, 0)
            self.assertIsNone(st["root_check"]["ok"])
            self.assertIn("root-check-error", [e["event"] for e in st["events"]])
            code, out, _ = w.run("status", "--json")
            self.assertIsNone(json.loads(out)["release"]["root_check"]["ok"])
            self.assertTrue(json.loads(out)["release"]["root_check"]["error"])
            # the next update is not refused as "a trial boot is already pending"
            del w.host.check_root
            code, _, err = w.run("update", str(w.release("2026.11.22-1")), "--unsigned")
            self.assertEqual(code, 0, err)

    def test_mini_the_same(self):
        w = MiniWorld(self)
        code, _, err = w.run("update", str(w.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        w.trial_boot()
        release = w.state()["trial"]["release"]
        self.crash(w, RuntimeError("a bug"))
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)
        self.assertIsNone(w.state()["trial"])
        self.assertEqual(w.state()["configured"]["release"], release)

    def test_a_passing_check_is_recorded_too(self):
        w = World(self)
        self.armed(w)
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 0)
        self.assertTrue(w.state()["root_check"]["ok"])

    def test_a_crash_while_staging_refuses_the_update_and_arms_nothing(self):
        w = World(self)
        self.crash(w, RuntimeError("a bug"))
        code, _, err = w.run("update", str(w.release()), "--unsigned")
        self.assertEqual(code, 1)
        self.assertIn("root check could not run", err)
        self.assertEqual(w.state()["last_result"]["reason"], "root-check-error")
        self.assertFalse((w.prefix / "top/@r-2026.11.21-1").exists())
        self.assertIsNone(w.state().get("trial"))


class RefusalKeepsTheFallback(unittest.TestCase):
    """A refused update leaves the previous release's boot files on the ESP."""

    def two_releases(self):
        w = World(self)
        for name in ("2026.11.21-1", "2026.11.22-1"):
            code, _, err = w.run("update", str(w.release(name, uki=f"uki-{name}".encode(),
                                                          stage2=f"s2-{name}".encode())), "--unsigned")
            self.assertEqual(code, 0, err)
            w.trial_boot(name)
            code, _, err = w.run("health-run")
            self.assertEqual(code, 0, err)
            w.back_on_configured(f"@r-{name}", boot_id=f"boot-after-{name}")
        st = w.state()
        self.assertEqual(st["previous"]["release"], "2026.11.21-1")
        return w

    def test_an_unsafe_root_refusal_puts_the_previous_boot_files_back(self):
        w = self.two_releases()
        prev_uki = w.esp / sr.LAYOUT_STUDIO.previous_uki
        self.assertEqual(prev_uki.read_bytes(), b"uki-2026.11.21-1")
        w.host.owners = {"etc": (1000, 1000)}
        code, _, err = w.run("update", str(w.release("2026.11.23-1")), "--unsigned")
        self.assertEqual(code, 1)
        self.assertIn("refused", err)
        self.assertEqual(prev_uki.read_bytes(), b"uki-2026.11.21-1")
        self.assertEqual((w.esp / sr.LAYOUT_STUDIO.previous_boot).read_bytes(), b"s2-2026.11.21-1")
        self.assertEqual(w.state()["previous"]["uki"], sr.LAYOUT_STUDIO.previous_uki)

    def test_any_other_refusal_after_the_cleanup_does_too(self):
        w = self.two_releases()
        prev_uki = w.esp / sr.LAYOUT_STUDIO.previous_uki
        with mock.patch.object(sr, "receive_root", side_effect=sr.Fail("receive failed")):
            code, _, _ = w.run("update", str(w.release("2026.11.23-1")), "--unsigned")
        self.assertEqual(code, 1)
        self.assertEqual(prev_uki.read_bytes(), b"uki-2026.11.21-1")


class KeptRoots(unittest.TestCase):
    """check-kept: the invariant on the rollback targets, information in status --json."""


    two_releases = RefusalKeepsTheFallback.two_releases

    def test_kept_roots_are_checked_and_shown_in_status(self):
        w = self.two_releases()
        (w.prefix / "top/@r-2026.11.21-1/etc").mkdir(parents=True, exist_ok=True)
        calls = []
        real = w.host.check_root

        def spy(path):
            calls.append(Path(path).name)
            if Path(path).name == "@r-2026.11.21-1":
                w.host.owners = {"etc": (1000, 1000)}
            else:
                w.host.owners = {}
            try:
                return real(path)
            finally:
                w.host.owners = {}

        w.host.check_root = spy
        code, out, err = w.run("check-kept", "--json", "--max-age", "3600")
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertNotIn("@r-2026.11.22-1", calls)              # the running root is integrity's
        by = {r["release"]: r for r in doc["roots"]}
        self.assertIs(by["2026.11.21-1"]["ok"], False)
        self.assertIs(doc["ok"], False)
        code, out, _ = w.run("status", "--json")
        status = json.loads(out)
        rows = {r["release"]: r for r in sr.release_rows(w.state())}
        self.assertIn("2026.11.21-1", rows)
        self.assertIn("keptRootsCheck", status)
        # reused while fresh and the same roots: no second walk
        n = len(calls)
        code, out, _ = w.run("check-kept", "--json", "--max-age", "3600")
        self.assertEqual(len(calls), n)
        w.host.clock += 7200
        code, out, _ = w.run("check-kept", "--json", "--max-age", "3600")
        self.assertGreater(len(calls), n)

    def test_status_never_walks(self):
        w = self.two_releases()

        def boom(_path):
            raise AssertionError("status walked a root")

        w.host.check_root = boom
        code, out, err = w.run("status", "--json")
        self.assertEqual(code, 0, err)


class JournalBeforeReboot(unittest.TestCase):
    def test_the_journal_is_flushed_before_a_rollback_reboot(self):
        tmp = Path(tempfile.mkdtemp(prefix="srel-j-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        log = tmp / "calls"
        for name in ("journalctl", "systemctl"):
            (tmp / name).write_text(f'#!/bin/sh\necho "{name} $*" >>"{log}"\n')
            (tmp / name).chmod(0o755)
        host = sr.Host(str(tmp / "room"))
        with mock.patch.dict(os.environ, {"PATH": f"{tmp}:{os.environ['PATH']}"}):
            host.reboot()
        self.assertEqual(log.read_text().splitlines(),
                         ["journalctl --flush", "journalctl --sync", "systemctl reboot --no-block"])


class RoomPages(unittest.TestCase):
    """Waiting on Lucas: "room pages up when a display is connected" as a trial health
    condition. Written and tested, off by default (require_room_pages=no)."""

    def trial(self, world, conf=None):
        if conf:
            (world.prefix / "etc/smartroomos").mkdir(parents=True, exist_ok=True)
            (world.prefix / "etc/smartroomos/release.conf").write_text(conf)
            world.host._conf = None
        code, _, err = world.run("update", str(world.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        world.trial_boot()

    def test_off_by_default_a_trial_without_room_pages_is_still_kept(self):
        w = World(self)
        w.host.room_pages_up = lambda: 0
        self.trial(w)
        self.assertEqual(sr.DEFAULTS["require_room_pages"], "no")
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 0)
        self.assertEqual(w.state()["configured"]["release"], "2026.11.21-1")

    def test_on_a_trial_whose_room_pages_never_start_rolls_back(self):
        w = World(self)
        w.host.room_pages_up = lambda: 0
        self.trial(w, "require_room_pages=yes\n")
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        st = w.state()
        self.assertEqual(st["configured"]["release"], sr.INSTALLED)
        self.assertEqual(st["last_result"]["reason"], "health-timeout")
        self.assertFalse(st["last_result"]["displays_ok"])
        self.assertEqual(st["last_result"]["room_pages_required"], "display")

    def test_always_requires_pages_also_without_a_drm_display(self):
        w = World(self)
        w.host.screens = 0                  # a test Studio: Hyprland headless outputs only
        w.host.room_pages_up = lambda: 0
        self.trial(w, "require_room_pages=always\n")
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(w.state()["last_result"]["room_pages_required"], "always")

    def test_on_with_room_pages_up_the_trial_is_kept(self):
        w = World(self)
        w.host.room_pages_up = lambda: 1
        self.trial(w, "require_room_pages=yes\n")
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 0)

    def test_on_without_a_display_no_page_is_required(self):
        w = World(self)
        w.host.screens = 0
        w.host.room_pages_up = lambda: 0
        self.trial(w, "require_room_pages=yes\n")
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 0)

    def test_room_pages_are_kiosk_browser_mains_with_a_room_url(self):
        tmp = Path(tempfile.mkdtemp(prefix="srel-pages-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "etc").mkdir()
        (tmp / "etc/passwd").write_text("root:x:0:0::/root:/bin/bash\nsmartroomcontroller:x:1000:1000::/h:/bin/sh\n")

        def proc(pid, comm, uid, *args):
            d = tmp / "proc" / str(pid)
            d.mkdir(parents=True)
            (d / "comm").write_text(comm + "\n")
            (d / "status").write_text(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
            (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")

        host = sr.Host(str(tmp))
        (tmp / "proc").mkdir()
        self.assertEqual(host.room_pages_up(), 0)
        proc(10, "chromium", 1000, "/usr/lib/chromium/chromium", "--type=renderer",
             "https://s.example/test-full?role=presentationDisplay")                      # a renderer
        proc(11, "chromium", 0, "/usr/lib/chromium/chromium", "https://s.example/r?role=x")   # not the kiosk user
        proc(12, "chromium", 1000, "/usr/lib/chromium/chromium", "about:blank")               # no room page
        proc(13, "bash", 1000, "bash", "https://s.example/r?role=x")
        self.assertEqual(host.room_pages_up(), 0)
        # Chromium's rewritten title (one space-joined string), as on the Home Studio
        proc(15, "chromium", 1000, "/usr/lib/chromium/chromium --type=zygote --no-zygote-sandbox")
        self.assertEqual(host.room_pages_up(), 0)
        proc(14, "chromium", 1000, "/usr/lib/chromium/chromium --user-data-dir=/opt/smartroom/chrome-profiles/x "
             "--kiosk --app=https://dev.example/test-full?role=presentationDisplay")
        self.assertEqual(host.room_pages_up(), 1)
        proc(16, "chromium", 1000, "/usr/lib/chromium/chromium", "--kiosk",
             "https://dev.example/test-full?role=extraDisplay1")                   # NUL-separated
        self.assertEqual(host.room_pages_up(), 2)


class RollbackRefusal(unittest.TestCase):
    """Waiting on Lucas: refuse a rollback/restore to a root that fails the invariant.
    Written and tested behind refuse_unsafe_rollback=no (default: today's behaviour)."""

    two_releases = RefusalKeepsTheFallback.two_releases

    def spoil_previous(self, w):
        real = w.host.check_root

        def spoiled(path):
            w.host.owners = {"etc": (1000, 1000)} if Path(path).name == "@r-2026.11.21-1" else {}
            try:
                return real(path)
            finally:
                w.host.owners = {}
        w.host.check_root = spoiled

    def conf(self, w, text):
        (w.prefix / "etc/smartroomos").mkdir(parents=True, exist_ok=True)
        (w.prefix / "etc/smartroomos/release.conf").write_text(text)
        w.host._conf = None

    def test_off_by_default_the_rollback_is_armed_and_the_trial_refuses_it(self):
        w = self.two_releases()
        self.spoil_previous(w)
        self.assertEqual(sr.DEFAULTS["refuse_unsafe_rollback"], "no")
        code, _, err = w.run("rollback")
        self.assertEqual(code, 0, err)
        self.assertEqual(w.state()["trial"]["release"], "2026.11.21-1")

    def test_on_a_rollback_to_an_unsafe_root_is_refused_before_arming(self):
        w = self.two_releases()
        self.conf(w, "refuse_unsafe_rollback=yes\n")
        self.spoil_previous(w)
        code, _, err = w.run("rollback")
        self.assertEqual(code, 1)
        self.assertIn("not armed", err)
        st = w.state()
        self.assertIsNone(st.get("trial"))
        self.assertEqual((st["last_result"]["result"], st["last_result"]["reason"]), ("refused", "unsafe-root"))
        self.assertFalse((w.esp / sr.LAYOUT_STUDIO.trial_uki).exists())
        self.assertEqual((w.esp / sr.LAYOUT_STUDIO.previous_uki).read_bytes(), b"uki-2026.11.21-1")

    def test_a_failed_rollback_keeps_the_previous_boot_files_on_the_esp(self):
        w = self.two_releases()
        prev_uki = w.esp / sr.LAYOUT_STUDIO.previous_uki
        with mock.patch.object(sr, "esp_free_bytes", return_value=0):      # esp-full after the cleanup
            code, _, err = w.run("rollback")
        self.assertEqual(code, 1)
        self.assertIn("ESP", err)
        self.assertEqual(prev_uki.read_bytes(), b"uki-2026.11.21-1")

    def test_on_a_good_root_and_a_check_error_still_roll_back(self):
        w = self.two_releases()
        self.conf(w, "refuse_unsafe_rollback=yes\n")
        code, _, err = w.run("rollback")
        self.assertEqual(code, 0, err)
        w2 = self.two_releases()
        self.conf(w2, "refuse_unsafe_rollback=yes\n")

        def boom(_path):
            raise RuntimeError("a bug")
        w2.host.check_root = boom
        code, _, err = w2.run("rollback")
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
