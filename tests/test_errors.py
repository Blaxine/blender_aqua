# SPDX-License-Identifier: GPL-3.0-or-later
"""Error pipeline: recording, plain messages, scrubbed reports, operator
and deferred (update callback / frame handler) failures.

Headless Blender has no windows, so popups never open here: errors stay
in the pending queue, which is what these tests inspect.  The popup and
the clipboard are covered by the release checklist."""

import glob
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import errors, handlers  # noqa: E402
from aquasuite.level1 import rain_reactive as rr  # noqa: E402
from aquasuite.level2 import rain_sim  # noqa: E402
from aquasuite.level3 import hose  # noqa: E402

C = lib.C


def _call(op, **kw):
    """Scripted operator calls turn an ERROR report into RuntimeError;
    in the UI the user gets the popup instead."""
    try:
        return op(**kw)
    except RuntimeError as exc:
        return {"CANCELLED", f"reported: {exc}"}


class _Patch:
    def __init__(self, module, name, exc):
        self.module, self.name, self.exc = module, name, exc

    def __enter__(self):
        self.orig = getattr(self.module, self.name)
        exc = self.exc

        def boom(*_a, **_k):
            raise exc

        setattr(self.module, self.name, boom)

    def __exit__(self, *_a):
        setattr(self.module, self.name, self.orig)


def test_report_is_scrubbed():
    path = lib.save_blend("client_secret_project")
    home = os.path.expanduser("~")
    try:
        raise RuntimeError(f"could not read {path} in {home}")
    except RuntimeError as exc:
        err = errors.record("AquaSuite couldn't test", exc, mode=C.MODE_OCEAN)
    report = errors.build_report(err)
    leaks = [s for s in (home, home.replace("\\", "/"), path, "client_secret_project")
             if s.lower() in report.lower()]
    lib.check("report has no home folder, .blend path or name", not leaks, str(leaks))
    needed = (C.ADDON_VERSION, "Blender:", "OS:", "Mode: Plane Ocean",
              "What happened:", "Traceback:")
    missing = [n for n in needed if n not in report]
    lib.check("report has versions, OS, mode, message, traceback", not missing,
              f"missing {missing}")
    errors.reset_session()


def test_plain_messages():
    lib.check("RuntimeError text becomes the message",
              errors.plain_message(RuntimeError("Error: canvas could not be created"))
              == "Canvas could not be created")
    lib.check("internal errors get a generic sentence",
              errors.plain_message(KeyError("x")).startswith("Something unexpected"))


def test_create_failure_recorded_once():
    errors.reset_session()
    before = lib.tagged_left()
    with _Patch(rr, "configure_brush", RuntimeError("Dynamic Paint brush could not be created")):
        r1 = _call(bpy.ops.aquasuite.rain_reactive_create)
        r2 = _call(bpy.ops.aquasuite.rain_reactive_create)
    p = errors.pending()
    lib.check("failed create returns CANCELLED, nothing left behind",
              "CANCELLED" in r1 and "CANCELLED" in r2
              and lib.tagged_left() == before, str(r1))
    lib.check("one popup queued, plain message", len(p) == 1
              and p[0]["message"] == "Dynamic Paint brush could not be created"
              and "Reactive Rain" in p[0]["title"], str([e["title"] for e in p]))


def test_unhandled_operator_failure_caught():
    errors.reset_session()
    bpy.ops.aquasuite.hose_create()
    u = lib.last_uuid()
    with _Patch(hose, "apply_regime", ValueError("internal detail")):
        r = _call(bpy.ops.aquasuite.hose_set_regime, uuid=u, regime="SPRAY")
    p = errors.pending()
    lib.check("operator without its own handling still fails cleanly",
              "CANCELLED" in r and len(p) == 1 and p[0]["mode"] == C.MODE_HOSE
              and p[0]["uuid"] == u and p[0]["message"].startswith("Something unexpected"),
              str(p[0] if p else r))


def test_update_callback_failure_deferred_once():
    errors.reset_session()
    bpy.ops.aquasuite.rain_sim_create()
    u = lib.last_uuid()
    with _Patch(rain_sim, "apply_rain_params", RuntimeError("forced")):
        lib.entry(u).rain_speed = 10.0
        lib.entry(u).rain_speed = 11.0
    p = errors.pending()
    lib.check("slider failure recorded once, not raised", len(p) == 1
              and p[0]["uuid"] == u, str(len(p)))


def test_handler_failure_recorded_once():
    errors.reset_session()
    bpy.ops.aquasuite.ocean_create()
    u = lib.last_uuid()
    lib.make_active(lib.add_cube(location=(1, 1, 0), name="Boat"))
    bpy.ops.aquasuite.ocean_attach_buoy(uuid=u)
    handlers._error_logged.discard(u)
    with _Patch(handlers, "_tick_assembly", RuntimeError("forced")):
        for f in (5, 6, 7):
            lib.scene().frame_set(f)
    p = [e for e in errors.pending() if e["uuid"] == u]
    lib.check("frame-handler failure recorded once", len(p) == 1, str(len(p)))


def test_no_system_console_wording():
    hits = []
    for f in glob.glob(os.path.join(lib.REPO, "**", "*.py"), recursive=True):
        if os.sep + "tests" + os.sep in f:
            continue
        with open(f, encoding="utf-8") as fh:
            if "System Console" in fh.read():
                hits.append(os.path.relpath(f, lib.REPO))
    lib.check("no user message points to the System Console", not hits, str(hits))


lib.main(globals())
