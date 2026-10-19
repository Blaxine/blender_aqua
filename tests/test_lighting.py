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


def _shared_world_roundtrip(reload):
    scene = lib.scene()
    world_name = lambda s: s.world.name if s.world else None  # survives reload
    previous = world_name(scene)
    bpy.ops.aquasuite.water_lighting()
    uid = lighting.existing(scene).uuid
    sky_world = scene.world
    other = bpy.data.scenes.new('AQS Shared World B')
    other.world = sky_world
    if reload:
        path = lib.save_blend('shared_world')
        bpy.ops.wm.open_mainfile(filepath=path)
        scene = lib.scene()
        other = bpy.data.scenes['AQS Shared World B']
        sky_world = other.world
    delete.delete_assembly(scene, uid)
    kept = other.world
    sky = next((n for n in kept.node_tree.nodes if n.type == 'TEX_SKY'), None) if kept and kept.use_nodes else None
    tag = '(reloaded)' if reload else ''
    lib.check(f'deleting lighting restores its own scene {tag}',
              world_name(scene) == previous and lighting.existing(scene) is None)
    lib.check(f'another scene keeps the shared sky world and node tree {tag}',
              kept is not None and kept == sky_world and sky is not None
              and any(l.to_node.type == 'OUTPUT_WORLD' for l in kept.node_tree.links))
    lib.check(f'kept world is no longer owned by AquaSuite {tag}',
              kept is not None and lib.C.OWNER_PROP not in kept.keys())
    bpy.data.scenes.remove(other)
    if kept is not None and kept.users == 0:
        bpy.data.worlds.remove(kept)


def test_shared_world_survives_delete():
    _shared_world_roundtrip(reload=False)


def test_shared_world_survives_delete_after_reload():
    _shared_world_roundtrip(reload=True)


def test_fake_user_world_survives_delete():
    scene = lib.scene()
    bpy.ops.aquasuite.water_lighting()
    entry = lighting.existing(scene)
    world = entry.light_world
    world.use_fake_user = True
    name = world.name
    delete.delete_assembly(scene, entry.uuid)
    kept = bpy.data.worlds.get(name)
    lib.check('a fake-user sky world is kept and released',
              kept is not None and lib.C.OWNER_PROP not in kept.keys())
    if kept is not None:
        kept.use_fake_user = False
        bpy.data.worlds.remove(kept)


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
