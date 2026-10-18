# SPDX-License-Identifier: GPL-3.0-or-later
"""Ocean (Simulated): tank build, paddle motion per preset, obstacles,
delete; with --bake, Calm stays flatter than Rolling Waves at the shipped
preset settings."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import presets  # noqa: E402
from aquasuite.level2 import simulated_ocean as so, still_water as sw  # noqa: E402

FRAMES = 72


def _stroke(u):
    pad = so._part(lib.entry(u), "paddle")
    xs = []
    for f in range(1, 61, 3):
        lib.scene().frame_set(f)
        xs.append(pad.matrix_world.translation.x)
    return max(xs) - min(xs)


def test_build_and_presets():
    bpy.data.objects.remove(bpy.data.objects["Cube"])
    strokes = {}
    for key in ("OCEAN_CALM", "OCEAN_ROLLING", "OCEAN_STORM"):
        bpy.ops.aquasuite.simulated_ocean_create(preset=key)
        u = lib.last_uuid()
        e = lib.entry(u)
        parts = {r: so._part(e, r) is not None for r in ("domain", "water", "paddle")}
        lib.check(f"{key}: tank, water block and paddle exist", all(parts.values()), str(parts))
        dom, ds = presets.domain(e)
        dx = max(sw.object_dims(dom)) / ds.resolution_max
        lib.check(f"{key}: cell no bigger than 13 cm (waves resolvable)", dx <= 0.13,
                  f"cell {dx:.3f} m at resolution {ds.resolution_max}")
        strokes[key] = _stroke(u)
        bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("paddle stroke grows Calm < Rolling < Storm",
              strokes["OCEAN_CALM"] < strokes["OCEAN_ROLLING"] < strokes["OCEAN_STORM"],
              str({k: round(v, 3) for k, v in strokes.items()}))
    lib.check("deleting tanks leaves nothing tagged (incl. paddle animation)",
              lib.tagged_left() == [] and not any(
                  a.get(lib.C.OWNER_PROP) for a in bpy.data.actions), str(lib.tagged_left()))


def test_obstacle_in_tank():
    bpy.ops.aquasuite.simulated_ocean_create()
    u = lib.last_uuid()
    rock = lib.add_cube(location=(7, 0, 1), size=1.5, name="Rock")
    bpy.ops.object.select_all(action="DESELECT")
    rock.select_set(True)
    lib.make_active(rock)
    bpy.ops.aquasuite.obstacles_add()
    lib.check("a rock in Water Obstacles becomes a liquid effector",
              any(m.type == "FLUID" and m.fluid_type == "EFFECTOR" for m in rock.modifiers))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def _waviness(u):
    dom, ds = presets.domain(lib.entry(u))
    ds.cache_frame_start, ds.cache_frame_end = 1, FRAMES
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                   selected_editable_objects=[dom]):
        bpy.ops.fluid.bake_all()
    lib.scene().frame_set(FRAMES)
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    mw = dom.matrix_world
    tops = {}
    for v in me.vertices:
        p = mw @ v.co
        if abs(p.y) < 1.0 and -9 < p.x < 6:
            b = round(p.x * 2) / 2
            tops[b] = max(tops.get(b, -1e9), p.z)
    ev.to_mesh_clear()
    return (max(tops.values()) - min(tops.values())) if tops else 0.0


def test_bake_calm_vs_rolling():
    if not lib.BAKE:
        lib.skip("ocean bakes", "run with --bake")
        return
    lib.save_blend("ocean")
    lib.scene().frame_start, lib.scene().frame_end = 1, FRAMES
    waves = {}
    for key in ("OCEAN_CALM", "OCEAN_ROLLING"):
        bpy.ops.aquasuite.simulated_ocean_create(preset=key)
        waves[key] = _waviness(lib.last_uuid())
    lib.check("baked Rolling Waves are clearly taller than Calm",
              waves["OCEAN_ROLLING"] > 0.15 and waves["OCEAN_ROLLING"] > 3 * waves["OCEAN_CALM"],
              f"crest-to-trough m: {({k: round(v, 3) for k, v in waves.items()})}")


lib.main(globals())
