# SPDX-License-Identifier: GPL-3.0-or-later
"""Ocean (Simulated): tank build, wave-maker forcing per preset, legacy
paddle tanks and their upgrade, obstacles, delete; with --bake, each preset
makes waves of about its target height mid-tank, Calm < Rolling < Storm,
without losing water or overdriving the wall."""

import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import presets  # noqa: E402
from aquasuite.level2 import simulated_ocean as so, still_water as sw  # noqa: E402

FRAMES = 288  # waves need ~10 s to build up mid-tank
MID_X = (-5.0, -4.5, -4.0, -3.5, -3.0)  # mid-tank gauges, clear of the 4 m zone
WALL_X = -9.5


def _generator(obj, e, path):
    curve = so._curve(obj, e, path, 0 if path == 'location' else None)
    return curve, next(m for m in curve.modifiers if m.type == 'FNGENERATOR')


def _fps():
    return lib.scene().render.fps / lib.scene().render.fps_base


def test_build_and_presets():
    bpy.data.objects.remove(bpy.data.objects["Cube"])
    strengths = {}
    for key in ("OCEAN_CALM", "OCEAN_ROLLING", "OCEAN_STORM"):
        bpy.ops.aquasuite.simulated_ocean_create(preset=key)
        u = lib.last_uuid()
        e = lib.entry(u)
        parts = {r: so._part(e, r) is not None for r in ("domain", "water", "wavemaker")}
        lib.check(f"{key}: tank, water block and wave maker exist", all(parts.values())
                  and so._part(e, "paddle") is None and not so.is_legacy(e), str(parts))
        dom, ds = presets.domain(e)
        dx = max(sw.object_dims(dom)) / ds.resolution_max
        lib.check(f"{key}: cell no bigger than 13 cm (waves resolvable)", dx <= 0.13,
                  f"cell {dx:.3f} m at resolution {ds.resolution_max}")
        maker = so._part(e, "wavemaker")
        field = maker.field
        _curve, gen = _generator(maker, e, "field.strength")
        strengths[key] = gen.amplitude
        _h, zone, strength = so.forcing_plan(e, _fps())
        lib.check(f"{key}: Wind field drives a sine at the wave period",
                  field.type == 'WIND' and abs(gen.amplitude - strength) < 1e-6
                  and abs(gen.phase_multiplier * e.wave_period * _fps() - 2 * math.pi) < 1e-4
                  and gen.use_restricted_range and gen.blend_in > 0,
                  f"{field.type} amp {gen.amplitude:.4f} plan {strength:.4f}")
        lib.check(f"{key}: forcing zone is a full-depth slab at the left wall",
                  field.falloff_type == 'TUBE' and field.z_direction == 'POSITIVE'
                  and abs(field.distance_max - zone) < 1e-6
                  and zone <= e.tank_size[0] * so.ZONE_SHARE + 1e-6
                  and field.radial_max >= math.hypot(e.tank_size[1], e.tank_size[2]) / 2
                  and abs(maker.matrix_world.translation.x - (dom.location.x - e.tank_size[0] / 2)) < 1e-4,
                  f"zone {field.distance_max:.2f} radial {field.radial_max:.2f}")
        lib.check(f"{key}: only this tank's own fields push its water",
                  ds.effector_weights.collection == e.root_collection)
        bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("wave-maker strength grows Calm < Rolling < Storm",
              strengths["OCEAN_CALM"] < strengths["OCEAN_ROLLING"] < strengths["OCEAN_STORM"],
              str({k: round(v, 4) for k, v in strengths.items()}))
    lib.check("deleting tanks leaves nothing tagged (incl. wave-maker animation)",
              lib.tagged_left() == [] and not any(
                  a.get(lib.C.OWNER_PROP) for a in bpy.data.actions), str(lib.tagged_left()))


