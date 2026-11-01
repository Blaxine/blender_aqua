# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression checks for the v0.21.0 inspection's bugs."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import bakes, errors, floating, handlers, obstacles  # noqa: E402
from aquasuite.level1 import rain_reactive  # noqa: E402
from aquasuite.level3 import hose  # noqa: E402
from aquasuite.ui import panel  # noqa: E402

C = lib.C


class Stub:
    """Stands in for a Blender layout: records what a panel function draws."""

    def __init__(self, log=None):
        self.__dict__["log"] = [] if log is None else log

    def __setattr__(self, _name, _value):
        pass

    def __getattr__(self, _name):
        return Stub(self.log)

    def __call__(self, *_args, **_kwargs):
        return Stub(self.log)

    def operator(self, op_id, **kwargs):
        self.log.append((op_id, kwargs.get("text")))
        return Stub(self.log)


def _drawn(entry):
    layout = Stub()
    panel._draw_spec(layout, bpy.context, entry)
    return layout.log


def _refused(op, **kwargs):
    """An operator's error report is an exception when run from a script."""
    try:
        return op(**kwargs)
    except RuntimeError:
        return {"CANCELLED"}


def _delete(u):
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_delete_in_a_copied_scene_keeps_the_original():
    original = lib.scene()
    bpy.ops.aquasuite.ocean_create()
    u = lib.last_uuid()
    bpy.ops.aquasuite.rain_sim_create()
    rain = lib.last_uuid()
    surface = lib.entry(u).primary
    assert bpy.ops.scene.new(type="FULL_COPY") == {"FINISHED"}
    copy = next(s for s in bpy.data.scenes if s != original)
    lib.check("the copied scene has its own object", copy.aqs_assemblies[0].primary != surface)
    copied = copy.aqs_assemblies[0].primary.name

    from aquasuite.core import delete
    delete.delete_assembly(copy, u)
    delete.delete_assembly(copy, rain)
    entry = next(e for e in original.aqs_assemblies if e.uuid == u)
    lib.check("deleting in the copy leaves the original's object and setup",
              entry.primary == surface and surface.name in original.objects)
    lib.check("the copy's own object is gone", copied not in bpy.data.objects)
    from aquasuite.level1 import ocean
    lib.check("the original's ocean still has its surface modifier and material",
              ocean.find_ocean_modifier(surface, u) is not None and len(surface.data.materials) == 1
              and surface.data.materials[0] is not None)

    bpy.context.window.scene = original
    assert bpy.ops.scene.new(type="FULL_COPY") == {"FINISHED"}
    copy = next(s for s in bpy.data.scenes if s not in (original, ) and len(s.aqs_assemblies))
    keep = copy.aqs_assemblies[0].primary
    bpy.context.window.scene = original
    delete.delete_assembly(original, u)
    delete.delete_assembly(original, rain)
    lib.check("deleting in the original leaves the copy", keep.name in bpy.data.objects
              and keep.name in copy.objects)
    delete.delete_assembly(copy, u)
    delete.delete_assembly(copy, rain)
    lib.check("deleting the last copy leaves nothing tagged", lib.tagged_left() == [], str(lib.tagged_left()))
    bpy.context.window.scene = original
    bpy.data.scenes.remove(copy)


def test_simulated_hose_has_bake_in_simple_view():
    bpy.ops.aquasuite.hose_create()
    u = lib.last_uuid()
    e = lib.entry(u)
    lib.check("a real-time hose shows no Bake", "aquasuite.bake_fluid" not in [o for o, _t in _drawn(e)])
    e.hose_liquid = True
    ops = [o for o, _t in _drawn(lib.entry(u))]
    lib.check("Simple view shows Bake and Free once Simulate Liquid is on",
              "aquasuite.bake_fluid" in ops and "aquasuite.free_liquid" in ops, str(ops))
    lib.entry(u).show_advanced = True
    ops = [o for o, _t in _drawn(lib.entry(u))]
    lib.check("Advanced view still shows Bake once", ops.count("aquasuite.bake_fluid") == 1, str(ops))
    lib.entry(u).show_advanced = False
    lib.entry(u).regime = C.REGIME_MIST
    lib.check("Mist needs no bake", "aquasuite.bake_fluid" not in [o for o, _t in _drawn(lib.entry(u))])
    lib.entry(u).regime = C.REGIME_NORMAL
    labels = [t for o, t in _drawn(lib.entry(u)) if o == "aquasuite.hose_set_regime"]
    lib.check("regime buttons read Normal, Mist, Spray, Blast",
              labels == ["Normal", "Mist", "Spray", "Blast"], str(labels))
    _delete(u)


