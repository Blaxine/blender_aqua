# SPDX-License-Identifier: GPL-3.0-or-later
"""Creating, failing to create, deleting and unregistering."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.level1 import rain_reactive as rr  # noqa: E402

CREATE_OPS = ("ocean_create", "rain_create", "rain_reactive_create",
              "snow_create", "hose_create", "rain_sim_create")


def test_reactive_rain_creates():
    r = bpy.ops.aquasuite.rain_reactive_create()
    u = lib.last_uuid()
    e = lib.entry(u)
    floor = e.primary
    dp = next((m for m in floor.modifiers if m.type == "DYNAMIC_PAINT"), None)
    em = next(o for o in e.root_collection.all_objects if o.particle_systems)
    bdp = next((m for m in em.modifiers if m.type == "DYNAMIC_PAINT"), None)
    lib.check("reactive rain creates canvas + brush",
              r == {"FINISHED"} and e.mode == "RRAIN" and dp is not None
              and len(dp.canvas_settings.canvas_surfaces) == 1
              and bdp is not None and bdp.brush_settings is not None, str(r))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_failed_create_leaves_nothing():
    before = lib.tagged_left()
    orig = rr.configure_brush

    def boom(*_a, **_k):
        raise RuntimeError("forced failure")

    rr.configure_brush = boom
    try:
        try:
            r = bpy.ops.aquasuite.rain_reactive_create()
        except RuntimeError as exc:
            r = f"raised ({str(exc).strip()[:40]})"
    finally:
        rr.configure_brush = orig
    left = [x for x in lib.tagged_left() if x not in before]
    lib.check("failed create leaves nothing tagged", not left, f"{r}; leftovers={left}")


def test_delete_all_leaves_nothing():
    for op in CREATE_OPS:
        getattr(bpy.ops.aquasuite, op)()
    lib.make_active(lib.add_cube(location=(30, 0, 1), name="UserCube"))
    bpy.ops.aquasuite.still_water_create()
    for u in [x.uuid for x in lib.scene().aqs_assemblies]:
        bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("delete-all leaves nothing tagged",
              lib.tagged_left() == [] and len(lib.scene().aqs_assemblies) == 0,
              str(lib.tagged_left()))


def test_unregister():
    lib.aq.unregister()
    lib.check("unregister", not hasattr(bpy.types.Scene, "aqs_assemblies"))


lib.main(globals())
