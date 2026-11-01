# SPDX-License-Identifier: GPL-3.0-or-later
"""Floating Objects: the scene collection, per-object settings, keys that
always come off again (button, Outliner, Clear, Free, Delete), the panel,
and Plane Ocean floaters whose waterline comes from a density."""

import os
import sys
import types

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


def _tank(preset="STILL_CALM", x=0.0):
    """A Still Water setup (not baked) at x; returns its uuid."""
    water = lib.add_cube(location=(x, 0, 0.5), name="WaterBlock")
    water.scale = (3.0, 3.0, 1.0)
    bpy.context.view_layer.update()
    lib.make_active(water)
    bpy.ops.aquasuite.still_water_create(preset=preset)
    e = lib.entry(lib.last_uuid())
    dom = sw.find_domain_object(e)
    dom.location, dom.scale = (x, 0, 1.0), (3.0, 3.0, 2.0)
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


def _settle(rho_body, rho_liquid, seconds=8.0, fps=24):
    """A 0.5 m cube on flat liquid up to z = 1 (no bake): the settled body."""
    tank = types.SimpleNamespace(lo=np.array((-1.5, -1.5, 0.0)), hi=np.array((1.5, 1.5, 2.0)), cell=0.05)
    cube = lib.add_cube(location=(0, 0, 1.0), size=0.5, name="Settle")
    body = fl.Body(cube, density=rho_body, params=dict(liquid_density=rho_liquid))
    plane = fl.Plane(0.0, 0.0, 1.0, wet=True)
    for _f in range(int(seconds * fps)):
        fl.advance([body], [(plane, plane)], tank, 1.0 / fps)
    body.bottom = float((body.hull @ body.rotation().T + body.x)[:, 2].min())
    bpy.data.objects.remove(cube)
    return body


def test_liquid_density_from_the_setup():
    uid = _tank()
    lib.check("no setup: water", floating.liquid_density(None) == fl.RHO_WATER)
    for key, package in presets.CATALOG.items():
        if "liquid" not in package:
            lib.entry(uid).preset_id = key
            lib.check(f"{key}: water", floating.liquid_density(lib.entry(uid)) == fl.RHO_WATER)
    lib.entry(uid).preset_id = ""
    lib.check("no preset: water", floating.liquid_density(lib.entry(uid)) == fl.RHO_WATER)
    bpy.ops.aquasuite.assembly_delete(uuid=uid)
    for key, rho in (("WATER", 1000.0), ("OIL", 915.0), ("HONEY", 1420.0)):
        uid = _tank(f"STILL_{key}", 10.0)
        got = floating.liquid_density(lib.entry(uid))
        lib.check(f"{key} preset: density {rho:.0f}", got == rho, f"{got}")
        bpy.ops.aquasuite.assembly_delete(uuid=uid)


def test_note_follows_the_liquid():
    oil, honey, water = (_tank(f"STILL_{k}", x) for k, x in
                         (("OIL", 10.0), ("HONEY", 20.0), ("WATER", 30.0)))
    box = lib.add_cube(location=(10, 0, 1.2), size=0.5, name="NoteBox")
    s = box.aqs_float

    def note(uid):
        return floating.buoyancy_note(box, lib.entry(uid))

    s.material = "ICE"
    lib.check("ice floats in water", note(water).endswith("floats ~92% submerged"), note(water))
    lib.check("ice sinks in oil (917 against 915)", note(oil).endswith("sinks"), note(oil))
    s.material = "RUBBER"
    lib.check("rubber sinks in water", note(water).endswith("sinks"), note(water))
    lib.check("rubber floats in honey (1100 against 1420)",
              note(honey).endswith("floats ~77% submerged"), note(honey))
    s.material = "WOOD"
    lib.check("wood sits higher in honey than in water",
              note(honey).endswith("floats ~42% submerged")
              and note(water).endswith("floats ~60% submerged"), note(honey))
    s.material = "ICE"
    _select(box)
    bpy.ops.aquasuite.floating_add()
    log = []
    panel._draw_floating(_Layout(log), bpy.context, lib.entry(oil))
    labels = [x[1] for x in log if x[0] == "label"]
    lib.check("the panel's note uses the tank's liquid",
              any(t.endswith("· sinks") for t in labels), str(labels))
    _select(box)
    bpy.ops.aquasuite.floating_remove()
    bpy.data.objects.remove(box)
    for uid in (oil, honey, water):
        bpy.ops.aquasuite.assembly_delete(uuid=uid)


def test_physics_follows_the_liquid():
    tol = 0.01
    ice_oil = _settle(917.0, 915.0)
    # Only 2 kg/m^3 of difference: it goes under, then drifts down at the
    # speed where linear drag balances it, 2 g / (915 x 5) = 4.3 mm/s.
    lib.check("ice sinks in oil (917 against 915): fully under, still going down",
              abs(ice_oil.vsub / ice_oil.volume - 1.0) < 1e-6
              and abs(ice_oil.v[2] + 2 * fl.GRAVITY / (915.0 * 5.0)) < 1e-3,
              f"{ice_oil.vsub / ice_oil.volume:.3f}, speed {ice_oil.v[2]:.4f}")
    ice_water = _settle(917.0, 1000.0)
    lib.check("ice floats ~92% deep in water", abs(ice_water.vsub / ice_water.volume - 0.917) < 0.03,
              f"{ice_water.vsub / ice_water.volume:.3f}")
    rubber_water = _settle(1100.0, 1000.0)
    lib.check("rubber sinks to the floor in water", abs(rubber_water.bottom) < tol,
              f"bottom {rubber_water.bottom:.3f}")
    rubber_honey = _settle(1100.0, 1420.0)
    frac = rubber_honey.vsub / rubber_honey.volume
    lib.check("rubber floats ~77% deep in honey", abs(frac - 1100.0 / 1420.0) < 0.03
              and rubber_honey.bottom > 0.5, f"{frac:.3f}, bottom {rubber_honey.bottom:.3f}")


