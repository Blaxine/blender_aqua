# SPDX-License-Identifier: GPL-3.0-or-later
"""Floating objects (level2/floaters.py, prototype): mass from density and
mesh volume, float/sink on a synthetic flat water box, keyframes and their
removal, the "pushes water" effector kept out of the Water Obstacles sync;
with --bake, wood/ice/steel in a baked Still Water tank."""

import math
import os
import sys
import types

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Euler  # noqa: E402
from aquasuite.core import obstacles  # noqa: E402
from aquasuite.level2 import floaters as fl  # noqa: E402

LEVEL = 1.0
TANK = types.SimpleNamespace(lo=np.array((-1.5, -1.5, 0.0)), hi=np.array((1.5, 1.5, 2.0)),
                             cell=0.05)


def _water_box():
    """A closed box of 'liquid' from the floor to LEVEL, as Mantaflow
    would mesh still water."""
    (x0, y0, z0), (x1, y1) = TANK.lo, TANK.hi[:2]
    v = np.array([(x, y, z) for z in (z0, LEVEL) for y in (y0, y1) for x in (x0, x1)], float)
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    tris = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
    return fl.Surface(v, np.array(tris))


def _float(objs, densities, seconds=6.0, fps=24):
    surf = _water_box()
    bodies = [fl.Body(o, density=densities[o.name]) for o in objs]
    gap = 2 * TANK.cell
    for f in range(int(seconds * fps)):
        planes = [fl.sample_plane(surf, b, TANK, gap) for b in bodies]
        fl.advance(bodies, [(p, p) for p in planes], TANK, 1.0 / fps)
        for b, p in zip(bodies, planes):
            fl._record(b, f + 1, p)
    return bodies


def test_mass_from_density_and_volume():
    cube = lib.add_cube(location=(0, 0, 3), size=0.5, name="MassCube")
    b = fl.Body(cube, density=600.0)
    lib.check("mass = density x mesh volume (0.5 m cube of wood: 75 kg)",
              abs(b.volume - 0.125) < 1e-6 and abs(b.mass - 75.0) < 1e-3, f"{b.volume} {b.mass}")
    cube.scale = (2.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    b = fl.Body(cube, density=600.0)
    lib.check("volume includes the object's scale", abs(b.volume - 0.25) < 1e-6, f"{b.volume}")
    b = fl.Body(cube, mass=10.0)
    lib.check("a mass override wins over density", abs(b.mass - 10.0) < 1e-9
              and abs(b.density - 40.0) < 1e-6, f"{b.mass} {b.density}")
    ixx = b.mass * (0.5 ** 2 + 0.5 ** 2) / 12
    lib.check("inertia from the sample points matches the box formula (5%)",
              abs(b.inertia[0, 0] - ixx) < 0.05 * ixx and abs(b.com_local).max() < 1e-6,
              f"{b.inertia[0, 0]:.4f} vs {ixx:.4f}")
    bpy.data.objects.remove(cube)


def test_open_meshes_rejected():
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, 3))
    plane = bpy.context.active_object
    ok, why = fl.eligible(plane)
    lib.check("an open mesh can't float (its volume is undefined)", not ok and "holes" in why, why)
    bpy.data.objects.remove(plane)


