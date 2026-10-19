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

FRAMES = 120


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


def test_wavemaker_theory():
    import math
    # Linear dispersion: deep water L = g T^2 / 2pi.
    k = so.wave_number(1.0, 50.0)
    lib.check("dispersion matches deep-water wavelength",
              abs(2 * math.pi / k - 9.81 / (2 * math.pi)) < 1e-3, f"L={2 * math.pi / k:.4f}")
    bpy.ops.aquasuite.simulated_ocean_create(preset="OCEAN_STORM")
    u = lib.last_uuid()
    e = lib.entry(u)
    height, _amp = so.wave_plan(e)
    lib.check("Storm Surf preset is below the breaking limit (not capped)",
              abs(height - e.wave_height) < 1e-6, f"{height:.3f} of {e.wave_height:.3f}")
    e.wave_period = 1.5
    height, amp = so.wave_plan(e)
    lib.check("a 0.9 m wave at 1.5 s is capped below breaking (H/L < 0.142)",
              height < 0.45 and height / (2 * math.pi / so.wave_number(1.5, 2.2)) < 0.142,
              f"{height:.3f} m")
    # The period now changes the stroke: the piston must still clear the
    # back wall at full stroke and leave the water block in front of it.
    pad, src = so._part(e, "paddle"), so._part(e, "water")
    dom, ds = presets.domain(e)
    walls = []
    for period in (12.0, 0.6, 2.8):
        e.wave_period = period
        _h, amp = so.wave_plan(e)
        rest = so._paddle_curve(pad, e).keyframe_points[0].co.y  # minus the sine
        back = rest - pad.scale.x / 2 - amp          # full backward stroke
        front_at_rest = rest + pad.scale.x / 2
        water_back = src.location.x - src.scale.x / 2
        walls.append(back > dom.location.x - e.tank_size[0] / 2
                     and front_at_rest < water_back)
    lib.check("period edits keep the paddle inside the tank, water block in front",
              all(walls), str(walls))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


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
    samples = []
    for frame in range(FRAMES * 3 // 4, FRAMES + 1, 6):
        samples.append(_surface_range(dom, frame))
    return samples


def _surface_range(dom, frame):
    lib.scene().frame_set(frame)
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
    for key in ("OCEAN_CALM", "OCEAN_ROLLING", "OCEAN_STORM"):
        lib.scene().frame_set(1)
        bpy.ops.aquasuite.simulated_ocean_create(preset=key)
        uid = lib.last_uuid()
        waves[key] = _waviness(uid)
        from aquasuite.core import delete
        delete.delete_assembly(lib.scene(), uid, delete_cache=True)
    means = {k: sum(v) / len(v) for k, v in waves.items()}
    lib.check("late-quarter waves order Calm < Rolling < Storm",
              means['OCEAN_CALM'] < means['OCEAN_ROLLING'] < means['OCEAN_STORM'], str(waves))
    lib.check('Storm remains sustained through the last quarter',
              min(waves['OCEAN_STORM']) > .3 and means['OCEAN_STORM'] > .45, str(waves['OCEAN_STORM']))


lib.main(globals())