def test_physics_water_is_the_default():
    """A body told nothing and one told water behave identically, bit for bit."""
    tank = types.SimpleNamespace(lo=np.array((-1.5, -1.5, 0.0)), hi=np.array((1.5, 1.5, 2.0)), cell=0.05)
    cube = lib.add_cube(location=(0, 0, 1.3), size=0.5, name="Same")
    cube.rotation_euler = (0.2, 0.1, 0.0)
    bpy.context.view_layer.update()
    plain = fl.Body(cube, density=600.0)
    water = fl.Body(cube, density=600.0, params=dict(liquid_density=1000.0))
    plane = fl.Plane(0.0, 0.0, 1.0, 0.05, -0.02, np.array((0.1, 0.0, 0.05)), True)
    for _f in range(48):
        fl.advance([plain, water], [(plane, plane)] * 2, tank, 1.0 / 24)
    lib.check("water setups stay at exactly 1000", plain.p["liquid_density"] == 1000.0)
    lib.check("same path with or without the parameter",
              (plain.x == water.x).all() and (plain.q == water.q).all() and (plain.v == water.v).all())
    bpy.data.objects.remove(cube)


class _Stop(Exception):
    pass


def test_both_bakes_get_the_density():
    """The two drivers build their bodies from the setup's liquid.  Stops
    before anything is baked."""
    e = lib.entry(_tank("STILL_OIL", 10.0))
    box = lib.add_cube(location=(10, 0, 1.2), size=0.5, name="Driven")
    _select(box)
    bpy.ops.aquasuite.floating_add()
    seen = {}

    def spy_bake(_scene, _dom, _objs, *_a, params=None, **_k):
        seen["one way"] = params

    class SpyCoupled:
        def __init__(self, _scene, _dom, _objs, params=None, **_k):
            seen["coupled"] = params
            raise _Stop()

    real_bake, real_coupled = fl.bake, fl.CoupledBake
    fl.bake, fl.CoupledBake = spy_bake, SpyCoupled
    try:
        floating.bake_one_way(bpy.context, e)
        try:
            floating.bake_coupled(bpy.context, e, lambda *_a: None)
        except _Stop:
            pass
    finally:
        fl.bake, fl.CoupledBake = real_bake, real_coupled
    for driver in ("one way", "coupled"):
        lib.check(f"{driver}: the bake gets oil's density",
                  seen.get(driver, {}).get("liquid_density") == 915.0, str(seen.get(driver)))
    dom = sw.find_domain_object(e)
    params = floating._body_params(e, dom)
    coupled = fl.CoupledBake(lib.scene(), dom, [box], params=params)
    lib.check("CoupledBake's bodies carry it", coupled.bodies[0].p["liquid_density"] == 915.0)
    bodies, _timing = fl.bake(lib.scene(), dom, [box], 1, 1, params=params, write=False)
    lib.check("bake's bodies carry it", bodies[0].p["liquid_density"] == 915.0)
    _select(box)
    bpy.ops.aquasuite.floating_remove()
    bpy.data.objects.remove(box)
    bpy.ops.aquasuite.assembly_delete(uuid=e.uuid)


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


def _baked_tank(name, res=48, frames=48, preset="STILL_CALM"):
    lib.save_blend(name)
    sc = lib.scene()
    sc.frame_start, sc.frame_end = 1, frames
    uid = _tank(preset)
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


def _float_in(preset, material, name):
    """One-way Bake Floaters: a 0.5 m cube of this material in a baked tank of
    this liquid; returns (cube's height after 72 frames, tank floor, level)."""
    bpy.ops.wm.read_homefile(use_empty=True)
    uid = _baked_tank(name, frames=72, preset=preset)
    e = lib.entry(uid)
    cube = lib.add_cube(location=(0, 0, 1.13), size=0.5, name="Cube")
    bpy.context.view_layer.update()
    _select(cube)
    bpy.ops.aquasuite.floating_add()
    cube.aqs_float.material = material
    bpy.ops.aquasuite.bake_fluid(uuid=uid)
    r = bpy.ops.aquasuite.bake_floaters(uuid=uid)
    lib.check(f"{preset}: Bake Floaters keys the cube", r == {"FINISHED"})
    lib.scene().frame_set(72)
    dom = sw.find_domain_object(e)
    tank = fl.Tank(dom)
    surface = fl.Surface.from_domain(dom, bpy.context.evaluated_depsgraph_get())
    level = fl.sample_plane(surface, fl.Body(cube), tank, 0.15).h0
    return cube.matrix_world.translation.z, tank.lo[2], level


def test_bake_ice_goes_under_in_oil():
    if not lib.BAKE:
        lib.skip("ice in baked oil", "run with --bake")
        return
    z, _floor, level = _float_in("STILL_OIL", "ICE", "floating_oil")
    lib.check("ice goes under the oil's surface (in water 8% stays out)", z + 0.25 < level + 0.02,
              f"top {z + 0.25:.3f}, level {level:.3f}")


def test_bake_rubber_floats_in_honey():
    if not lib.BAKE:
        lib.skip("rubber in baked honey", "run with --bake")
        return
    z, floor, level = _float_in("STILL_HONEY", "RUBBER", "floating_honey")
    lib.check("rubber stays up in honey (in water it reaches the floor)",
              z - 0.25 > floor + 0.1 and z + 0.25 > level, f"z {z:.3f}, floor {floor:.3f}, level {level:.3f}")


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