def test_lighting_delete_keeps_a_newer_world():
    scene = lib.scene()
    old = scene.world
    bpy.ops.aquasuite.water_lighting()
    u = lib.last_uuid()
    mine = bpy.data.worlds.new("User HDRI")
    scene.world = mine
    _delete(u)
    lib.check("the world chosen after adding lighting stays", scene.world == mine)
    scene.world = old
    bpy.data.worlds.remove(mine)
    bpy.ops.aquasuite.water_lighting()
    _delete(lib.last_uuid())
    lib.check("without a newer world, the old one comes back", scene.world == old)


def test_ripples_can_be_baked_again():
    scene = lib.scene()
    scene.frame_start, scene.frame_end = 1, 12
    bpy.ops.aquasuite.rain_reactive_create()
    u = lib.last_uuid()
    e = lib.entry(u)
    surf = next(m for m in e.primary.modifiers if m.type == "DYNAMIC_PAINT").canvas_settings.canvas_surfaces[0]
    surf.frame_start, surf.frame_end = 1, 12
    # Headless Dynamic Paint writes no frames to compare, so watch for the free
    # that makes Blender bake an already-baked cache again.
    freed = []
    real_free = rain_reactive._free_cache

    def counting_free(*args):
        freed.append(surf.point_cache.is_baked)
        real_free(*args)

    rain_reactive._free_cache = counting_free
    try:
        assert bpy.ops.aquasuite.bake_ripples(uuid=u) == {"FINISHED"}
        lib.check("the first bake has nothing to free", freed == [], str(freed))
        assert bpy.ops.aquasuite.bake_ripples(uuid=u) == {"FINISHED"}
        lib.check("Bake Again frees the old bake, then bakes",
                  freed == [True] and surf.point_cache.is_baked, str(freed))
    finally:
        rain_reactive._free_cache = real_free
    lib.check("the panel offers Free for ripples",
              "aquasuite.free_ripples" in [o for o, _t in _drawn(lib.entry(u))])
    r = bpy.ops.aquasuite.free_ripples(uuid=u)
    lib.check("Free Ripple Bake frees them", r == {"FINISHED"} and not bakes.has_bake(lib.entry(u)))
    _delete(u)
    scene.frame_start, scene.frame_end = 1, 250


def test_tank_gives_the_timeline_back():
    scene = lib.scene()
    scene.frame_end = 250
    bpy.ops.aquasuite.simulated_ocean_create()
    a = lib.last_uuid()
    lib.check("a tank extends the timeline", scene.frame_end == 720, str(scene.frame_end))
    bpy.ops.aquasuite.simulated_ocean_create()
    b = lib.last_uuid()
    _delete(a)
    lib.check("another tank still needs it", scene.frame_end == 720, str(scene.frame_end))
    _delete(b)
    lib.check("the last tank restores it", scene.frame_end == 250, str(scene.frame_end))
    bpy.ops.aquasuite.simulated_ocean_create()
    c = lib.last_uuid()
    scene.frame_end = 900
    _delete(c)
    lib.check("a timeline the user changed stays", scene.frame_end == 900, str(scene.frame_end))
    scene.frame_end = 250


