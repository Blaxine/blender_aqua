# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import aqs_testlib as lib
import bpy
from aquasuite.core import demo, lighting, obstacles
from aquasuite.level3 import hose


def test_demo_isolation_and_playback():
    original = lib.scene()
    original_constraints = {o: tuple(o.constraints) for o in original.objects}
    before = (set(original.objects), original.world, original.camera, original.frame_current,
              original.render.engine, tuple(original.cursor.location))
    scene = demo.build(bpy.context)
    after = (set(original.objects), original.world, original.camera, original.frame_current,
             original.render.engine, tuple(original.cursor.location))
    lib.check('demo leaves original scene untouched', before == after and bpy.context.scene == original
              and original_constraints == {o: tuple(o.constraints) for o in original.objects})
    modes = {e.mode for e in scene.aqs_assemblies}
    lib.check('demo contains ocean rain hose lighting camera',
              modes == {'OCEAN', 'RAIN', 'HOSE', 'LIGHTING'} and scene.camera is not None)
    lib.check('wall and floor are Water Obstacles', len(obstacles.members(scene)) == 2)
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        ocean_entry = next(e for e in scene.aqs_assemblies if e.mode == 'OCEAN')
        lib.check('demo attaches its own floater', ocean_entry.buoys[0].obj.name.startswith('Demo Floater')
                  and ocean_entry.buoys[0].obj not in original.objects[:])
        hose_entry = next(e for e in scene.aqs_assemblies if e.mode == 'HOSE')
        rain = next(e.primary for e in scene.aqs_assemblies if e.mode == 'RAIN')
        heights = []
        for frame in range(1, 41):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            heights.append(ocean_entry.buoys[0].empty.location.z)
        dg = bpy.context.evaluated_depsgraph_get()
        em = hose._find_emitter(hose_entry).evaluated_get(dg)
        jet, _mod = hose._psys(em, 'jet')
        rain_ps = rain.evaluated_get(dg).particle_systems[0]
        lib.check('demo floater moves without bake', max(heights) - min(heights) > .01)
        lib.check('demo rain and hose particles alive', any(p.alive_state == 'ALIVE' for p in rain_ps.particles)
                  and any(p.alive_state == 'ALIVE' for p in jet.particles))


def test_demo_failure_rolls_back():
    before_scenes, before_objects = set(bpy.data.scenes), set(bpy.data.objects)
    original = lighting.create
    def fail(_scene):
        raise RuntimeError('forced demo failure')
    lighting.create = fail
    try:
        try:
            demo.build(bpy.context)
        except RuntimeError:
            pass
    finally:
        lighting.create = original
    lib.check('failed demo removes its scene and objects', set(bpy.data.scenes) == before_scenes
              and set(bpy.data.objects) == before_objects)


lib.main(globals())
