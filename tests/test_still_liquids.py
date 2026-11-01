# SPDX-License-Identifier: GPL-3.0-or-later
"""Still Water's real-liquid presets: the menu, the viscosity calculation, the
material looks; with --bake, volume is kept and viscosity changes the flow."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bmesh  # noqa: E402
import bpy  # noqa: E402
from aquasuite.core import liquids, presets  # noqa: E402
from aquasuite.level2 import still_water as sw  # noqa: E402

THIN_TO_THICK = ("WATER", "CREAM", "OIL", "THICK_CREAM", "SYRUP", "CHOCOLATE", "HONEY", "OATMEAL")
U = {}


def _create(key, size=2.0, location=(0, 0, 3)):
    cube = lib.add_cube(location=location, size=size)
    bpy.context.view_layer.update()
    lib.make_active(cube)
    assert bpy.ops.aquasuite.still_water_create(preset=liquids.preset_id(key)) == {"FINISHED"}
    bpy.context.view_layer.update()
    return lib.last_uuid(), cube


def _material(u):
    dom, _ds = presets.domain(lib.entry(u))
    return dom.material_slots[0].material


def _node_types(mat):
    return {n.type for n in mat.node_tree.nodes}


def _surface_type(mat):
    out = next(n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
    return out.inputs["Surface"].links[0].from_node.type


def _apply(u, preset):
    lib.entry(u).preset_choice = preset
    return bpy.ops.aquasuite.apply_preset(uuid=u)


def test_menu():
    keys = [item[0] for item in presets.ITEMS[lib.C.MODE_STILL]]
    wanted = ["WATER", "SYRUP", "OIL", "CHOCOLATE", "THICK_CREAM", "CREAM", "OATMEAL", "HONEY"]
    lib.check("the menu lists Water first, then the requested liquids",
              keys[:8] == [liquids.preset_id(k) for k in wanted], str(keys))
    lib.check("the earlier presets stay in the menu",
              keys[8:] == ["STILL_CALM", "STILL_SPLASHY", "STILL_THICK"], str(keys[8:]))
    lib.check("Water is the default", presets.DEFAULTS[lib.C.MODE_STILL] == "STILL_WATER")
    numbers = {i[0]: i[3] for items in presets.ITEMS.values() for i in items}
    old = ("STILL_CALM", "STILL_SPLASHY", "STILL_THICK", "RAIN_DRIZZLE", "RAIN_RAIN", "RAIN_STORM",
           "HOSE_GARDEN", "HOSE_FIRE", "HOSE_SPRINKLER", "OCEAN_CALM", "OCEAN_ROLLING", "OCEAN_STORM")
    lib.check("saved files keep their preset: the old enum numbers did not move",
              [numbers[k] for k in old] == list(range(1, 13)), str(numbers))


def test_calculation():
    lib.check("nu is viscosity / density (honey)", abs(liquids.kinematic("HONEY") - 10.0 / 1420.0) < 1e-9)
    nus = [liquids.kinematic(k) for k in THIN_TO_THICK]
    lib.check("kinematic viscosity rises from water to oatmeal", nus == sorted(nus), str(nus))
    flips = [liquids.flip_ratio(k) for k in THIN_TO_THICK]
    lib.check("FLIP falls as liquids thicken, from 0.97 for water",
              flips[0] == 0.97 and flips == sorted(flips, reverse=True) and flips[-1] >= 0.3, str(flips))
    lib.check("a mesh up to the reference size gets the real viscosity",
              liquids.simulated_nu("HONEY", 0.05) == liquids.kinematic("HONEY"))
    lib.check("a mesh 100x the reference size scales by 100^1.5",
              abs(liquids.simulated_nu("HONEY", 10.0) / liquids.kinematic("HONEY") - 1000.0) < 1e-6)
    lib.check("water leaves the viscosity solver off at any size",
              all(liquids.solver_viscosity("WATER", s, s * 2.7) == 0.0 for s in (0.1, 2.0, 50.0)))
    lib.check("the result never passes the property's limit",
              liquids.solver_viscosity("OATMEAL", 0.01, 0.001) == liquids.MAX_VISCOSITY)


def test_apply_every_liquid():
    bad = []
    for key in liquids.LIQUIDS:
        u, _cube = _create(key)
        e = lib.entry(u)
        dom, ds = presets.domain(e)
        want = liquids.solver_viscosity(key, 2.0, max(sw.object_dims(dom)))
        if ds.use_viscosity != (want > 0.0) or (want and abs(ds.viscosity_value - want) > want * 1e-3):
            bad.append(f"{key}: viscosity {ds.use_viscosity} {ds.viscosity_value} expected {want}")
        if abs(ds.flip_ratio - liquids.flip_ratio(key)) > 1e-3:
            bad.append(f"{key}: flip {ds.flip_ratio}")
        if presets.is_modified(e) or e.preset_label != liquids.LIQUIDS[key]["label"]:
            bad.append(f"{key}: modified or label {e.preset_label}")
        look = liquids.LIQUIDS[key]["look"]
        wanted = "BSDF_PRINCIPLED" if look and look["kind"] == "OPAQUE" else "BSDF_GLASS"
        if _surface_type(_material(u)) != wanted:
            bad.append(f"{key}: surface {_surface_type(_material(u))}")
        bpy.ops.aquasuite.assembly_delete(uuid=u)
        lib.check(f"{key}: delete leaves nothing tagged", lib.tagged_left() == [], str(lib.tagged_left()))
    lib.check("every liquid sets its viscosity, FLIP, label and material", not bad, "; ".join(bad))


def test_viscosity_follows_mesh_size():
    small, _a = _create("HONEY", size=0.5, location=(0, 0, 2))
    big, _b = _create("HONEY", size=4.0, location=(20, 0, 6))
    values = {}
    for name, u, size in (("small", small, 0.5), ("big", big, 4.0)):
        dom, ds = presets.domain(lib.entry(u))
        values[name] = ds.viscosity_value
        want = liquids.solver_viscosity("HONEY", size, max(sw.object_dims(dom)))
        lib.check(f"{name} mesh: the domain gets the calculated viscosity",
                  abs(ds.viscosity_value - want) < want * 1e-3, f"{ds.viscosity_value} vs {want}")
    lib.check("the solver value differs by mesh size", values["small"] != values["big"], str(values))
    for u in (small, big):
        bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_look_switching():
    u, _cube = _create("HONEY")
    mat = _material(u)
    lib.check("Honey is glass with coloured absorption",
              _surface_type(mat) == "BSDF_GLASS" and "VOLUME_ABSORPTION" in _node_types(mat))
    lib.check("Solid view shows the liquid's colour",
              abs(mat.diffuse_color[0] - liquids.LIQUIDS["HONEY"]["look"]["color"][0]) < 1e-3)
    _apply(u, "STILL_OATMEAL")
    lib.check("Oatmeal is opaque with lumps",
              _surface_type(mat) == "BSDF_PRINCIPLED" and "TEX_NOISE" in _node_types(mat)
              and "VOLUME_ABSORPTION" not in _node_types(mat))
    lib.check("the liquid render mask survives a change of look", "OUTPUT_AOV" in _node_types(mat))
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.123
    _apply(u, "STILL_OATMEAL")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    lib.check("re-applying the same liquid keeps edits to its material",
              abs(bsdf.inputs["Roughness"].default_value - 0.123) < 1e-3)
    _apply(u, "STILL_CALM")
    _dom, ds = presets.domain(lib.entry(u))
    lib.check("an earlier preset goes back to the water look and no viscosity",
              _surface_type(mat) == "BSDF_GLASS" and "TEX_NOISE" not in _node_types(mat)
              and not ds.use_viscosity)
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_earlier_presets_keep_a_fresh_material():
    u, _cube = _create("WATER")
    mat = _material(u)
    glass = next(n for n in mat.node_tree.nodes if n.type == "BSDF_GLASS")
    glass.inputs["Roughness"].default_value = 0.2
    _apply(u, "STILL_SPLASHY")
    glass = next(n for n in mat.node_tree.nodes if n.type == "BSDF_GLASS")
    lib.check("presets that are all water leave the water material's edits alone",
              abs(glass.inputs["Roughness"].default_value - 0.2) < 1e-3)
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_refresh_before_bake():
    u, cube = _create("HONEY")
    e = lib.entry(u)
    _dom, ds = presets.domain(e)
    before = ds.viscosity_value
    cube.scale = (3.0, 3.0, 3.0)
    bpy.context.view_layer.update()
    presets.refresh_liquid(e)
    lib.check("a mesh that grew gets a new viscosity before the bake",
              ds.viscosity_value != before, f"{before} -> {ds.viscosity_value}")
    bpy.context.view_layer.update()
    lib.check("following the mesh doesn't mark the preset modified",
              not presets.is_modified(lib.entry(u)))
    ds.viscosity_value = 1.5
    bpy.context.view_layer.update()
    lib.check("a viscosity set by hand marks the preset modified", presets.is_modified(lib.entry(u)))
    cube.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    presets.refresh_liquid(lib.entry(u))
    lib.check("and the refresh keeps it", abs(ds.viscosity_value - 1.5) < 1e-5, str(ds.viscosity_value))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_save_and_reload():
    u, _cube = _create("THICK_CREAM")
    _apply(u, "STILL_CHOCOLATE")
    lib.save_blend("still_liquids")
    bpy.ops.wm.open_mainfile(filepath=bpy.data.filepath)
    e = lib.entry(u)
    lib.check("the preset survives save and reload",
              e.preset_id == "STILL_CHOCOLATE" and e.preset_choice == "STILL_CHOCOLATE"
              and not presets.is_modified(e), f"{e.preset_id} {e.preset_choice}")
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def _volume(dom):
    bpy.context.view_layer.update()
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    bm = bmesh.new()
    bm.from_mesh(ev.to_mesh())
    bm.transform(dom.matrix_world)
    volume = abs(bm.calc_volume(signed=True))
    bm.free()
    ev.to_mesh_clear()
    return volume


def test_liquids_keep_their_volume():
    if not lib.BAKE:
        lib.skip("liquid volume bakes", "run with --bake")
        return
    lib.save_blend("still_liquids_volume")
    scene = lib.scene()
    scene.frame_start, scene.frame_end = 1, 120
    for key in ("WATER", "OIL", "HONEY"):
        u, cube = _create(key)
        e = lib.entry(u)
        e.base_resolution = 48
        dom, ds = presets.domain(e)
        ds.cache_frame_start, ds.cache_frame_end = 1, 120
        with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                       selected_editable_objects=[dom]):
            bpy.ops.fluid.bake_all()
        scene.frame_set(120)
        volume = _volume(dom)
        lib.check(f"{key}: an 8 m³ cube stays near 8 m³ after 120 frames", 6.0 < volume < 11.0,
                  f"{volume:.1f} m³")
        scene.frame_set(1)
        bpy.ops.aquasuite.assembly_delete(uuid=u, delete_cache=True)
        bpy.data.objects.remove(cube, do_unlink=True)


def _top_of_liquid(dom):
    bpy.context.view_layer.update()
    ev = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    mw = dom.matrix_world
    zs = sorted((mw @ v.co).z for v in me.vertices)
    ev.to_mesh_clear()
    return zs[int(len(zs) * 0.95)] - sw.domain_bounds(dom)[0].z if zs else 0.0


def test_viscosity_changes_the_flow():
    if not lib.BAKE:
        lib.skip("liquid viscosity bakes", "run with --bake")
        return
    lib.save_blend("still_liquids_bake")
    scene = lib.scene()
    scene.frame_start, scene.frame_end = 1, 60
    heights = {}
    for key in ("WATER", "THICK_CREAM", "OATMEAL"):
        u, cube = _create(key)
        e = lib.entry(u)
        e.base_resolution = 48
        dom, ds = presets.domain(e)
        ds.cache_frame_start, ds.cache_frame_end = 1, 60
        with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom],
                                       selected_editable_objects=[dom]):
            bpy.ops.fluid.bake_all()
        scene.frame_set(60)
        heights[key] = _top_of_liquid(dom)
        scene.frame_set(1)
        bpy.ops.aquasuite.assembly_delete(uuid=u, delete_cache=True)
        bpy.data.objects.remove(cube, do_unlink=True)
    # At frame 60 water is still climbing the walls; thick liquids have landed.
    lib.check("water still splashes up the walls while thick liquids stay low, oatmeal piled highest",
              heights["WATER"] > 2 * heights["OATMEAL"] and heights["OATMEAL"] > heights["THICK_CREAM"],
              str({k: round(v, 3) for k, v in heights.items()}))


lib.main(globals())
