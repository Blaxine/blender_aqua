# SPDX-License-Identifier: GPL-3.0-or-later
"""Whitewater (Spray / Foam / Bubbles): render-ready particles, toggling,
Draft, no leftover settings, delete; with --bake, live particles."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import presets  # noqa: E402

U = {}
NAMES = ("Spray", "Foam", "Bubbles")


def _systems():
    dom, _ds = presets.domain(lib.entry(U["w"]))
    return {p.name: p.settings for p in dom.particle_systems}


def _render_ready(name):
    ps = _systems().get(name)
    return bool(ps and ps.render_type == "OBJECT" and ps.instance_object is not None)


def test_setup():
    lib.save_blend("whitewater")
    lib.scene().frame_start, lib.scene().frame_end = 1, 24
    lib.make_active(lib.add_cube(location=(0, 0, 1)))
    bpy.ops.aquasuite.still_water_create(preset="STILL_SPLASHY")
    U["w"] = lib.last_uuid()
    lib.check("Splashy: all three elements render-ready (not Halo)",
              all(_render_ready(n) for n in NAMES), str({n: _render_ready(n) for n in NAMES}))
    lib.check("no whitewater warning", lib.entry(U["w"]).ww_warning == "")


def test_toggle_off_and_on():
    before = {ps.name for ps in bpy.data.particles}
    lib.entry(U["w"]).ww_foam = False
    after = {ps.name for ps in bpy.data.particles}
    lib.check("Foam off removes its system and its settings (no leftovers)",
              "Foam" not in _systems() and len(after) == len(before) - 1,
              f"{len(before)} -> {len(after)} settings")
    lib.entry(U["w"]).ww_foam = True
    lib.check("Foam on again is render-ready", _render_ready("Foam"))


def test_draft_suspends():
    e = lib.entry(U["w"])
    e.draft = True
    suspended = not any(n in _systems() for n in NAMES)
    kept = (e.ww_spray, e.ww_foam, e.ww_bubbles) == (True, True, True)
    lib.entry(U["w"]).draft = False
    lib.check("Draft suspends whitewater and keeps the checkboxes",
              suspended and kept and all(_render_ready(n) for n in NAMES))


def test_size():
    lib.entry(U["w"]).ww_foam_size = 0.031
    lib.check("Size drives the render size", abs(_systems()["Foam"].particle_size - 0.031) < 1e-6)


def test_bake_has_particles():
    if not lib.BAKE:
        lib.skip("whitewater bake", "run with --bake")
        return
    e = lib.entry(U["w"])
    e.base_resolution = 48
    dom, ds = presets.domain(lib.entry(U["w"]))
    ds.cache_frame_start, ds.cache_frame_end = 1, 24
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                   selected_editable_objects=[dom]):
        bpy.ops.fluid.bake_all()
    lib.scene().frame_set(20)
    dg = bpy.context.evaluated_depsgraph_get()
    alive = {p.name: sum(1 for q in p.particles if q.alive_state == "ALIVE")
             for p in dom.evaluated_get(dg).particle_systems}
    lib.check("baked Spray, Foam and Bubbles all have particles",
              all(alive.get(n, 0) > 0 for n in NAMES), str(alive))


def test_delete():
    bpy.ops.aquasuite.assembly_delete(uuid=U["w"])
    lib.check("delete leaves nothing tagged", lib.tagged_left() == [], str(lib.tagged_left()))


lib.main(globals())
