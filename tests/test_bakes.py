# SPDX-License-Identifier: GPL-3.0-or-later
"""Low-resolution bakes (only with --bake): every liquid mode must actually
produce liquid.  A few minutes per Blender."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bmesh  # noqa: E402
import bpy  # noqa: E402
from aquasuite.level2 import rain_sim, still_water as sw  # noqa: E402

FRAMES = 16


def _bake(u):
    """Bake frames 1..FRAMES; return liquid volume (m^3) at mid and end."""
    dom = sw.find_domain_object(lib.entry(u))
    ds = dom.modifiers["AQS Fluid"].domain_settings
    ds.cache_frame_start, ds.cache_frame_end = 1, FRAMES
    with bpy.context.temp_override(active_object=dom, object=dom,
                                   selected_objects=[dom],
                                   selected_editable_objects=[dom]):
        bpy.ops.fluid.bake_all()
    vols = []
    for f in (FRAMES // 2, FRAMES):
        lib.scene().frame_set(f)
        ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        # an unbaked/empty domain falls back to its 8-vertex box
        if len(me.vertices) <= 8:
            vols.append(0.0)
        else:
            bm = bmesh.new()
            bm.from_mesh(me)
            vols.append(abs(bm.calc_volume()))
            bm.free()
        ev.to_mesh_clear()
    return vols


def _report(name, vols, min_end, growing=False):
    ok = vols[-1] >= min_end and (not growing or vols[-1] > vols[0] * 1.2)
    lib.check(f"{name} bake produces liquid", ok,
              f"liquid m3 at frames {FRAMES // 2}/{FRAMES}: "
              f"{vols[0]:.4f}/{vols[1]:.4f} (need >= {min_end}"
              + (", growing)" if growing else ")"))


def test_bakes():
    if not lib.BAKE:
        lib.skip("bake tests", "run with --bake")
        return
    lib.save_blend("bakes")
    lib.scene().frame_start, lib.scene().frame_end = 1, FRAMES

    lib.make_active(lib.add_cube(location=(0, 0, 1), name="WaterBlock"))
    bpy.ops.aquasuite.still_water_create()
    u = lib.last_uuid()
    lib.entry(u).base_resolution = 32
    from aquasuite.core import bakes
    before = bakes.has_bake(lib.entry(u))
    _report("Still Water", _bake(u), 0.05)
    lib.check("liquid bake state: none before, baked after (button red -> blue)",
              not before and bakes.has_bake(lib.entry(u)))

    bpy.ops.aquasuite.hose_create()
    u = lib.last_uuid()
    lib.entry(u).hose_liquid = True
    lib.entry(u).base_resolution = 48           # Draft halves it
    _report("Hose (Normal)", _bake(u), 0.01, growing=True)

    bpy.ops.aquasuite.rain_sim_create(rate=150)
    u = lib.last_uuid()
    pool = lib.add_cube(location=(0, 0, 0.2), name="Pool")
    pool.scale = (4.4, 4.4, 0.4)
    bpy.ops.object.transform_apply(scale=True)
    lib.make_active(pool)
    bpy.ops.aquasuite.rain_sim_add_pool(uuid=u)
    lib.scene().frame_set(10)
    bpy.context.view_layer.update()
    em = rain_sim.find_emitter(lib.entry(u))
    dg = bpy.context.evaluated_depsgraph_get()
    mw = em.matrix_world
    level = rain_sim.water_level(lib.entry(u))
    drop_z = sorted((mw @ v.co).z for v in em.evaluated_get(dg).data.vertices)
    low = [z for z in drop_z if z < mw.translation.z - 0.01]   # skip the plane outline
    lib.check("Rain Sim emitter only holds drops near the water",
              bool(low) and max(low) < level + 1.0,
              f"drop z {min(low):.2f}..{max(low):.2f}, water {level:.2f}" if low else "no drops")
    # liquid touching the domain walls has an open surface, so measured
    # volume under-reads; the check only separates "real liquid" from empty
    _report("Rain Sim (pool)", _bake(u), 0.1)


lib.main(globals())
