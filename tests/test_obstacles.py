# SPDX-License-Identifier: GPL-3.0-or-later
"""Water Obstacles: membership is the only obstacle rule; adding gives an
object what it needs, removing (button or by hand) undoes exactly that;
hose jets bounce only off the collection."""

import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from mathutils import Euler  # noqa: E402
from aquasuite.core import obstacles  # noqa: E402
from aquasuite.level3 import hose  # noqa: E402

OBJ = {}


def _types(obj):
    return sorted(m.type for m in obj.modifiers)


def _select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    lib.make_active(objs[0])


def test_add_and_remove():
    box = lib.add_cube(location=(5, 0, 0), name="Box")
    OBJ["box"] = box
    _select(box)
    bpy.ops.aquasuite.obstacles_add()
    col = obstacles.collection(lib.scene())
    lib.check("collection created and holds the object",
              col is not None and box.name in col.objects)
    lib.check("obstacle gets Collision + Fluid effector",
              _types(box) == ["COLLISION", "FLUID"]
              and box.modifiers[-1].fluid_type == "EFFECTOR", str(_types(box)))
    lib.check("added collision splats instead of bouncing",
              box.collision.damping_factor >= 0.8)
    _select(box)
    bpy.ops.aquasuite.obstacles_remove()
    lib.check("remove undoes everything AquaSuite added",
              _types(box) == [] and obstacles.MARK_PROP not in box.keys(), str(_types(box)))


def test_user_modifiers_untouched():
    wall = lib.add_cube(location=(8, 0, 0), name="Wall")
    wall.modifiers.new("My Collision", "COLLISION")
    wall.collision.damping_factor = 0.123
    _select(wall)
    bpy.ops.aquasuite.obstacles_add()
    lib.check("existing Collision kept as is; only a Fluid effector added",
              _types(wall) == ["COLLISION", "FLUID"]
              and abs(wall.collision.damping_factor - 0.123) < 1e-6)
    _select(wall)
    bpy.ops.aquasuite.obstacles_remove()
    lib.check("remove keeps the user's own Collision",
              _types(wall) == ["COLLISION"] and wall.modifiers[0].name == "My Collision")


def test_water_sources_rejected():
    src = lib.add_cube(location=(11, 0, 1), name="Source")
    lib.make_active(src)
    bpy.ops.aquasuite.still_water_create()
    _select(src)
    try:
        bpy.ops.aquasuite.obstacles_add()
    except RuntimeError:
        pass
    col = obstacles.collection(lib.scene())
    lib.check("a Still Water source can't be an obstacle",
              src.name not in col.objects and "COLLISION" not in _types(src))


def test_manual_unlink_undoes():
    box = OBJ["box"]
    _select(box)
    bpy.ops.aquasuite.obstacles_add()
    obstacles.collection(lib.scene()).objects.unlink(box)   # by hand, Outliner-style
    bpy.context.view_layer.update()                          # depsgraph handler syncs
    lib.check("unlinking by hand removes what AquaSuite added",
              _types(box) == [] and obstacles.MARK_PROP not in box.keys(), str(_types(box)))


def _below_floor(in_collection):
    bpy.ops.aquasuite.hose_create()
    e = lib.entry(lib.last_uuid())
    e.primary.location = (0, 30 if in_collection else 60, 2)
    e.primary.rotation_euler = Euler((0, math.radians(-30), 0))
    floor_y = 30 if in_collection else 60
    bpy.ops.mesh.primitive_plane_add(size=20, location=(3, floor_y, 0))
    floor = bpy.context.active_object
    if in_collection:
        _select(floor)
        bpy.ops.aquasuite.obstacles_add()
    else:
        floor.modifiers.new("Collision", "COLLISION")      # NOT in the collection
    for f in range(1, 31):
        lib.scene().frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    psys, _ = hose._psys(hose._find_emitter(e).evaluated_get(dg), "jet")
    alive = [p for p in psys.particles if p.alive_state == "ALIVE"]
    return sum(1 for p in alive if p.location.z < -0.05), len(alive)


def test_jet_respects_only_the_collection():
    lib.scene().frame_start, lib.scene().frame_end = 1, 40
    below_in, n_in = _below_floor(True)
    lib.check("jet stops on a floor in Water Obstacles", n_in > 500 and below_in == 0,
              f"{below_in}/{n_in} below")
    below_out, n_out = _below_floor(False)
    lib.check("jet ignores a Collision floor outside Water Obstacles", below_out > 100,
              f"{below_out}/{n_out} below")


lib.main(globals())
