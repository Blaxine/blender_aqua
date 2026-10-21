# SPDX-License-Identifier: GPL-3.0-or-later
"""Floating Objects: the scene collection, per-object settings, keys that
always come off again (button, Outliner, Clear, Free, Delete), the panel,
and Plane Ocean floaters whose waterline comes from a density."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from aquasuite.core import floating, obstacles, presets  # noqa: E402
from aquasuite.level2 import floaters as fl  # noqa: E402
from aquasuite.level2 import still_water as sw  # noqa: E402
from aquasuite.ui import panel  # noqa: E402

UID = {}


def _select(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    lib.make_active(objs[0])


def _types(obj):
    return sorted(m.type for m in obj.modifiers)


def _fake_keys(obj, uuid, dz=0.3):
    """Key the object as a bake would (a short track rising by dz)."""
    body = fl.Body(obj)
    loc, q = body.pose()
    body.track = [dict(frame=f, loc=loc + np.array((0, 0, dz * i / 4)), q=q)
                  for i, f in enumerate(range(1, 6))]
    fl.write_keyframes(body)
    obj[floating.WATER_PROP] = uuid


def _tank():
    """A Still Water setup (not baked) around the origin; returns its uuid."""
    water = lib.add_cube(location=(0, 0, 0.5), name="WaterBlock")
    water.scale = (3.0, 3.0, 1.0)
    bpy.context.view_layer.update()
    lib.make_active(water)
    bpy.ops.aquasuite.still_water_create(preset="STILL_CALM")
    e = lib.entry(lib.last_uuid())
    dom = sw.find_domain_object(e)
    dom.location, dom.scale = (0, 0, 1.0), (3.0, 3.0, 2.0)
    bpy.context.view_layer.update()
    return e.uuid


def test_add_remove_and_eligibility():
    if "Cube" in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects["Cube"])
    box = lib.add_cube(location=(0.5, 0, 1.2), size=0.5, name="Crate")
    _select(box)
    bpy.ops.aquasuite.floating_add()
    col = floating.collection(lib.scene())
    lib.check("collection created and holds the object", col is not None and box.name in col.objects)
    lib.check("adding changes nothing on the object", _types(box) == [] and not box.animation_data)

    bpy.ops.mesh.primitive_plane_add(size=1, location=(5, 0, 0))
    sheet = bpy.context.active_object
    parent = lib.add_cube(location=(6, 0, 0), name="Parent")
    child = lib.add_cube(location=(6, 0, 1), size=0.3, name="Child")
    child.parent = parent
    wall = lib.add_cube(location=(8, 0, 0), name="Wall")
    _select(wall)
    bpy.ops.aquasuite.obstacles_add()
    for obj, why in ((sheet, "an open mesh"), (child, "a parented object"),
                     (wall, "a Water Obstacle")):
        _select(obj)
        try:
            bpy.ops.aquasuite.floating_add()
        except RuntimeError:
            pass
        lib.check(f"{why} can't float", obj.name not in col.objects)
    _select(box)
    try:
        bpy.ops.aquasuite.obstacles_add()
    except RuntimeError:
        pass
    lib.check("a floating object can't be a Water Obstacle",
              box.name not in obstacles.collection(lib.scene()).objects
              and _types(box) == [])
    _select(box)
    bpy.ops.aquasuite.floating_remove()
    lib.check("remove takes it out of the collection", box.name not in col.objects)
    UID["box"] = box.name


def test_material_mass_and_note():
    box = bpy.data.objects[UID["box"]]
    s = box.aqs_float
    s.material = "ICE"
    lib.check("material sets the density", abs(s.density - 917.0) < 1e-6)
    mass, rho = floating.mass_of(box)
    lib.check("mass = density x volume", abs(mass - 917 * 0.125) < 0.01, f"{mass}")
    lib.check("note says how deep it floats", floating.buoyancy_note(box).endswith("floats ~92% submerged"),
              floating.buoyancy_note(box))
    s.use_mass, s.mass = True, 200.0
    lib.check("mass override wins (and sinks)", floating.buoyancy_note(box) == "200 kg · sinks",
              floating.buoyancy_note(box))
    body = fl.Body(box)
    lib.check("the physics uses the same mass", abs(body.mass - 200.0) < 1e-6)
    s.use_mass = False
    s.material = "STEEL"
    lib.check("steel sinks", floating.buoyancy_note(box).endswith("sinks"))
    s.material = "WOOD"


def test_pushes_water_follows_membership():
    box = bpy.data.objects[UID["box"]]
    box.aqs_float.pushes_water = True
    lib.check("Pushes Water does nothing outside the collection", _types(box) == [])
    _select(box)
    bpy.ops.aquasuite.floating_add()
    lib.check("in the collection it gets a collision effector",
              _types(box) == ["FLUID"] and box.modifiers[0].fluid_type == "EFFECTOR"
              and box.get(fl.EFFECTOR_PROP))
    obstacles.sync(lib.scene())
    lib.check("Water Obstacles sync leaves the floater's effector alone", _types(box) == ["FLUID"])
    box.aqs_float.pushes_water = False
    lib.check("switching it off removes the effector", _types(box) == [])
    box.aqs_float.pushes_water = True


def test_outliner_unlink_restores():
    box = bpy.data.objects[UID["box"]]
    box.animation_data_create()
    mine = bpy.data.actions.new("MyAnim")
    box.animation_data.action = mine
    start = box.location.copy()
    _fake_keys(box, "nobody")
    lib.scene().frame_set(5)
    lib.check("keys move the object", abs(box.location.z - start.z - 0.3) < 1e-4)
    floating.collection(lib.scene()).objects.unlink(box)      # by hand
    bpy.context.view_layer.update()                             # depsgraph handler syncs
    lib.scene().frame_set(1)
    lib.check("unlinking by hand removes keys and effector, restores the object",
              _types(box) == [] and (box.location - start).length < 1e-6
              and box.animation_data.action == mine
              and not floating._ours(box), f"{_types(box)} {box.location}")
    box.animation_data.action = None
    bpy.data.actions.remove(mine)


def test_tank_membership_and_warnings():
    uid = _tank()
    UID["tank"] = uid
    e = lib.entry(uid)
    box = bpy.data.objects[UID["box"]]
    away = lib.add_cube(location=(20, 0, 1), size=0.5, name="Away")
    _select(box, away)
    bpy.ops.aquasuite.floating_add()
    lib.check("the tank's floaters are those inside it",
              [o.name for o in floating.floaters_of(e)] == [box.name])
    lib.check("an object in no tank is reported", [o.name for o in floating.outside(lib.scene())] == ["Away"])
    ds = presets.domain(e)[1]
    ds.resolution_max = 24       # 12.5 cm cells: a 0.5 m crate is 4 across
    lib.check("too few cells to push water is a warning",
              any("cells across" in w for w in floating.warnings(box, e)), str(floating.warnings(box, e)))
    ds.resolution_max = 96
    lib.check("enough cells: no warning", floating.warnings(box, e) == [])
    _select(away)
    bpy.ops.aquasuite.floating_remove()


class _Layout:
    """Stands in for UILayout: checks every property and operator the
    panel draws exists."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split"):
            return lambda *a, **k: _Layout(self.log)
        if name == "label":
            return lambda **k: self.log.append(("label", k.get("text", "")))
        if name == "separator":
            return lambda *a, **k: None
        raise AttributeError(name)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def prop(self, owner, name, **k):
        assert name in owner.bl_rna.properties, name
        self.log.append(("prop", name))

    def operator(self, idname, **k):
        mod, op = idname.split(".")
        assert hasattr(getattr(bpy.ops, mod), op), idname
        self.log.append(("operator", idname))
        return _Props()