def test_float_and_sink_on_flat_water():
    specs = {"Plank": (600.0, (-0.8, -0.8)), "Ice": (917.0, (0.8, -0.8)),
             "Steel": (7800.0, (0.0, 0.8)), "Cork": (240.0, (-0.8, 0.8))}
    objs = []
    for name, (_rho, (x, y)) in specs.items():
        o = lib.add_cube(location=(x, y, LEVEL + 0.25), size=0.5, name=name)
        if name == "Plank":
            o.scale.z = 0.4
            o.location.z = LEVEL + 0.1
        objs.append(o)
    bpy.context.view_layer.update()
    bodies = _float(objs, {k: v[0] for k, v in specs.items()})
    got = {b.obj.name: b for b in bodies}
    for name in ("Plank", "Ice", "Cork"):
        b = got[name]
        frac = np.mean([t["vsub"] for t in b.track[-24:]]) / b.volume
        want = b.density / fl.RHO_WATER
        lib.check(f"{name} floats with {want:.0%} of its volume under water (+-0.03)",
                  abs(frac - want) < 0.03, f"{frac:.3f}")
    z = [t["com"][2] for t in got["Plank"].track[-24:]]
    lib.check("the wood plank has settled after 6 s (bob < 5 mm)", max(z) - min(z) < 0.005,
              f"{1000 * (max(z) - min(z)):.1f} mm")
    s = got["Steel"]
    bottom = (s.hull @ s.rotation().T + s.x)[:, 2].min()
    lib.check("steel sinks and rests on the floor", abs(bottom - TANK.lo[2]) < 0.01
              and np.linalg.norm(s.v) < 0.05, f"bottom {bottom:.3f}, speed {np.linalg.norm(s.v):.3f}")
    for o in objs:
        bpy.data.objects.remove(o)


def test_level_wood_cube_tips_over():
    """A cube of density 0.6 is unstable upright (negative metacentric
    height): the centre-of-buoyancy torque must turn it."""
    o = lib.add_cube(location=(0, 0, LEVEL + 0.25), size=0.5, name="TipCube")
    o.rotation_euler = Euler((math.radians(3), math.radians(2), 0))
    bpy.context.view_layer.update()
    b = _float([o], {"TipCube": 600.0}, seconds=8.0)[0]
    up = b.rotation() @ np.array((0, 0, 1.0))
    tilt = math.degrees(math.acos(min(1.0, abs(up[2]))))
    lib.check("a wood cube rolls off its face (> 20 degrees)", tilt > 20, f"{tilt:.1f} deg")
    bpy.data.objects.remove(o)


def test_buoy_offset_from_density():
    """Plane Ocean buoys: density -> the static waterline offset."""
    o = lib.add_cube(location=(0, 0, 3), size=0.5, name="BuoyCube")
    wood, ice, steel = (fl.buoy_offset(o, d) for d in (600.0, 917.0, 7800.0))
    lib.check("wood cube origin sits 5 cm under the waterline, ice 21 cm; steel sinks",
              abs(wood + 0.05) < 0.005 and abs(ice + 0.2085) < 0.005 and steel is None,
              f"{wood:.4f} {ice:.4f} {steel}")
    bpy.data.objects.remove(o)


def test_keyframes_and_restore():
    o = lib.add_cube(location=(0.3, 0.2, LEVEL + 0.2), size=0.5, name="Keyed")
    o.rotation_euler = (0.1, 0.0, 0.0)
    o.keyframe_insert("location", frame=1)
    user_action = o.animation_data.action
    o.location = (0.3, 0.2, LEVEL + 0.2)
    bpy.context.view_layer.update()
    b = _float([o], {"Keyed": 600.0}, seconds=1.0)[0]
    fl.write_keyframes(b)
    act = o.animation_data.action
    act_name = act.name
    lib.check("Bake Floaters keys the object in its own action",
              act is not None and act != user_action and act.get(lib.C.OWNER_PROP, "").startswith("FLOAT:"))
    lib.scene().frame_set(24)
    moved = abs(o.location.z - (LEVEL + 0.2)) > 0.01
    fl.clear(o)
    lib.check("keys move the object; clearing restores its own action and transform",
              moved and o.animation_data.action == user_action
              and abs(o.location.z - (LEVEL + 0.2)) < 1e-6 and abs(o.rotation_euler.x - 0.1) < 1e-6
              and fl.RESTORE_PROP not in o.keys() and act_name not in bpy.data.actions,
              f"moved={moved} action={o.animation_data.action}")
    bpy.data.objects.remove(o)