def test_emitters_follow_the_timeline():
    scene = lib.scene()
    scene.frame_start, scene.frame_end = 1, 250
    bpy.ops.aquasuite.hose_create()
    hu = lib.last_uuid()
    bpy.ops.aquasuite.rain_create()
    ru = lib.last_uuid()
    bpy.ops.aquasuite.snow_create()
    su = lib.last_uuid()
    jet = hose._psys(hose._find_emitter(lib.entry(hu)), "jet")[0].settings
    rain = lib.entry(ru).primary.particle_systems[0].settings
    snow = lib.entry(su).primary.particle_systems[0].settings
    rain_count = rain.count
    snow.frame_end = 100   # the user's own range
    handlers.aqs_range_sync(scene)
    scene.frame_end = 500
    handlers.aqs_range_sync(scene)
    lib.check("hose and rain run for the whole new timeline",
              jet.frame_end == 500 and rain.frame_end == 500, f"{jet.frame_end} {rain.frame_end}")
    lib.check("at the same rate", abs(rain.count - rain_count * 2) <= 1, f"{rain_count} -> {rain.count}")
    lib.check("an emitter range the user set stays", snow.frame_end == 100, str(snow.frame_end))
    scene.frame_start, scene.frame_end = 300, 400
    handlers.aqs_range_sync(scene)
    lib.check("moving the range past the old end works",
              (rain.frame_start, rain.frame_end) == (300, 400), f"{rain.frame_start} {rain.frame_end}")
    scene.frame_start, scene.frame_end = 1, 250
    handlers.aqs_range_sync(scene)
    for u in (hu, ru, su):
        _delete(u)


def test_floaters_and_obstacles_cannot_become_water():
    cube = lib.add_cube(location=(0, 0, 1), name="Crate")
    floating.add(lib.scene(), [cube])
    lib.make_active(cube)
    r = _refused(bpy.ops.aquasuite.still_water_create)
    lib.check("a Floating Object can't be turned into water",
              r == {"CANCELLED"} and C.SRC_PROP not in cube.keys(), str(r))
    bpy.ops.aquasuite.rain_sim_create()
    u = lib.last_uuid()
    lib.make_active(cube)
    r = _refused(bpy.ops.aquasuite.rain_sim_add_pool, uuid=u)
    lib.check("nor into a rain pool", r == {"CANCELLED"} and C.SRC_PROP not in cube.keys(), str(r))
    _delete(u)
    floating.remove(lib.scene(), [cube])
    lib.make_active(cube)


def test_report_keeps_ordinary_words():
    lib.save_blend("water")
    err = errors.record("AquaSuite couldn't bake", RuntimeError("Water domain missing in " + bpy.data.filepath),
                        mode=C.MODE_STILL)
    text = errors.build_report(err)
    lib.check("a file called water.blend leaves 'Still Water' in the report", "Mode: Still Water" in text, text[:200])
    lib.check("the file's path and name are still removed",
              bpy.data.filepath not in text and "water.blend" not in text, text[:300])
    errors.reset_session()


def test_no_empty_obstacles_collection_left():
    scene = lib.scene()
    for obj in obstacles.members(scene):
        obstacles.remove(scene, [obj])
    col = obstacles.collection(scene)
    if col is not None:
        scene.aqs_obstacles = None
        bpy.data.collections.remove(col)
    bpy.ops.aquasuite.hose_create()
    a = lib.last_uuid()
    bpy.ops.aquasuite.hose_create()
    b = lib.last_uuid()
    _delete(a)
    lib.check("another hose still needs the collection", obstacles.collection(scene) is not None)
    _delete(b)
    lib.check("deleting the last hose removes the empty collection", obstacles.collection(scene) is None
              and "AQS Water Obstacles" not in bpy.data.collections)
    bpy.ops.aquasuite.hose_create()
    u = lib.last_uuid()
    rock = lib.add_cube(location=(9, 0, 0), name="Rock")
    obstacles.add(scene, [rock])
    _delete(u)
    lib.check("a collection with obstacles in it stays", rock.name in obstacles.collection(scene).objects)
    obstacles.remove(scene, [rock])


lib.main(globals())
