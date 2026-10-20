# SPDX-License-Identifier: GPL-3.0-or-later
"""Rename-safe lookups, reversible delete, refcounted obstacles, bake cache."""

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


def test_delete_restores_source_and_cache():
    src = OBJ["src"]
    _fluid_mods(src)[0].name = "My Flow"
    cdir = delete.cache_dir(U["still"])
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "x.bin"), "wb") as fh:
        fh.write(bytes(2048))
    bpy.ops.aquasuite.assembly_delete(uuid=U["still"], delete_cache=True)
    lib.check("renamed source Flow removed, source restored",
              not _fluid_mods(src) and C.SRC_PROP not in src.keys()
              and src.display_type == "TEXTURED", str([m.name for m in src.modifiers]))
    lib.check("cache removed when asked", not os.path.isdir(cdir))
    cdir2 = delete.cache_dir(U["rs"])
    os.makedirs(cdir2, exist_ok=True)
    bpy.ops.aquasuite.assembly_delete(uuid=U["rs"])            # cache kept by default
    lib.check("cache kept by default", os.path.isdir(cdir2))


lib.main(globals())