class _Props:
    pass


def test_panel_draws():
    e = lib.entry(UID["tank"])
    log = []
    panel._draw_floating(_Layout(log), bpy.context, e)
    ops = [x[1] for x in log if x[0] == "operator"]
    labels = " ".join(x[1] for x in log if x[0] == "label")
    lib.check("panel offers add/remove/bake/clear",
              {"aquasuite.floating_add", "aquasuite.floating_remove",
               "aquasuite.bake_floaters", "aquasuite.clear_floaters"} <= set(ops), str(ops))
    lib.check("panel is honest about pushed water", "level doesn't" in labels and "busy" in labels,
              labels)
    for mode in floating.LIQUID_MODES:
        if mode != lib.C.MODE_HOSE:
            from aquasuite.ui import control_spec
            lib.check(f"{mode}: Floating Objects in the panel",
                      "floating" in control_spec.controls(mode)
                      and "floating" in control_spec.controls(mode, True))


def test_clear_free_and_delete_restore():
    e = lib.entry(UID["tank"])
    box = bpy.data.objects[UID["box"]]
    start = box.location.copy()
    _fake_keys(box, e.uuid)
    lib.check("keyed objects are listed for their water", floating.keyed(e) == [box])
    bpy.ops.aquasuite.clear_floaters(uuid=e.uuid)
    lib.scene().frame_set(5)
    lib.check("Clear Floaters restores the object",
              (box.location - start).length < 1e-6 and not (box.animation_data and box.animation_data.action)
              and box.name in floating.collection(lib.scene()).objects)
    _fake_keys(box, e.uuid)
    bpy.ops.aquasuite.assembly_delete(uuid=e.uuid)
    lib.scene().frame_set(5)
    lib.check("deleting the liquid setup restores its floaters",
              (box.location - start).length < 1e-6 and not (box.animation_data and box.animation_data.action)
              and floating.WATER_PROP not in box.keys())
    lib.check("no floater actions left",
              not any(a.get(lib.C.OWNER_PROP, "").startswith("FLOAT:") for a in bpy.data.actions))


