"""Room screens are part of trial health. No switch.

A good release passes when the box is not adopted, when it is adopted with no
saved display settings, and when the screens are blanked (the self-test turns
them on, sees a picture, and the result says they were put back). A display
that was already broken in the baseline does not fail the release. A display
that fails and was fine in the baseline does.
"""
import json
import unittest

from test_release import World, sr

ROLE = {"uuid": "edid:front", "name": "front", "endpointRole": "presentationDisplay"}
AV = {"presentationDisplay": {"address": "tcp://192.0.2.10:3629"}}


def adopt(world, room="room-101", displays=None, av=None):
    cfg = {"serverUrl": "https://rooms.example", "roomId": room}
    path = world.prefix / "opt/smartroom/config/agent.json"
    path.write_text(json.dumps(cfg))
    if displays is None and av is None:
        return
    cache = {
        "version": 1,
        "roomId": room,
        "displays": displays or [],
        "state": {"avControls": av or {}},
    }
    dest = world.prefix / "opt/smartroom/data/room-cache.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(cache))


def mark_test_room(world, name="room-A"):
    dest = world.prefix / "etc/smartroomos/test-room"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"room={name}\n")
    (world.prefix / "etc/hostname").write_text("room-A\n")


def good_display(ok=True):
    return {
        "ok": ok,
        "skipped": None,
        "displays": [{
            "id": "presentationDisplay",
            "kind": "projector",
            "connected": ok,
            "reportsOn": ok,
            "nonBlack": ok,
            "ok": ok,
            "restored": {"power": "off", "blank": True},
            "error": None,
        }],
    }


class DisplayHealth(unittest.TestCase):
    def trial(self, world):
        code, _, err = world.run("update", str(world.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        world.trial_boot()

    def test_switches_are_gone(self):
        self.assertNotIn("require_room_pages", sr.DEFAULTS)
        self.assertNotIn("refuse_unsafe_rollback", sr.DEFAULTS)

    def test_not_adopted_passes_with_displays_and_no_pages(self):
        w = World(self)
        calls = []
        w.host.display_self_test = lambda: calls.append(1)
        w.host.screens = 3
        self.trial(w)
        self.assertEqual(calls, [])
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(calls, [])
        self.assertEqual(w.state()["configured"]["release"], "2026.11.21-1")
        doc = json.loads((w.prefix / "var/lib/smartroomos/display-baseline.json").read_text())
        self.assertEqual(doc["screenCase"], "not-adopted")
        self.assertEqual(doc["selfTest"]["skipped"], "not-adopted")

    def test_adopted_with_no_saved_display_settings_passes(self):
        w = World(self)
        adopt(w, displays=[{"uuid": "edid:x", "name": "panel", "endpointRole": None}], av={})
        calls = []
        w.host.display_self_test = lambda: calls.append(1)
        w.host.screens = 3
        self.trial(w)
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(calls, [])
        self.assertEqual(w.state()["trial"], None)

    def test_blanked_screens_pass_when_the_self_test_is_good(self):
        """Powered off at night: no DRM connector during the quiet window.
        The self-test (faked) reports the picture was good and power was put back."""
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        seen = []

        def once():
            seen.append(1)
            return good_display(True)

        w.host.display_self_test = once
        w.host.screens = 0
        self.trial(w)
        # The baseline is the pre-update call. Health is the second.
        self.assertEqual(len(seen), 1)
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(seen), 2)
        self.assertEqual(w.state()["configured"]["release"], "2026.11.21-1")
        base = w.state()["last_result"]
        self.assertNotEqual(base.get("reason"), "display-self-test")

    def test_a_display_already_broken_in_the_baseline_does_not_fail(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        w.host.display_self_test = lambda: good_display(False)
        w.host.screens = 0
        self.trial(w)
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(w.state()["configured"]["release"], "2026.11.21-1")

    def test_a_newly_broken_display_fails_the_trial(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        answers = [good_display(True), good_display(False)]

        def seq():
            return answers.pop(0)

        w.host.display_self_test = seq
        w.host.room_pages_up = lambda: 1
        w.host.screens = 1
        self.trial(w)
        code, _, err = w.run("health-run")
        self.assertEqual(code, 1, err)
        st = w.state()
        self.assertEqual(st["configured"]["release"], sr.INSTALLED)
        self.assertEqual(st["last_result"]["reason"], "display-self-test")
        self.assertEqual(st["last_result"]["newlyBroken"], ["presentationDisplay"])
        self.assertEqual(w.host.reboots, 1)

    def test_no_baseline_failure_does_not_excuse_a_new_failure(self):
        """A skipped baseline is not proof the display was already broken."""
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        answers = [
            {"ok": True, "skipped": "unavailable", "displays": []},
            good_display(False),
        ]
        w.host.display_self_test = lambda: answers.pop(0)
        w.host.screens = 0
        self.trial(w)
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(w.state()["last_result"]["reason"], "display-self-test")

    def test_a_test_room_requires_pages_with_no_drm_display(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        mark_test_room(w)
        w.host.display_self_test = lambda: good_display(True)
        w.host.screens = 0
        w.host.room_pages_up = lambda: 0
        self.trial(w)
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(w.state()["last_result"]["reason"], "health-timeout")
        self.assertEqual(w.state()["last_result"]["room_pages_required"], "always")

    def test_a_real_room_with_nothing_connected_does_not_require_pages(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        w.host.display_self_test = lambda: good_display(True)
        w.host.screens = 0
        w.host.room_pages_up = lambda: 0
        self.trial(w)
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)

    def test_an_old_require_room_pages_no_does_not_disable_the_check(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        (w.prefix / "etc/smartroomos").mkdir(parents=True, exist_ok=True)
        (w.prefix / "etc/smartroomos/release.conf").write_text("require_room_pages=no\n")
        w.host._conf = None
        w.host.display_self_test = lambda: good_display(True)
        w.host.screens = 2
        w.host.room_pages_up = lambda: 0
        self.trial(w)
        code, _, _ = w.run("health-run")
        self.assertEqual(code, 1)
        self.assertEqual(w.state()["last_result"]["reason"], "health-timeout")
        self.assertEqual(w.state()["last_result"]["room_pages_required"], "display")

    def test_cache_missing_on_the_trial_root_uses_the_baseline(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        w.host.display_self_test = lambda: good_display(True)
        w.host.screens = 0
        code, _, err = w.run("update", str(w.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        cache = w.prefix / "opt/smartroom/data/room-cache.json"
        cache.unlink()
        w.trial_boot()
        w.host.room_pages_up = lambda: 0
        self.assertEqual(w.host.screen_case(w.state()["trial"]["baseline"]), "configured")
        code, _, err = w.run("health-run")
        self.assertEqual(code, 0, err)

    def test_an_update_is_not_refused_because_the_baseline_display_is_broken(self):
        w = World(self)
        adopt(w, displays=[ROLE], av=AV)
        w.host.display_self_test = lambda: good_display(False)
        code, _, err = w.run("update", str(w.release()), "--unsigned")
        self.assertEqual(code, 0, err)
        self.assertEqual(w.state()["trial"]["baseline"]["displaySelfTest"]["displays"][0]["ok"], False)


if __name__ == "__main__":
    unittest.main()
