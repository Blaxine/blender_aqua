# SPDX-License-Identifier: GPL-3.0-or-later
"""Still Water's water-mesh list: Turn Into Water converts the active mesh
only, Add Mesh to Water lists more meshes (entry.pool_sources) and grows the
domain, the per-mesh X gives one back exactly, and Delete/undo restore them
all.  Every liquid domain takes liquid only from its own Flow collection,
never from other setups' meshes or the user's own Fluid flows."""

import os
import sys
import types

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from aquasuite.level2 import still_water as sw  # noqa: E402

C = lib.C


def _reset():
    bpy.ops.wm.read_homefile(use_empty=True)


def _select(objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    lib.make_active(active)


def _cube(name, location, scale=(1.0, 1.0, 1.0)):
    obj = lib.add_cube(location=location, name=name)
    obj.scale = scale
    return obj


def _user_flow(name, location, scale=(0.25, 0.25, 0.25)):
    """The user's own Fluid FLOW mesh, unrelated to AquaSuite."""
    obj = _cube(name, location, scale)
    mod = obj.modifiers.new("My Flow", "FLUID")
    mod.fluid_type = "FLOW"
    mod.flow_settings.flow_type = "LIQUID"
    mod.flow_settings.flow_behavior = "GEOMETRY"
    return obj


def _contains(outer, inner, tol=1e-4):
    return all(outer[0][i] <= inner[0][i] + tol and inner[1][i] <= outer[1][i] + tol
               for i in range(3))


def _same(a, b, tol=1e-4):
    return all(abs(a[k][i] - b[k][i]) <= tol for k in range(2) for i in range(3))


def _domain(u):
    bpy.context.view_layer.update()
    return sw.domain_bounds(sw.find_domain_object(lib.entry(u)))


def _ds(u):
    dom = sw.find_domain_object(lib.entry(u))
    return next(m for m in dom.modifiers if m.type == "FLUID").domain_settings


def _flows(u):
    """Names in the domain's Flow collection ('-' when none is set)."""
    grp = _ds(u).fluid_group
    return sorted(o.name for o in grp.objects) if grp else "-"


def _state(obj):
    """Everything Still Water may change on a user mesh."""
    return dict(mods=[(m.name, m.type) for m in obj.modifiers],
                hide_render=obj.hide_render, display=obj.display_type,
                src=obj.get(C.SRC_PROP), owner=obj.get(C.OWNER_PROP),
                cols=sorted(c.name for c in obj.users_collection))


def _is_water(obj, u):
    flows = [m for m in obj.modifiers
             if m.type == "FLUID" and m.fluid_type == "FLOW"]
    return (len(flows) == 1 and flows[0].flow_settings.flow_behavior == "GEOMETRY"
            and obj.get(C.SRC_PROP) == u and obj.hide_render
            and obj.display_type == "WIRE")


def _three():
    """Three meshes of different sizes far apart; B has a user modifier and
    a non-default display, C is hidden from render."""
    a = _cube("A", (0, 0, 1))
    b = _cube("B", (-5, 2, 0.5), (0.5, 0.5, 0.5))
    b.modifiers.new("My Bevel", "BEVEL")
    b.display_type = "SOLID"
    c = _cube("C", (4, -3, 2), (1.5, 1.0, 0.5))
    c.hide_render = True
    return a, b, c


def _setup(active, more=()):
    """Turn Into Water on `active`, then Add Mesh to Water with `more`."""
    _select([active], active)
    bpy.ops.aquasuite.still_water_create()
    u = lib.last_uuid()
    if more:
        _select(list(more), more[0])
        bpy.ops.aquasuite.still_water_add_source(uuid=u)
    return u


def test_create_uses_active_only():
    _reset()
    a, b, c = _three()
    before = {o.name: _state(o) for o in (b, c)}
    user = _user_flow("UserFlow", (0, 0, 1))
    _select([a, b, c, user], a)
    result = bpy.ops.aquasuite.still_water_create()
    u = lib.last_uuid()
    e = lib.entry(u)
    lib.check("Turn Into Water converts only the active mesh",
              result == {"FINISHED"} and e.source == a and _is_water(a, u)
              and len(e.pool_sources) == 0
              and all(_state(o) == before[o.name] for o in (b, c)))
    lib.check("domain fitted to the active mesh as before",
              _same(_domain(u), sw._fitted_bounds([a])))
    lib.check("domain's Flow collection holds only its source",
              _flows(u) == ["A"] and _ds(u).fluid_group == e.flow_collection,
              str(_flows(u)))
    lib.check("Flow collection lives in the setup's collection",
              e.flow_collection.name in e.root_collection.children
              and e.flow_collection.get(C.OWNER_PROP, "").endswith(u))


def test_add_to_list():
    _reset()
    a, b, c = _three()
    before = {o.name: _state(o) for o in (a, b, c)}
    fluid = _user_flow("HasFluid", (0, 6, 1))
    bpy.ops.object.empty_add(location=(0, 0, 9))
    empty = bpy.context.active_object
    u = _setup(a)
    dom0 = _domain(u)
    _select([b, c, fluid, empty, a], b)
    result = bpy.ops.aquasuite.still_water_add_source(uuid=u)
    e = lib.entry(u)
    lib.check("Add Mesh to Water lists the selected meshes",
              result == {"FINISHED"} and e.source == a
              and [r.obj.name for r in e.pool_sources] == ["B", "C"],
              str([r.obj.name for r in e.pool_sources]))
    lib.check("listed meshes have a GEOMETRY flow, the tag, wire, no render",
              all(_is_water(o, u) for o in (a, b, c)))
    lib.check("restore records hold each mesh's own prior state",
              [(r.hide_render, r.display_type) for r in e.pool_sources]
              == [(False, "SOLID"), (True, "TEXTURED")])
    lib.check("a mesh with its own Fluid modifier is skipped (W021)",
              C.SRC_PROP not in fluid.keys()
              and [m.name for m in fluid.modifiers] == ["My Flow"])
    lib.check("a selected non-mesh is ignored", C.SRC_PROP not in empty.keys())
    lib.check("Flow collection = exactly the listed meshes",
              _flows(u) == ["A", "B", "C"], str(_flows(u)))
    dom = _domain(u)
    lib.check("the domain grows to hold every listed mesh",
              _contains(dom, dom0) and not _same(dom, dom0)
              and all(_contains(dom, sw.world_bbox(o)) for o in (a, b, c)))
    lib.check("an automatic domain grows to the fitted union",
              _same(dom, sw._fitted_bounds([a, b, c])))
    lib.check("an unbaked setup isn't flagged for a re-bake", not e.sources_changed)

    _select([c], c)
    result = bpy.ops.aquasuite.still_water_add_source(uuid=u)
    lib.check("adding a mesh that is already listed does nothing",
              result == {"CANCELLED"} and len(lib.entry(u).pool_sources) == 2)

    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("delete restores every listed mesh exactly",
              all(_state(o) == before[o.name] for o in (a, b, c)),
              str({o.name: _state(o) for o in (a, b, c)}))
    lib.check("delete leaves no source or owner tags",
              not lib.tagged_left()
              and not any(C.SRC_PROP in o.keys() for o in bpy.data.objects),
              str(lib.tagged_left()))


def test_open_and_owned_meshes():
    _reset()
    a = _cube("A", (0, 0, 1))
    bpy.ops.mesh.primitive_plane_add(location=(3, 0, 1))
    plane = bpy.context.active_object
    plane.name = "OpenPlane"
    u1 = _setup(a)
    dom1 = sw.find_domain_object(lib.entry(u1))
    b = _cube("B", (-3, 0, 1))
    u2 = _setup(b)
    _select([plane, a, dom1], plane)
    bpy.ops.aquasuite.still_water_add_source(uuid=u2)
    e2 = lib.entry(u2)
    lib.check("an open mesh can be added (W012 is only a warning)",
              _is_water(plane, u2) and plane in sw.water_sources(e2))
    lib.check("another setup's source and domain are skipped",
              a.get(C.SRC_PROP) == u1 and C.SRC_PROP not in dom1.keys()
              and sw.water_sources(e2) == [b, plane])
    lib.check("each domain's Flow collection is its own list",
              _flows(u1) == ["A"] and _flows(u2) == ["B", "OpenPlane"],
              f"{_flows(u1)} {_flows(u2)}")


def test_floaters_and_obstacles_not_water():
    """Water can't come from an object that floats in it or blocks it."""
    _reset()
    a = _cube("A", (0, 0, 1))
    u = _setup(a)
    crate = _cube("Crate", (0.3, 0, 1), (0.2, 0.2, 0.2))
    rock = _cube("Rock", (-0.3, 0, 1), (0.2, 0.2, 0.2))
    _select([crate], crate)
    bpy.ops.aquasuite.floating_add()
    _select([rock], rock)
    bpy.ops.aquasuite.obstacles_add()
    _select([crate, rock], crate)
    result = bpy.ops.aquasuite.still_water_add_source(uuid=u)
    lib.check("a Floating Object or Water Obstacle isn't added as water",
              result == {"CANCELLED"} and len(lib.entry(u).pool_sources) == 0
              and C.SRC_PROP not in crate.keys() and C.SRC_PROP not in rock.keys()
              and _flows(u) == ["A"], str(_flows(u)))


def test_grow_keeps_enlarged_domain():
    _reset()
    a, b, _c = _three()
    u = _setup(a)
    dom = sw.find_domain_object(lib.entry(u))
    dom.scale.z *= 3.0
    dom.scale.x *= 30.0
    tall = _domain(u)
    d = _cube("D", (2.0, 0.0, 1))
    _select([d], d)
    bpy.ops.aquasuite.still_water_add_source(uuid=u)
    lib.check("a mesh inside an enlarged domain leaves it unchanged",
              _same(_domain(u), tall) and _is_water(d, u))


def test_remove_one():
    _reset()
    a, b, c = _three()
    before = {o.name: _state(o) for o in (a, b, c)}
    u = _setup(a, (b, c))
    result = bpy.ops.aquasuite.water_source_remove(uuid=u, name="C")
    e = lib.entry(u)
    lib.check("remove gives the mesh back exactly",
              result == {"FINISHED"} and _state(c) == before["C"], str(_state(c)))
    lib.check("the others stay water and in the Flow collection",
              _is_water(a, u) and _is_water(b, u) and sw.water_sources(e) == [a, b]
              and _flows(u) == ["A", "B"])
    lib.check("an automatic domain is refit to the remaining meshes",
              _same(_domain(u), sw._fitted_bounds([a, b])))

    # The main source: the next mesh takes its place.
    bpy.ops.aquasuite.water_source_remove(uuid=u, name="A")
    e = lib.entry(u)
    lib.check("removing the main source restores it and promotes the next",
              _state(a) == before["A"] and e.source == b
              and len(e.pool_sources) == 0 and _flows(u) == ["B"]
              and (e.src_hide_render, e.src_display_type) == (False, "SOLID"))
    try:
        result = bpy.ops.aquasuite.water_source_remove(uuid=u, name="B")
    except RuntimeError:
        result = {"CANCELLED"}
    lib.check("the last water mesh can't be removed",
              result == {"CANCELLED"} and _is_water(b, u))
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("delete after removals restores the rest",
              all(_state(o) == before[o.name] for o in (a, b, c)))


def test_remove_keeps_resized_domain():
    _reset()
    a, b, c = _three()
    u = _setup(a, (b, c))
    dom = sw.find_domain_object(lib.entry(u))
    dom.location.z += 0.5
    moved = _domain(u)
    bpy.ops.aquasuite.water_source_remove(uuid=u, name="C")
    lib.check("a domain the user moved or resized is left as it is",
              _same(_domain(u), moved))


def test_object_only_in_flow_collection_survives():
    """A listed mesh the user unlinked from their own collections is kept
    in the scene when the setup's collections go."""
    _reset()
    a, b, _c = _three()
    u = _setup(a, (b,))
    for col in list(b.users_collection):
        if not col.get(C.OWNER_PROP):
            col.objects.unlink(b)
    bpy.ops.aquasuite.water_source_remove(uuid=u, name="B")
    lib.check("removed mesh stays in the scene",
              b.name in lib.scene().collection.objects and C.SRC_PROP not in b.keys())
    for col in list(a.users_collection):
        if not col.get(C.OWNER_PROP):
            col.objects.unlink(a)
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("deleted setup's main mesh stays in the scene",
              "A" in bpy.data.objects and a.name in lib.scene().collection.objects
              and C.SRC_PROP not in a.keys())


def test_flow_collections_all_modes():
    """Every liquid mode's domain takes only its own flows."""
    _reset()
    user = _user_flow("UserFlow", (0, 0, 1))
    still = _setup(_cube("S", (0, 0, 1)))
    bpy.ops.aquasuite.rain_sim_create()
    rain = lib.last_uuid()
    pool = _cube("Pool", (0, 0, 0.2), (2.0, 2.0, 0.2))
    pool_before = _state(pool)
    lib.make_active(pool)
    bpy.ops.aquasuite.rain_sim_add_pool(uuid=rain)
    bpy.ops.aquasuite.hose_create()
    hose = lib.last_uuid()
    bpy.ops.aquasuite.simulated_ocean_create()
    ocean = lib.last_uuid()
    for u in (still, rain, hose, ocean):
        e = lib.entry(u)
        want = sorted(o.name for o in sw.flow_objects(e))
        flows = _flows(u)
        lib.check(f"{e.mode}: Flow collection = its own flows only",
                  flows == want and bool(want) and "UserFlow" not in flows
                  and all(not o.get(C.SRC_PROP) or o.get(C.SRC_PROP) == u
                          for o in _ds(u).fluid_group.objects),
                  f"{flows} vs {want}")
    lib.check("Rain Sim pool is one of its flows", "Pool" in _flows(rain))
    lib.check("the user's own flow is in no setup's Flow collection",
              not any(c.get(C.OWNER_PROP) for c in user.users_collection))
    result = bpy.ops.aquasuite.water_source_remove(uuid=rain, name="Pool")
    lib.check("removing a Rain Sim pool restores it, pool and Flow links too",
              result == {"FINISHED"} and "Pool" not in _flows(rain)
              and _state(pool) == pool_before, str(_state(pool)))


def test_old_setup_mended():
    """A setup from an older file has no Flow collection: nothing changes
    until it is synced (before every bake), which then adds one."""
    _reset()
    a = _cube("A", (0, 0, 1))
    u = _setup(a)
    e = lib.entry(u)
    col = e.flow_collection
    _ds(u).fluid_group = None
    e.flow_collection = None
    bpy.data.collections.remove(col)
    _draw(lib.entry(u))
    lib.check("an old setup is left alone when drawn", _flows(u) == "-")
    sw.sync_flows(lib.entry(u))
    lib.check("sync gives an old setup its Flow collection",
              _flows(u) == ["A"])


def test_undo():
    _reset()
    a, b, c = _three()
    before = {o.name: _state(o) for o in (a, b, c)}
    _select([a], a)
    bpy.ops.ed.undo_push(message="before create")
    bpy.ops.aquasuite.still_water_create()
    u = lib.last_uuid()
    bpy.ops.ed.undo_push(message="created")
    _select([b, c], b)
    bpy.ops.aquasuite.still_water_add_source(uuid=u)
    bpy.ops.ed.undo_push(message="added")
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    bpy.ops.ed.undo_push(message="deleted")
    bpy.ops.ed.undo()
    objs = [bpy.data.objects[n] for n in "ABC"]
    lib.check("undoing Delete brings every water mesh back",
              lib.entry(u) is not None and all(_is_water(o, u) for o in objs)
              and len(lib.entry(u).pool_sources) == 2 and _flows(u) == ["A", "B", "C"])
    bpy.ops.ed.undo()
    objs = [bpy.data.objects[n] for n in "ABC"]
    lib.check("undoing Add Mesh to Water restores those meshes",
              _state(objs[1]) == before["B"] and _state(objs[2]) == before["C"]
              and _is_water(objs[0], u) and _flows(u) == ["A"])
    bpy.ops.ed.undo()
    objs = [bpy.data.objects[n] for n in "ABC"]
    lib.check("undoing Turn Into Water restores the mesh",
              len(lib.scene().aqs_assemblies) == 0
              and all(_state(o) == before[o.name] for o in objs),
              str([_state(o) for o in objs]))


def test_save_reload():
    _reset()
    a, b, c = _three()
    before = {o.name: _state(o) for o in (a, b, c)}
    u = _setup(a, (b, c))
    dom = _domain(u)
    path = lib.save_blend("still_sources")
    bpy.ops.wm.open_mainfile(filepath=path)
    e = lib.entry(u)
    objs = [bpy.data.objects[n] for n in "ABC"]
    lib.check("reloaded: source and listed meshes are still recorded",
              e is not None and e.source == objs[0]
              and [r.obj for r in e.pool_sources] == objs[1:]
              and all(_is_water(o, u) for o in objs))
    lib.check("reloaded: domain and Flow collection unchanged",
              _same(_domain(u), dom) and _flows(u) == ["A", "B", "C"]
              and _ds(u).fluid_group == e.flow_collection)
    bpy.ops.aquasuite.water_source_remove(uuid=u, name="B")
    lib.check("reloaded: remove still restores exactly",
              _state(bpy.data.objects["B"]) == before["B"])
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("reloaded: delete restores every mesh",
              all(_state(bpy.data.objects[n]) == before[n] for n in "ABC"))


def test_single_mesh_unchanged():
    """A setup from one mesh is what older versions made: no list records,
    the same domain."""
    _reset()
    a = _cube("A", (1, 2, 1), (1.0, 2.0, 0.5))
    before = _state(a)
    u = _setup(a)
    e = lib.entry(u)
    dom = sw.find_domain_object(e)
    mins, maxs = sw.world_bbox(a)
    size = maxs - mins
    center = (maxs + mins) * 0.5
    top = maxs.z + size.z * 0.2
    bottom = mins.z - size.z * 1.5
    old_loc = (center.x, center.y, (top + bottom) * 0.5)
    old_scale = (size.x * 1.5, size.y * 1.5, top - bottom)
    lib.check("single mesh: no list records, not flagged",
              len(e.pool_sources) == 0 and e.source == a and not e.sources_changed)
    lib.check("single mesh: domain placed exactly as before",
              all(abs(dom.location[i] - old_loc[i]) < 1e-6
                  and abs(dom.scale[i] - old_scale[i]) < 1e-6 for i in range(3)),
              f"{tuple(dom.location)} {tuple(dom.scale)}")
    lib.check("single mesh: the X is disabled for the only mesh",
              _x_buttons(e) == [False])
    bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("single mesh: delete restores it", _state(a) == before)


class _Layout:
    """Just enough of UILayout to run the panel's draw code headless."""

    def __init__(self, log):
        self.log, self.enabled, self.alert = log, True, False

    def _child(self, *_a, **_k):
        child = _Layout(self.log)
        child.parent = self
        return child

    row = column = box = _child

    def label(self, **kw):
        self.log.append(("label", kw.get("text", "")))

    def prop(self, *_a, **_k):
        pass

    def operator(self, idname, **kw):
        op = types.SimpleNamespace()
        node, enabled = self, True
        while node is not None:
            enabled = enabled and node.enabled
            node = getattr(node, "parent", None)
        self.log.append(("op", idname, enabled, kw.get("text")))
        return op


def _draw(e):
    from aquasuite.ui import panel
    log = []
    panel._draw_spec(_Layout(log), bpy.context, e)
    return log


def _x_buttons(e):
    return [item[2] for item in _draw(e)
            if item[0] == "op" and item[1] == "aquasuite.water_source_remove"]


def test_panel():
    _reset()
    a, b, c = _three()
    e = lib.entry(_setup(a, (b, c)))
    log = _draw(e)
    ops = [(item[1], item[3]) for item in log if item[0] == "op"]
    labels = [item[1] for item in log if item[0] == "label"]
    lib.check("panel: Add Mesh to Water button and one X per listed mesh",
              ("aquasuite.still_water_add_source", "Add Mesh to Water") in ops
              and _x_buttons(e) == [True, True, True]
              and {"A", "B", "C", "Water meshes: 3"} <= set(labels), str(labels))
    e.show_advanced = True
    lib.check("panel: Advanced draws too", bool(_draw(e)))


def _liquid_points(dom):
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    pts = [dom.matrix_world @ v.co for v in me.vertices] if len(me.vertices) > 8 else []
    ev.to_mesh_clear()
    return pts


def _near(pts, obj, r=0.6):
    c = obj.matrix_world.translation
    return sum(1 for p in pts if abs(p.x - c.x) < r and abs(p.y - c.y) < r)


def test_bake_own_flows_only():
    """Two Still Water setups whose domains overlap the same space, plus the
    user's own Fluid flow there: each bake holds only its listed meshes."""
    if not lib.BAKE:
        lib.skip("own-flows bake", "run with --bake")
        return
    _reset()
    lib.save_blend("still_sources_bake")
    lib.scene().frame_start, lib.scene().frame_end = 1, 4
    half = (0.25, 0.25, 0.25)
    left, right = _cube("Left", (-1.5, 0, 1), half), _cube("Right", (1.5, 0, 1), half)
    mid = _cube("Mid", (0, 0, 1), half)
    user = _user_flow("UserFlow", (0, 1.2, 1))
    u1 = _setup(left, (right,))
    u2 = _setup(mid)
    # An older setup: no Flow collection until Bake mends it.
    e2 = lib.entry(u2)
    old = e2.flow_collection
    _ds(u2).fluid_group = None
    e2.flow_collection = None
    bpy.data.collections.remove(old)
    box = (Vector((-2.2, -0.6, 0.3)), Vector((2.2, 1.8, 1.6)))
    results = {}
    for u in (u1, u2):
        e = lib.entry(u)
        e.base_resolution = 48
        dom = sw.find_domain_object(e)
        sw._set_domain_bounds(dom, *box)
        ds = _ds(u)
        ds.cache_frame_start, ds.cache_frame_end = 1, 4
        bpy.ops.aquasuite.bake_fluid(uuid=u)
        lib.scene().frame_set(3)
        pts = _liquid_points(dom)
        results[u] = {o.name: _near(pts, o) for o in (left, right, mid, user)}
    r1, r2 = results[u1], results[u2]
    detail = f"setup 1 {r1}, setup 2 {r2}"
    lib.check("one bake: both listed meshes produce liquid",
              r1["Left"] > 20 and r1["Right"] > 20, detail)
    lib.check("no liquid from another setup's mesh or the user's flow",
              r1["Mid"] == 0 and r1["UserFlow"] == 0, detail)
    lib.check("older setup mended at Bake: only its own mesh",
              r2["Mid"] > 20 and r2["Left"] == r2["Right"] == r2["UserFlow"] == 0
              and _flows(u2) == ["Mid"], detail)

    extra = _cube("Extra", (0, -0.4, 1), half)
    _select([extra], extra)
    bpy.ops.aquasuite.still_water_add_source(uuid=u1)
    lib.check("adding a mesh after a bake asks for a re-bake",
              lib.entry(u1).sources_changed
              and any("Bake Again" in item[1] for item in _draw(lib.entry(u1))
                      if item[0] == "label"))
    bpy.ops.aquasuite.bake_fluid(uuid=u1)
    lib.scene().frame_set(3)
    pts = _liquid_points(sw.find_domain_object(lib.entry(u1)))
    n = {o.name: _near(pts, o, 0.15) for o in (left, right, extra)}
    lib.check("Bake Again clears the note and bakes the added mesh too",
              not lib.entry(u1).sources_changed
              and n["Left"] > 20 and n["Right"] > 20 and n["Extra"] > 0, str(n))


lib.main(globals())