def test_wavemaker_theory():
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
    fps = _fps()
    _h, zone, base = so.forcing_plan(e, fps)
    _h, _z, double_fps = so.forcing_plan(e, fps * 2)
    lib.check("Wind strength scales with 1/fps (the solver adds it per frame step)",
              abs(double_fps * 2 - base) < 1e-9, f"{base:.5f} vs {double_fps:.5f}")
    e.wave_height = 0.45
    _h, _z, half = so.forcing_plan(e, fps)
    lib.check("Wind strength is proportional to the planned height",
              abs(half / base - 0.5) < 1e-6, f"{half / base:.4f}")
    e.wave_height = 0.9
    e.wave_period = 1.5
    height, _amp = so.wave_plan(e)
    lib.check("a 0.9 m wave at 1.5 s is capped below breaking (H/L < 0.142)",
              height < 0.45 and height / (2 * math.pi / so.wave_number(1.5, 2.2)) < 0.142,
              f"{height:.3f} m")
    # Period edits re-plan the zone; it and the water block stay inside the
    # tank, and the water fills it end to end.
    maker, src = so._part(e, "wavemaker"), so._part(e, "water")
    dom, _ds = presets.domain(e)
    ok = []
    for period in (12.0, 0.6, 2.8):
        e.wave_period = period
        _h, zone, _s = so.forcing_plan(e, fps)
        lam = 2 * math.pi / so.wave_number(period, e.tank_size[2] * so.WATER_FRACTION)
        water = (src.location.x - src.scale.x / 2, src.location.x + src.scale.x / 2)
        ok.append(zone <= min(lam / 2, e.tank_size[0] * so.ZONE_SHARE) + 1e-6
                  and abs(maker.field.distance_max - zone) < 1e-6
                  and water[0] > dom.location.x - e.tank_size[0] / 2
                  and water[1] < dom.location.x + e.tank_size[0] / 2
                  and src.scale.x > e.tank_size[0] * 0.95)
    lib.check("period edits keep the zone at most half a wavelength, water filling the tank",
              all(ok), str(ok))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def _make_legacy_tank(key="OCEAN_ROLLING"):
    """A tank as 0.19 built it: the same parts, but a collision paddle in
    place of the wave maker and no effector-collection limit."""
    bpy.ops.aquasuite.simulated_ocean_create(preset=key)
    u = lib.last_uuid()
    e = lib.entry(u)
    maker = so._part(e, "wavemaker")
    action = maker.animation_data.action
    bpy.data.objects.remove(maker, do_unlink=True)
    bpy.data.actions.remove(action)
    _dom, ds = presets.domain(e)
    ds.effector_weights.collection = None
    paddle = so._box(e.root_collection, u, 'paddle')
    mod = paddle.modifiers.new('AQS Wave Paddle', 'FLUID')
    mod.fluid_type = 'EFFECTOR'
    mod.effector_settings.effector_type = 'COLLISION'
    paddle.hide_render = True
    paddle.display_type = 'WIRE'
    so.apply_settings(bpy.context, e)
    return u


def _paddle_state(u):
    e = lib.entry(u)
    pad, src = so._part(e, "paddle"), so._part(e, "water")
    curve, gen = _generator(pad, e, "location")
    return (round(gen.amplitude, 6), round(gen.phase_multiplier, 6),
            round(curve.keyframe_points[0].co.y, 6), tuple(round(v, 6) for v in src.location),
            tuple(round(v, 6) for v in src.scale))


