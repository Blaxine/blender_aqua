# SPDX-License-Identifier: GPL-3.0-or-later
"""Ocean (Simulated): tank build, wave-maker forcing per preset,
default cache length, legacy paddle tanks and their upgrade, 0.20.0
keyframed wave makers and their switch to a driver, obstacles,
delete; with --bake, each preset makes waves of about its target height
mid-tank that still reach the far end, Calm < Rolling < Storm,
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

FRAMES = 720  # 30 s: wave fronts reach the far end after 20-24 s
MID_X = (-5.0, -4.5, -4.0, -3.5, -3.0)  # mid-tank gauges, clear of the 4 m zone
FAR_X = (4.0, 4.5, 5.0, 5.5, 6.0)       # far-tank gauges
FAR_SHARE = 0.5  # far-tank waves must keep at least half the mid-tank height
PERIODS = 3      # late heights are averaged over this many final wave periods:
                 # the far-tank pattern drifts from one period to the next
CAL_FRAME = 288  # 12 s: mid-tank waves are built up and the far-wall reflection
                 # has not come back yet (Storm's returns at ~19 s), so this is
                 # where the wave maker's calibration is checked
LATE_LIMIT = 2.5  # the closed tank stacks reflections into a partial standing
                  # wave (Storm: ~1.9x the set height mid-tank by 30 s); this
                  # only catches runaway build-up
WALL_X = -9.5


def _generator(obj, e, path):
    curve = so._strength_curve(obj, e) if path == 'field.strength' else so._curve(obj, e, path, 0)
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
        drivers = maker.animation_data.drivers
        lib.check(f"{key}: strength is a frame driver, not keyframed (no 'Animation -> Rigid "
                  "Body' console warning) and runs without Python auto-run",
                  maker.animation_data.action is None and len(drivers) == 1
                  and drivers[0].driver.is_valid and drivers[0].driver.is_simple_expression,
                  f"action {maker.animation_data.action} drivers {len(drivers)}")
        bpy.ops.aquasuite.assembly_delete(uuid=u)
    sc = lib.scene()
    sc.frame_start, sc.frame_end = 1, 250
    bpy.ops.aquasuite.simulated_ocean_create(preset="OCEAN_ROLLING")
    u = lib.last_uuid()
    _dom, ds = presets.domain(lib.entry(u))
    lib.check(f"a new tank bakes {so.CACHE_SECONDS} s, so waves reach the far end, and the "
              "timeline is extended to show it",
              ds.cache_frame_start == 1 and ds.cache_frame_end == round(so.CACHE_SECONDS * _fps())
              and sc.frame_end == ds.cache_frame_end, f"{ds.cache_frame_end} / {sc.frame_end}")
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    sc.frame_end = 1000
    bpy.ops.aquasuite.simulated_ocean_create(preset="OCEAN_ROLLING")
    u = lib.last_uuid()
    lib.check("a longer timeline is left alone", sc.frame_end == 1000)
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    sc.frame_end = 250
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
    bpy.data.objects.remove(so._part(e, "wavemaker"), do_unlink=True)
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
    lib.check("upgrade removes the paddle animation (the wave maker uses a driver)",
              owned == [] and len(maker.animation_data.drivers) == 1, str(owned))
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("deleting the upgraded tank leaves nothing tagged",
              lib.tagged_left() == [] and not any(
                  a.get(lib.C.OWNER_PROP) for a in bpy.data.actions), str(lib.tagged_left()))


def _make_020_tank(key="OCEAN_ROLLING"):
    """A tank as 0.20.0 built it: the wave maker's strength keyframed in an
    action (the same constant key and sine modifier) instead of a driver."""
    bpy.ops.aquasuite.simulated_ocean_create(preset=key)
    u = lib.last_uuid()
    e = lib.entry(u)
    maker = so._part(e, "wavemaker")
    _driven, gen = _generator(maker, e, "field.strength")
    names = ('function_type', 'use_additive', 'amplitude', 'phase_multiplier', 'phase_offset',
             'value_offset', 'use_restricted_range', 'frame_end', 'frame_start', 'blend_in',
             'blend_out')
    settings = {n: getattr(gen, n) for n in names}
    maker.driver_remove('field.strength')
    curve = so._curve(maker, e, 'field.strength')
    curve.keyframe_points[0].co.y = 0
    curve.keyframe_points[0].interpolation = 'CONSTANT'
    old = curve.modifiers.new('FNGENERATOR')
    for name, value in settings.items():
        setattr(old, name, value)
    return u


def _strengths(u):
    sc = lib.scene()
    maker = so._part(lib.entry(u), "wavemaker")
    values = []
    for frame in (1, 13, 37, 100, 301):
        for sub in (0.0, 0.5):
            sc.frame_set(frame, subframe=sub)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            values.append(maker.evaluated_get(depsgraph).field.strength)
    sc.frame_set(1)
    return values


def test_020_keyframed_tank():
    u = _make_020_tank()
    e = lib.entry(u)
    maker = so._part(e, "wavemaker")
    before = _strengths(u)
    lib.check("a 0.20.0 tank keyframes its wave-maker strength (test setup)",
              maker.animation_data.action is not None and not maker.animation_data.drivers
              and max(map(abs, before)) > 0, str([round(v, 4) for v in before]))
    path = lib.save_blend("ocean_020")
    bpy.ops.wm.open_mainfile(filepath=path)
    e = lib.entry(u)
    maker = so._part(e, "wavemaker")
    lib.check("after reopening, the 0.20.0 tank is unchanged (still keyframed, same strength)",
              maker.animation_data.action is not None and not maker.animation_data.drivers
              and _strengths(u) == before)
    so.apply_period(e)  # what Bake and every wave edit run first
    e = lib.entry(u)
    maker = so._part(e, "wavemaker")
    drivers = maker.animation_data.drivers
    after = _strengths(u)
    lib.check("its next bake swaps the action for the driver with identical strength",
              maker.animation_data.action is None and len(drivers) == 1
              and drivers[0].driver.is_simple_expression and after == before
              and not any(a.get(lib.C.OWNER_PROP) for a in bpy.data.actions),
              f"max diff {max(abs(a - b) for a, b in zip(after, before)):.3g}")
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("deleting the converted tank leaves nothing tagged", lib.tagged_left() == [],
              str(lib.tagged_left()))


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
    """Mid-tank and wall wave height (crest to trough) over the period ending
    at CAL_FRAME; mid-tank, far-tank and per-0.5 m heights averaged over the
    last PERIODS; first/last liquid volume and the bake time."""
    e = lib.entry(u)
    dom, ds = presets.domain(e)
    ds.cache_frame_start, ds.cache_frame_end = 1, FRAMES
    so.apply_period(e)  # fade-in starts at the cache start
    import time
    started = time.time()
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                   selected_editable_objects=[dom]):
        bpy.ops.fluid.bake_all()
    seconds = time.time() - started
    period = round(e.wave_period * _fps())
    series, volumes = {}, []
    frames = sorted({1, *range(CAL_FRAME - period + 1, CAL_FRAME + 1),
                     *range(FRAMES - PERIODS * period + 1, FRAMES + 1)})
    for frame in frames:
        tops, volume = _surface(dom, frame)
        series[frame] = tops
        volumes.append(volume)
    late = [range(end - period + 1, end + 1)
            for end in range(FRAMES - (PERIODS - 1) * period, FRAMES + 1, period)]
    calibration = [range(CAL_FRAME - period + 1, CAL_FRAME + 1)]

    def height(x, windows):
        """Crest to trough per period, averaged over the windows."""
        hs = []
        for window in windows:
            zs = [series[f][x] for f in window if x in series[f]]
            hs.append(max(zs) - min(zs) if zs else 0.0)
        return sum(hs) / len(hs)

    def gauges(xs, windows):
        return sum(height(x, windows) for x in xs) / len(xs)
    return dict(mid=round(gauges(MID_X, calibration), 3),
                wall=round(height(WALL_X, calibration), 3),
                gauges=[round(height(x, calibration), 3) for x in MID_X],
                late_mid=round(gauges(MID_X, late), 3), far=round(gauges(FAR_X, late), 3),
                late_wall=round(height(WALL_X, late), 3),
                profile={x / 2: round(height(x / 2, late), 3) for x in range(-19, 20)},
                bake_s=round(seconds),
                volume=(round(volumes[0], 2), round(volumes[-1], 2)),
                target=round(so.wave_plan(e)[0], 3))


BUTTONS = [("Preview", 48), ("Medium", 96), ("High", 160), ("Ultra", 256)]


class _Layout:
    """Records the text a panel draw would show."""
    def __init__(self, lines):
        self.lines, self.alert, self.enabled = lines, False, True

    def row(self, **_kw):
        return _Layout(self.lines)
    column = row

    def label(self, text="", **_kw):
        self.lines.append(text)

    def operator(self, *_a, **_kw):
        return type("Op", (), {})()

    def prop(self, *_a, **_kw):
        pass


def _panel_text(e):
    from aquasuite.ui import panel
    lines = []
    panel._draw_wave_limit(_Layout(lines), e)
    return " ".join(lines)


def test_resolution_warning():
    need = {}
    for key in ("OCEAN_CALM", "OCEAN_ROLLING", "OCEAN_STORM"):
        bpy.ops.aquasuite.simulated_ocean_create(preset=key)
        u = lib.last_uuid()
        e = lib.entry(u)
        dom, ds = presets.domain(e)
        package = presets.CATALOG[key]['entry']
        lib.check(f"{key}: the tank size the panel shows is the preset's, and the domain matches",
                  tuple(round(v, 4) for v in e.tank_size) == tuple(package['tank_size'])
                  and all(abs(a - b) < 1e-4 for a, b in zip(sw.object_dims(dom), e.tank_size))
                  and e.base_resolution == package['resolution' if 'resolution' in package
                                                    else 'base_resolution'],
                  f"{tuple(e.tank_size)} res {e.base_resolution}")
        need[key] = so.min_resolution(e)
        lib.check(f"{key}: no resolution warning at the preset's own resolution",
                  so.resolution_warning(e, BUTTONS) == '', so.resolution_warning(e, BUTTONS))
        bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("minimum resolution follows the measured limits: Calm 400, Rolling and Storm 160",
              need == {"OCEAN_CALM": 400, "OCEAN_ROLLING": 160, "OCEAN_STORM": 160}, str(need))

    bpy.ops.aquasuite.simulated_ocean_create(preset="OCEAN_ROLLING")
    u = lib.last_uuid()
    e = lib.entry(u)
    e.base_resolution = 96
    text = so.resolution_warning(e, BUTTONS)
    lib.check("Medium (96) warns that Rolling's waves need 160 (High) to cross the tank",
              "160" in text and "(High)" in text and "at 96" in text, text)
    shown = _panel_text(e)
    lib.check("the panel shows that warning with the panel's own button names",
              "160 or more (High)" in shown, shown)
    e.base_resolution = 160
    e.draft = True
    text = so.resolution_warning(e, BUTTONS)
    lib.check("Draft at 160 warns that it halves the resolution to 80 and says to turn it off",
              "Draft" in text and "80" in text and "Turn Draft off" in text, text)
    lib.check("the panel shows the Draft warning", "Turn Draft off" in _panel_text(e), _panel_text(e))
    e.draft = False
    lib.check("no panel warning once Draft is off at 160", "resolution" not in _panel_text(e),
              _panel_text(e))
    bpy.ops.aquasuite.assembly_delete(uuid=u)

    bpy.ops.aquasuite.simulated_ocean_create(preset="OCEAN_CALM")
    u = lib.last_uuid()
    e = lib.entry(u)
    e.base_resolution = 256
    text = so.resolution_warning(e, BUTTONS)
    lib.check("Calm at Ultra (256) still warns, naming 400 and Custom",
              "400" in text and "(Custom)" in text, text)
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_old_calm_tank():
    """A Calm tank saved before 0.20 (20 x 8 x 4 m at resolution 200) keeps
    its own size and resolution: the catalogue change does not touch it."""
    import json
    bpy.ops.aquasuite.simulated_ocean_create(preset="OCEAN_CALM")
    u = lib.last_uuid()
    e = lib.entry(u)
    with presets.applying(e):
        e.tank_size = (20.0, 8.0, 4.0)
        e.base_resolution = 200
        so.apply_settings(bpy.context, e)
    saved = json.loads(e.preset_snapshot)
    e.preset_snapshot = json.dumps(presets.snapshot(e, saved), sort_keys=True)
    path = lib.save_blend("ocean_old_calm")
    bpy.ops.wm.open_mainfile(filepath=path)
    e = lib.entry(u)
    dom, ds = presets.domain(e)
    lib.check("an old Calm tank reopens unchanged and not marked modified",
              tuple(e.tank_size) == (20.0, 8.0, 4.0) and e.base_resolution == 200
              and ds.resolution_max == 200 and not presets.is_modified(e)
              and all(abs(a - b) < 1e-4 for a, b in zip(sw.object_dims(dom), (20, 8, 4))),
              f"{tuple(e.tank_size)} res {e.base_resolution}/{ds.resolution_max}")
    so.apply_period(e)  # what Bake does first
    lib.check("baking it keeps its size and resolution, and the panel says 400 would carry its waves",
              all(abs(a - b) < 1e-4 for a, b in zip(sw.object_dims(dom), (20, 8, 4)))
              and ds.resolution_max == 200 and "400" in so.resolution_warning(e, BUTTONS),
              so.resolution_warning(e, BUTTONS))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


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
        print(f"{lib.TAG} INFO | [ocean bake] {key}: {w}", flush=True)
        from aquasuite.core import delete
        delete.delete_assembly(lib.scene(), uid, delete_cache=True)
        v0, v1 = w['volume']
        lib.check(f"{key}: mid-tank waves at 12 s within 35% of the {w['target']} m target",
                  abs(w['mid'] - w['target']) <= 0.35 * w['target'], str(w))
        lib.check(f"{key}: waves reach the far end (x +4..+6 at 30 s at least "
                  f"{FAR_SHARE:.0%} of mid-tank)", w['far'] >= FAR_SHARE * w['mid'], str(w))
        lib.check(f"{key}: reflections do not run away (mid-tank at 30 s at most "
                  f"{LATE_LIMIT}x the target)", w['late_mid'] <= LATE_LIMIT * w['target'], str(w))
        lib.check(f"{key}: the wall is not overdriven (at most 2.5x mid-tank)",
                  w['wall'] <= 2.5 * w['mid'], str(w))
        lib.check(f"{key}: liquid volume conserved within 1%",
                  v0 > 0 and abs(v1 - v0) <= 0.01 * v0, f"{v0} -> {v1}")
    mids = {k: v['mid'] for k, v in waves.items()}
    lib.check("mid-tank waves order Calm < Rolling < Storm",
              mids['OCEAN_CALM'] < mids['OCEAN_ROLLING'] < mids['OCEAN_STORM'], str(mids))


lib.main(globals())
