# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import json
sys.path.insert(0, os.path.dirname(__file__))
import aqs_testlib as lib
import bpy
from aquasuite.core import lighting, delete


def test_roundtrip_and_hint():
    scene = lib.scene()
    for obj in list(scene.objects):
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
    previous = scene.world
    lib.check('default grey world suggests lighting without lights', lighting.suggested(scene))
    before = {path: getattr(obj, name) for path in ('eevee.use_raytracing', 'eevee.use_ssr', 'eevee.use_ssr_refraction',
              'cycles.max_bounces', 'cycles.transmission_bounces', 'cycles.transparent_max_bounces')
              for obj, name in [lighting._setting(scene, path)] if obj is not None}
    result = bpy.ops.aquasuite.water_lighting()
    entry = lighting.existing(scene)
    assert entry is not None
    uid = entry.uuid
    lib.check('lighting owns a sky and sun', result == {'FINISHED'} and scene.world == entry.light_world
              and lighting.sky_node(entry) is not None and entry.primary.data.type == 'SUN')
    lib.check('second lighting disabled and hint hidden', not bpy.ops.aquasuite.water_lighting.poll() and not lighting.suggested(scene))
    entry.sun_strength = 3.5
    entry.sun_angle = .4
    lib.check('sun controls update owned light', abs(entry.primary.data.energy - 3.5) < 1e-5)
    for path, old in json.loads(entry.light_restore).items():
        assert before[path] == old
    delete.delete_assembly(scene, uid)
    after = {path: getattr(*lighting._setting(scene, path)) for path in before}
    lib.check('delete restores exact world and settings', scene.world == previous and before == after)
    lib.check('lighting worlds and lights swept', not any(x.get(lib.C.OWNER_PROP) for group in
              (bpy.data.worlds, bpy.data.lights) for x in group))
    scene.world = None
    lib.check('no world suggests lighting', lighting.suggested(scene))
    bpy.ops.aquasuite.water_lighting()
    delete.delete_assembly(scene, lighting.existing(scene).uuid)
    lib.check('None world restores', scene.world is None)
    scene.world = previous


def test_cycles_restore_when_enabled():
    import addon_utils
    addon_utils.enable('cycles', default_set=False, persistent=False)
    scene = lib.scene()
    if not hasattr(scene, 'cycles'):
        lib.skip('Cycles lighting restore', 'Cycles not available in this Blender')
        return
    scene.cycles.max_bounces = 4
    scene.cycles.transmission_bounces = 2
    scene.cycles.transparent_max_bounces = 3
    engine = scene.render.engine
    bpy.ops.aquasuite.water_lighting()
    entry = lighting.existing(scene)
    lib.check('Cycles lighting settings raised without switching engine',
              scene.cycles.max_bounces == 12 and scene.cycles.transmission_bounces == 8
              and scene.render.engine == engine)
    delete.delete_assembly(scene, entry.uuid)
    lib.check('Cycles settings restored exactly', (scene.cycles.max_bounces,
              scene.cycles.transmission_bounces, scene.cycles.transparent_max_bounces) == (4, 2, 3))


def test_lighting_failed_create_restores():
    scene = lib.scene()
    previous = scene.world
    original = lighting.update
    def fail(_entry):
        raise RuntimeError('forced lighting failure')
    lighting.update = fail
    try:
        try:
            result = bpy.ops.aquasuite.water_lighting()
        except RuntimeError as exc:
            assert 'Forced lighting failure' in str(exc)
            result = {'CANCELLED'}  # bpy.ops raises when an operator reports ERROR.
    finally:
        lighting.update = original
    lib.check('lighting creation failure rolls back', result == {'CANCELLED'} and scene.world == previous
              and lighting.existing(scene) is None)


lib.main(globals())
