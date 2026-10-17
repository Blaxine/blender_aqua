# SPDX-License-Identifier: GPL-3.0-or-later
"""Liquid-mode settings: secondary particles, Rain Sim emission and area,
hose velocity clamp, memory guard."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.level2 import rain_sim, still_water as sw  # noqa: E402
from aquasuite.level3 import hose  # noqa: E402

FLAGS = sw.SECONDARY_FLAGS
U = {}


def _flags(u):
    ds = sw.find_domain_object(lib.entry(u)).modifiers["AQS Fluid"].domain_settings
    return "".join("1" if getattr(ds, n) else "0" for n in FLAGS)


def test_setup():
    lib.scene().frame_start, lib.scene().frame_end = 1, 24
    lib.make_active(lib.add_cube(location=(30, 0, 1), name="UserCube"))
    bpy.ops.aquasuite.still_water_create()
    U["still"] = lib.last_uuid()
    bpy.ops.aquasuite.rain_sim_create()
    U["rs"] = lib.last_uuid()
    bpy.ops.aquasuite.hose_create()
    U["hose"] = lib.last_uuid()
    lib.entry(U["hose"]).hose_liquid = True    # liquid checks below
    lib.check("liquid setups created", all(lib.entry(u) for u in U.values()))


def test_secondary_particles_off():
    lib.check("Still Water / Rain Sim secondaries off",
              _flags(U["still"]) == "000" and _flags(U["rs"]) == "000",
              f"still={_flags(U['still'])} rs={_flags(U['rs'])}")


def test_hose_flags_stable():
    seq = [_flags(U["hose"])]
    for p in (0.9, 0.8, 0.7, 0.6):
        lib.entry(U["hose"]).pressure = p
        seq.append(_flags(U["hose"]))
    lib.check("hose secondaries stable across edits", set(seq) == {"000"}, str(seq))


def test_spray_secondaries_follow_draft():
    u = U["hose"]
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="SPRAY")
    lib.entry(u).draft = False
    on = _flags(u)
    lib.entry(u).draft = True
    off = _flags(u)
    lib.check("Spray: secondaries on without Draft, off with Draft",
              on == "111" and off == "000", f"{on} -> {off}")
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="NORMAL")


def test_rain_sim_inflow():
    fs = rain_sim._flow_settings(rain_sim.find_emitter(lib.entry(U["rs"])))
    lib.check("Rain Sim emitter uses INFLOW", fs.flow_behavior == "INFLOW", fs.flow_behavior)


def test_hose_clamp_recorded_and_cleared():
    u = U["hose"]
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="BLAST")
    e = lib.entry(u)
    e.draft = False
    e.base_resolution = 256
    e.pressure = 1.5
    c1 = hose.clamp_state(lib.entry(u))
    lib.entry(u).pressure = 0.3
    c2 = hose.clamp_state(lib.entry(u))
    lib.check("hose clamp recorded, then cleared", c1 is not None and c2 is None,
              f"{c1} -> {c2}")
    e = lib.entry(u)
    e.draft = True
    e.base_resolution = 96
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="NORMAL")


def test_rain_area_resizes_emitter_and_domain():
    e = lib.entry(U["rs"])
    emitter = rain_sim.find_emitter(e)
    e.rain_area = 8.0
    e = lib.entry(U["rs"])
    mn, mx = rain_sim.emitter_footprint(emitter)
    dom = sw.find_domain_object(e)
    bpy.context.view_layer.update()
    dmn, dmx = sw.world_bbox(dom)
    lib.check("Rain Area 8 m resizes emitter; domain covers it",
              abs((mx.x - mn.x) - 8.0) < 1e-3 and dmn.x <= mn.x and dmx.x >= mx.x,
              f"emitter {mx.x - mn.x:.2f} m, domain x [{dmn.x:.2f},{dmx.x:.2f}]")


def test_hose_aim_consistent_at_creation():
    e = lib.entry(U["hose"])
    em = hose._find_emitter(e)
    nozzle = e.primary
    bpy.context.view_layer.update()
    aim = hose._aim_direction(nozzle)
    normal = (em.matrix_world.to_3x3() @ em.data.polygons[0].normal).normalized()
    dom = sw.find_domain_object(e)
    dmin, dmax = sw.world_bbox(dom)
    z = nozzle.matrix_world.translation.z
    lib.check("hose emits along its aim, nozzle inside the domain",
              aim.dot(normal) > 0.99 and dmin.z < z < dmax.z and aim.z < -0.99,
              f"aim {tuple(round(c, 2) for c in aim)}, normal "
              f"{tuple(round(c, 2) for c in normal)}, nozzle z {z:.2f}, "
              f"domain z {dmin.z:.2f}..{dmax.z:.2f}")


def _injected_drops(u, frames=range(1, 25)):
    em = rain_sim.find_emitter(lib.entry(u))
    total = 0
    for f in frames:
        lib.scene().frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        total += max(len(em.evaluated_get(dg).data.vertices) - 4, 0) // 12
    return total


def test_splash_amount():
    u = U["rs"]
    lib.check("Splash Amount defaults to 10%",
              abs(lib.entry(u).splash_amount - 0.1) < 1e-6)
    lib.entry(u).splash_amount = 1.0
    every = _injected_drops(u)
    lib.entry(u).splash_amount = 0.1
    tenth = _injected_drops(u)
    lib.entry(u).splash_amount = 0.0
    none = _injected_drops(u)
    lib.entry(u).splash_amount = 0.1
    lib.check("Splash Amount scales the injected drops (0% = none)",
              every > 50 and none == 0 and 0.03 < tenth / every < 0.25,
              f"100%: {every}, 10%: {tenth}, 0%: {none}")


def test_memory_guard():
    e = lib.entry(U["still"])
    e.base_resolution = 512
    gb = sw.estimated_memory_gb(lib.entry(U["still"]))
    params = bpy.types.WindowManager.bl_rna.functions["invoke_confirm"].parameters.keys()
    lib.check("memory estimate over threshold + confirm API has message",
              gb > sw.MEMORY_CONFIRM_GB and "message" in params, f"{gb:.1f} GB")
    lib.entry(U["still"]).base_resolution = 96


def test_dead_props_removed():
    e = lib.entry(U["rs"])
    lib.check("dead Rain Sim props removed",
              not hasattr(e, "rain_streams") and not hasattr(e, "rain_auto_lifetime"))


lib.main(globals())