def test_pushes_water_effector_is_not_an_obstacle():
    o = lib.add_cube(location=(0, 0, 3), size=0.5, name="Pusher")
    fl.set_pushes_water(o, True)
    obstacles.sync(lib.scene())
    bpy.context.view_layer.update()
    mod = next((m for m in o.modifiers if m.type == "FLUID"), None)
    lib.check("Pushes water adds a collision effector the obstacle sync leaves alone",
              mod is not None and mod.fluid_type == "EFFECTOR" and o.get(fl.EFFECTOR_PROP)
              and obstacles.MARK_PROP not in o.keys()
              and mod.effector_settings.surface_distance == 0.0)
    fl.set_pushes_water(o, False)
    lib.check("turning it off removes only that effector",
              not any(m.type == "FLUID" for m in o.modifiers) and fl.EFFECTOR_PROP not in o.keys())
    bpy.data.objects.remove(o)


def test_bake_still_water():
    if not lib.BAKE:
        lib.skip("floaters on baked Still Water", "run with --bake")
        return
    from aquasuite.core import presets
    from aquasuite.level2 import still_water as sw
    lib.save_blend("floaters")
    sc = lib.scene()
    sc.frame_start, sc.frame_end = 1, 120
    if "Cube" in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects["Cube"])
    water = lib.add_cube(location=(0, 0, 0.5), name="WaterBlock")
    water.scale = (3.0, 3.0, 1.0)
    bpy.context.view_layer.update()
    lib.make_active(water)
    bpy.ops.aquasuite.still_water_create(preset="STILL_CALM")
    e = lib.entry(lib.last_uuid())
    dom = sw.find_domain_object(e)
    dom.location, dom.scale = (0, 0, 1.0), (3.0, 3.0, 2.0)
    ds = presets.domain(e)[1]
    e.base_resolution = 48
    ds.resolution_max = 48       # 6 cm cells: 8 across a 0.5 m cube
    ds.cache_frame_start, ds.cache_frame_end = 1, 120
    bpy.context.view_layer.update()
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                   selected_editable_objects=[dom]):
        bpy.ops.fluid.bake_all()
    tank = fl.Tank(dom)
    level = 1.03  # measured: the border cells raise a 1 m block to ~1.03 m at 48
    specs = {"Plank": (600.0, (-0.7, -0.7)), "Ice": (917.0, (0.7, -0.7)),
             "Steel": (7800.0, (0.0, 0.7))}
    objs = []
    for name, (_rho, (x, y)) in specs.items():
        o = lib.add_cube(location=(x, y, level + 0.25), size=0.5, name=name)
        if name == "Plank":
            o.scale.z = 0.4
            o.location.z = level + 0.1
        objs.append(o)
    bpy.context.view_layer.update()
    bodies, timing = fl.bake(sc, dom, objs, 1, 120, densities={k: v[0] for k, v in specs.items()})
    got = {b.obj.name: b for b in bodies}
    for name, lo, hi in (("Plank", 0.54, 0.66), ("Ice", 0.87, 0.97)):
        b = got[name]
        frac = np.mean([t["vsub"] for t in b.track[-24:]]) / b.volume
        lib.check(f"{name} floats {lo:.0%}-{hi:.0%} submerged on baked water", lo <= frac <= hi,
                  f"{frac:.3f}")
    s = got["Steel"]
    bottom = (s.hull @ s.rotation().T + s.x)[:, 2].min()
    lib.check("steel rests on the tank floor", abs(bottom - tank.lo[2]) < 0.02, f"{bottom:.3f}")
    keyed = all(o.animation_data and o.animation_data.action for o in objs)
    lib.check("every floater is keyed", keyed)
    print(f"{lib.TAG} INFO | [floaters] {1000 * (timing['surface'] + timing['dynamics']) / 119:.0f} "
          f"ms/frame for 3 objects on {timing['verts']} liquid verts", flush=True)
    for o in objs:
        fl.clear(o)
    lib.check("clearing removes every floater action",
              not any(a.get(lib.C.OWNER_PROP, "").startswith("FLOAT:") for a in bpy.data.actions))


lib.main(globals())