def test_plane_ocean_density():
    bpy.ops.aquasuite.ocean_create()
    e = lib.entry(lib.last_uuid())
    raft = lib.add_cube(location=(3, 3, 0), size=0.5, name="Raft")
    lib.make_active(raft)
    bpy.ops.aquasuite.ocean_attach_buoy(uuid=e.uuid, material="WOOD")
    b = e.buoys[0]
    lib.check("Attach Floater with a material sets the waterline",
              abs(b.offset - (-0.05)) < 1e-3, f"{b.offset:.4f}")
    b.material = "ICE"
    lib.check("changing the material moves it", abs(b.offset - (-0.2085)) < 2e-3, f"{b.offset:.4f}")
    b.material = "CUSTOM"
    b.density = 1200.0
    lib.check("a sinking density leaves the offset alone", abs(b.offset - (-0.2085)) < 2e-3,
              f"{b.offset:.4f}")
    items = {i.identifier for i in b.bl_rna.properties["material"].enum_items}
    lib.check("only floating materials are offered", "STEEL" not in items and "WOOD" in items)
    b.material = "MANUAL"
    b.offset = 0.4
    lib.check("Manual keeps the user's offset", abs(b.offset - 0.4) < 1e-6)
    log = []
    panel._draw_floaters(_Layout(log), e)
    lib.check("Plane Ocean floater row draws", ("prop", "material") in log)


def _baked_tank(name, res=48, frames=48):
    lib.save_blend(name)
    sc = lib.scene()
    sc.frame_start, sc.frame_end = 1, frames
    uid = _tank()
    e = lib.entry(uid)
    ds = presets.domain(e)[1]
    e.base_resolution = res
    ds.resolution_max = res
    ds.cache_frame_start, ds.cache_frame_end = 1, frames
    return uid


def _liquid_volume(dom, frame):
    lib.scene().frame_set(frame)
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        v = abs(bm.calc_volume(signed=True)) * float(np.prod(dom.matrix_world.to_scale()))
        bm.free()
    finally:
        ev.to_mesh_clear()
    return v


