# SPDX-License-Identifier: GPL-3.0-or-later
"""Every new setup is stamped; pre-release setups are recognised."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
import tomllib  # noqa: E402

C = lib.C
registry = lib.registry


def _manifest_version():
    with open(os.path.join(lib.REPO, "blender_manifest.toml"), "rb") as fh:
        return tomllib.load(fh)["version"]


def test_addon_version_from_manifest():
    lib.check("add-on version read from manifest",
              C.ADDON_VERSION == _manifest_version(), C.ADDON_VERSION)


def test_every_mode_is_stamped():
    for op in ("ocean_create", "rain_create", "rain_reactive_create",
               "snow_create", "hose_create", "rain_sim_create"):
        getattr(bpy.ops.aquasuite, op)()
    lib.make_active(lib.add_cube(location=(30, 0, 1), name="UserCube"))
    bpy.ops.aquasuite.still_water_create()
    entries = list(lib.scene().aqs_assemblies)
    lib.check("seven setups created", len(entries) == 7, str([e.mode for e in entries]))
    bad = [e.mode for e in entries
           if e.data_version != C.DATA_VERSION or e.addon_version != C.ADDON_VERSION]
    lib.check("stamp = current data version + add-on version", not bad,
              f"wrong on {bad}" if bad else f"data {C.DATA_VERSION}, add-on {C.ADDON_VERSION}")
    lib.check("new setups are not pre-release",
              not any(registry.is_pre_release(e) for e in entries))


def test_pre_release_detected():
    u = lib.last_uuid()
    lib.entry(u).data_version = 0          # what a 0.x file reads as
    lib.check("data version 0 is pre-release", registry.is_pre_release(lib.entry(u)))


lib.main(globals())
