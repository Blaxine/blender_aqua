# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake state and cancelling.  Headless Blender cannot run a bake as a
background job, so stopping a bake mid-way is covered by the release
checklist; this checks state detection, a harmless Cancel when idle, and
that the ripple bake still completes headless."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import bakes, errors  # noqa: E402

U = {}


def test_setup():
    lib.save_blend("bake_cancel")
    lib.scene().frame_start, lib.scene().frame_end = 1, 5
    lib.make_active(lib.add_cube(location=(30, 0, 1)))
    bpy.ops.aquasuite.still_water_create()
    U["still"] = lib.last_uuid()
    bpy.ops.aquasuite.hose_create()
    U["hose"] = lib.last_uuid()
    bpy.ops.aquasuite.rain_sim_create()
    U["rs"] = lib.last_uuid()
    bpy.ops.aquasuite.rain_reactive_create()
    U["rr"] = lib.last_uuid()
    lib.check("setups created", all(lib.entry(u) for u in U.values()))


def test_idle_is_not_baking():
    baking = {k: bakes.is_baking(lib.entry(u)) for k, u in U.items()}
    lib.check("nothing reports baking when idle", not any(baking.values()), str(baking))
    lib.check("no AquaSuite bake running", not bakes.any_baking())
    baked = {k: bakes.has_bake(lib.entry(u)) for k, u in U.items()}
    lib.check("new setups have no bake (red Bake, Free greyed out)",
              not any(baked.values()), str(baked))


def test_cancel_when_idle_is_harmless():
    errors.reset_session()
    results = [bpy.ops.aquasuite.cancel_bake(uuid=U["still"]),
               bpy.ops.aquasuite.cancel_bake(uuid=U["rr"])]
    lib.check("Cancel Bake when nothing bakes: no-op, no error popup",
              all(r == {"CANCELLED"} for r in results) and not errors.pending(),
              str(results))


def test_ripple_bake_completes_headless():
    pc = bakes.ripple_cache(lib.entry(U["rr"]))
    floor = lib.entry(U["rr"]).primary
    surf = next(m for m in floor.modifiers if m.type == "DYNAMIC_PAINT").canvas_settings.canvas_surfaces[0]
    surf.frame_start, surf.frame_end = 1, 5
    r = bpy.ops.aquasuite.bake_ripples(uuid=U["rr"])
    lib.check("ripple bake finishes headless (blocking)",
              r == {"FINISHED"} and pc.is_baked and not pc.is_baking, str(r))
    lib.check("baked ripples report a bake (blue Bake Again)",
              bakes.has_bake(lib.entry(U["rr"])))


lib.main(globals())