def test_legacy_paddle_tank():
    u = _make_legacy_tank()
    e = lib.entry(u)
    _h, amp = so.wave_plan(e)
    before = _paddle_state(u)
    lib.check("a 0.19 paddle tank is recognised as legacy and keeps its stroke",
              so.is_legacy(e) and abs(before[0] - amp) < 1e-6, str(before))
    path = lib.save_blend("ocean_legacy")
    bpy.ops.wm.open_mainfile(filepath=path)
    e = lib.entry(u)
    lib.check("after reopening, the paddle tank is unchanged and gets no wave maker",
              so.is_legacy(e) and _paddle_state(u) == before
              and so._part(e, "wavemaker") is None)
    e.wave_period = 3.1
    e = lib.entry(u)
    _h, amp = so.wave_plan(e)
    state = _paddle_state(u)
    _dom, ds = presets.domain(e)
    lib.check("editing a legacy tank still drives the paddle as before",
              abs(state[0] - amp) < 1e-6 and state != before
              and so._part(e, "wavemaker") is None and ds.effector_weights.collection is None,
              str(state))
    bpy.ops.aquasuite.simulated_ocean_upgrade(uuid=u)
    e = lib.entry(u)
    maker = so._part(e, "wavemaker")
    lib.check("Upgrade Wave Maker swaps the paddle for the Wind wave maker",
              maker is not None and so._part(e, "paddle") is None and not so.is_legacy(e)
              and maker.field.type == 'WIND' and abs(e.wave_period - 3.1) < 1e-6
              and ds.effector_weights.collection == e.root_collection)
    owned = [a.name for a in bpy.data.actions if a.get(lib.C.OWNER_PROP)]
    lib.check("upgrade removes the paddle animation (only the wave maker's remains)",
              owned == [maker.animation_data.action.name], str(owned))
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("deleting the upgraded tank leaves nothing tagged",
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
    bpy.data.objects.remove(rock, do_unlink=True)


def _surface(dom, frame):
    """(top height per 0.5 m bin along the centreline, liquid volume)."""
    lib.scene().frame_set(frame)
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    mw = dom.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    tops = {}
    for p in pts:
        if abs(p.y) < 1.0:
            b = round(p.x * 2) / 2
            tops[b] = max(tops.get(b, -1e9), p.z)
    me.calc_loop_triangles()
    volume = sum(pts[a].dot(pts[b].cross(pts[c])) for a, b, c in
                 (t.vertices for t in me.loop_triangles)) / 6
    ev.to_mesh_clear()
    return tops, volume


def _bake_and_measure(u):
    """Wave height (crest to trough over the last full period) at the
    mid-tank gauges and at the wall, plus first/last liquid volume."""
    e = lib.entry(u)
    dom, ds = presets.domain(e)
    ds.cache_frame_start, ds.cache_frame_end = 1, FRAMES
    so.apply_period(e)  # fade-in starts at the cache start
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                   selected_editable_objects=[dom]):
        bpy.ops.fluid.bake_all()
    period = round(e.wave_period * _fps())
    series, volumes = {}, []
    for frame in [1] + list(range(FRAMES - period + 1, FRAMES + 1)):
        tops, volume = _surface(dom, frame)
        series[frame] = tops
        volumes.append(volume)
    last = [series[f] for f in range(FRAMES - period + 1, FRAMES + 1)]

    def height(x):
        zs = [t[x] for t in last if x in t]
        return max(zs) - min(zs) if zs else 0.0
    mid = sum(height(x) for x in MID_X) / len(MID_X)
    return dict(mid=round(mid, 3), wall=round(height(WALL_X), 3),
                gauges=[round(height(x), 3) for x in MID_X],
                volume=(round(volumes[0], 2), round(volumes[-1], 2)),
                target=round(so.wave_plan(e)[0], 3))


def test_bake_wave_heights():
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
        waves[key] = w = _bake_and_measure(uid)
        print(f"[ocean bake] {key}: {w}", flush=True)
        from aquasuite.core import delete
        delete.delete_assembly(lib.scene(), uid, delete_cache=True)
        v0, v1 = w['volume']
        lib.check(f"{key}: mid-tank waves within 35% of the {w['target']} m target",
                  abs(w['mid'] - w['target']) <= 0.35 * w['target'], str(w))
        lib.check(f"{key}: the wall is not overdriven (at most 2.5x mid-tank)",
                  w['wall'] <= 2.5 * w['mid'], str(w))
        lib.check(f"{key}: liquid volume conserved within 1%",
                  v0 > 0 and abs(v1 - v0) <= 0.01 * v0, f"{v0} -> {v1}")
    mids = {k: v['mid'] for k, v in waves.items()}
    lib.check("mid-tank waves order Calm < Rolling < Storm",
              mids['OCEAN_CALM'] < mids['OCEAN_ROLLING'] < mids['OCEAN_STORM'], str(mids))


lib.main(globals())
