# SPDX-License-Identifier: GPL-3.0-or-later
"""Rename-safe lookups, reversible delete, refcounted obstacles, bake cache."""

import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import delete  # noqa: E402
from aquasuite.level1 import ocean as oc  # noqa: E402
from aquasuite.level2 import rain_sim, still_water as sw  # noqa: E402

C = lib.C
U = {}
OBJ = {}


def _fluid_mods(obj):
    return [m for m in obj.modifiers if m.type == "FLUID"]


def test_setup():
    lib.save_blend("ownership")          # cache paths need a saved file
    lib.scene().frame_start, lib.scene().frame_end = 1, 24
    OBJ["src"] = lib.add_cube(location=(30, 0, 1), name="UserCube")
    lib.make_active(OBJ["src"])
    bpy.ops.aquasuite.still_water_create()
    U["still"] = lib.last_uuid()
    bpy.ops.aquasuite.rain_sim_create()
    U["rs"] = lib.last_uuid()
    bpy.ops.aquasuite.ocean_create()
    U["ocean"] = lib.last_uuid()
    lib.check("setups created", all(lib.entry(u) for u in U.values()))


def test_ocean_rename_keeps_buoys():
    surf = lib.entry(U["ocean"]).primary
    boat = lib.add_cube(location=(1, 2, 0), name="Boat")
    OBJ["boat"] = boat
    bpy.ops.aquasuite.ocean_attach_buoy(uuid=U["ocean"])
    lib.scene().frame_set(10)
    z1 = boat.matrix_world.translation.z
    oc.find_ocean_modifier(surf, U["ocean"]).node_group.name = "MyOcean"
    lib.scene().frame_set(30)
    z2 = boat.matrix_world.translation.z
    lib.check("renamed ocean tree: buoy still attached and moving",
              len(lib.entry(U["ocean"]).buoys) == 1 and len(boat.constraints) == 2
              and abs(z2 - z1) > 1e-6, f"z {z1:.3f} -> {z2:.3f}")


def test_rain_rename_still_found():
    e = lib.entry(U["rs"])
    mod = rain_sim._drops_modifier(rain_sim.find_emitter(e), U["rs"])
    mod.node_group.name = "MyRain"
    e = lib.entry(U["rs"])
    lib.check("renamed drop tree: emitter still found",
              rain_sim.find_emitter(e) is not None
              and rain_sim._drops_modifier(rain_sim.find_emitter(e), U["rs"]) is not None)


def test_surface_deleted_detaches_buoys():
    surf = lib.entry(U["ocean"]).primary
    bpy.data.objects.remove(surf, do_unlink=True)
    lib.scene().frame_set(31)
    lib.check("ocean surface deleted: buoys detached",
              len(lib.entry(U["ocean"]).buoys) == 0 and len(OBJ["boat"].constraints) == 0)


def test_delete_restores_and_releases():
    src = OBJ["src"]
    _fluid_mods(src)[0].name = "My Flow"
    obst = lib.add_cube(location=(30, 0, -1), name="Obstacle")
    obst.modifiers.new("Collision", "COLLISION")
    sw.refresh_obstacles(lib.scene(), lib.entry(U["still"]))
    _fluid_mods(obst)[0].name = "My Effector"
    sw.refresh_obstacles(lib.scene(), lib.entry(U["rs"]))      # now shared
    cdir = delete.cache_dir(U["still"])
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "x.bin"), "wb") as fh:
        fh.write(b"\0" * 2048)
    bpy.ops.aquasuite.assembly_delete(uuid=U["still"], delete_cache=True)
    lib.check("renamed source Flow removed, source restored",
              not _fluid_mods(src) and C.SRC_PROP not in src.keys()
              and src.display_type == "TEXTURED", str([m.name for m in src.modifiers]))
    lib.check("shared effector kept for the remaining owner",
              bool(_fluid_mods(obst))
              and json.loads(obst[C.EFFECTOR_OWNERS_PROP]) == [U["rs"]])
    lib.check("cache removed when asked", not os.path.isdir(cdir))

    cdir2 = delete.cache_dir(U["rs"])
    os.makedirs(cdir2, exist_ok=True)
    bpy.ops.aquasuite.assembly_delete(uuid=U["rs"])            # cache kept by default
    lib.check("renamed effector removed with its last owner",
              not _fluid_mods(obst) and C.EFFECTOR_OWNERS_PROP not in obst.keys(),
              str([m.name for m in obst.modifiers]))
    lib.check("cache kept by default", os.path.isdir(cdir2))


def test_obstacle_refresh_scoped():
    lib.make_active(lib.add_cube(location=(50, 0, 1)))
    bpy.ops.aquasuite.still_water_create()
    a1 = lib.last_uuid()
    lib.make_active(lib.add_cube(location=(60, 0, 1), size=4))
    bpy.ops.aquasuite.still_water_create()
    a2 = lib.last_uuid()
    lib.entry(a1).base_resolution = 160
    lib.entry(a2).base_resolution = 32
    shared = lib.add_cube(location=(55, 0, -1))
    shared.modifiers.new("Collision", "COLLISION")
    sw.refresh_obstacles(lib.scene(), lib.entry(a2))
    d_a2 = _fluid_mods(shared)[0].effector_settings.surface_distance
    sw.refresh_obstacles(lib.scene(), lib.entry(a1))
    d_after = _fluid_mods(shared)[0].effector_settings.surface_distance
    only2 = lib.add_cube(location=(65, 0, -1))
    only2.modifiers.new("Collision", "COLLISION")
    sw.refresh_obstacles(lib.scene(), lib.entry(a2))
    only2.modifiers.remove(only2.modifiers["Collision"])
    es2 = _fluid_mods(only2)[0].effector_settings
    es2.surface_distance = 0.123
    sw.refresh_obstacles(lib.scene(), lib.entry(a1))
    lib.check("shared obstacle keeps the thicker surface distance",
              d_after >= d_a2, f"a2 set {d_a2:.3f}, after a1 {d_after:.3f}")
    lib.check("another assembly's obstacle untouched",
              abs(es2.surface_distance - 0.123) < 1e-6, f"{es2.surface_distance:.3f}")


lib.main(globals())