def test_bake_floaters_one_way():
    if not lib.BAKE:
        lib.skip("Bake Floaters on baked Still Water", "run with --bake")
        return
    bpy.ops.wm.read_homefile(use_empty=True)
    uid = _baked_tank("floating_oneway", frames=72)
    e = lib.entry(uid)
    plank = lib.add_cube(location=(-0.6, 0, 1.13), size=0.5, name="Plank")
    plank.scale.z = 0.4
    steel = lib.add_cube(location=(0.6, 0, 1.28), size=0.5, name="Anchor")
    bpy.context.view_layer.update()
    _select(plank, steel)
    bpy.ops.aquasuite.floating_add()
    steel.aqs_float.material = "STEEL"
    r = bpy.ops.aquasuite.bake_floaters(uuid=uid)
    lib.check("Bake Floaters needs a baked liquid", r == {"CANCELLED"} and not plank.animation_data)
    bpy.ops.aquasuite.bake_fluid(uuid=uid)
    start = plank.location.copy()
    r = bpy.ops.aquasuite.bake_floaters(uuid=uid)
    lib.check("Bake Floaters keys both objects", r == {"FINISHED"}
              and set(floating.keyed(e)) == {plank, steel})
    lib.scene().frame_set(72)
    tank = fl.Tank(sw.find_domain_object(e))
    lib.check("the steel block sinks to the floor",
              abs(steel.matrix_world.translation.z - 0.25 - tank.lo[2]) < 0.03,
              f"{steel.matrix_world.translation.z:.3f}")
    level = fl.sample_plane(
        fl.Surface.from_domain(sw.find_domain_object(e), bpy.context.evaluated_depsgraph_get()),
        fl.Body(plank), tank, 0.15).h0
    draft = (level - (plank.matrix_world.translation.z - 0.1)) / 0.2
    lib.check("the wood plank floats ~60% deep", 0.5 <= draft <= 0.7, f"{draft:.2f}")
    r = bpy.ops.aquasuite.bake_floaters(uuid=uid)
    lib.scene().frame_set(1)
    lib.check("baking again starts from where the user put it",
              r == {"FINISHED"} and (plank.location - start).length < 1e-4)
    bpy.ops.aquasuite.clear_floaters(uuid=uid)
    lib.check("Clear Floaters removes every key", not floating.keyed(e)
              and not (plank.animation_data and plank.animation_data.action) and not (steel.animation_data and steel.animation_data.action))


def test_bake_water_and_floaters():
    """Pushes Water: one blocking bake of the water and floaters together."""
    if not lib.BAKE:
        lib.skip("coupled water + floaters bake", "run with --bake")
        return
    bpy.ops.wm.read_homefile(use_empty=True)
    uid = _baked_tank("floating_coupled", frames=48)
    e = lib.entry(uid)
    dom = sw.find_domain_object(e)
    crate = lib.add_cube(location=(0, 0, 1.5), size=0.5, name="Crate")
    bpy.context.view_layer.update()
    _select(crate)
    bpy.ops.aquasuite.floating_add()
    crate.aqs_float.pushes_water = True
    r = bpy.ops.aquasuite.bake_floaters(uuid=uid)
    ds = presets.domain(e)[1]
    lib.check("one bake: the water is baked and the crate keyed",
              r == {"FINISHED"} and ds.has_cache_baked_any and floating.keyed(e) == [crate])
    v0, v1 = _liquid_volume(dom, 1), _liquid_volume(dom, 48)
    change = (v1 - v0) / v0
    print(f"{lib.TAG} INFO | [floating] coupled bake water volume {change:+.2%}", flush=True)
    lib.check("the dropped crate removes under 1.5% of the water", abs(change) < 0.015, f"{change:+.3%}")
    lib.scene().frame_set(48)
    z = crate.matrix_world.translation.z
    lib.check("the crate fell into the water and floats", 0.8 < z < 1.2, f"{z:.3f}")
    lib.check("fractions stay off", not ds.use_fractions)
    bpy.ops.aquasuite.assembly_delete(uuid=uid)
    lib.scene().frame_set(1)
    lib.check("deleting the setup puts the crate back",
              not (crate.animation_data and crate.animation_data.action) and abs(crate.location.z - 1.5) < 1e-6)


lib.main(globals())
