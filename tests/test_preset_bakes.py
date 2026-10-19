# SPDX-License-Identifier: GPL-3.0-or-later
"""REQ-003: presence-of-liquid smoke bake per preset, not visual acceptance."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import aqs_testlib as lib
import bpy
from aquasuite.core import presets, delete


def test_every_preset_produces_liquid():
    if not lib.BAKE:
        lib.skip('twelve preset bakes', 'run with --bake')
        return
    lib.save_blend('preset_smoke')
    scene = lib.scene()
    scene.frame_start, scene.frame_end = 1, 16
    for key, package in presets.CATALOG.items():
        scene.frame_set(1)
        sources = []
        mode = package['mode']
        if mode == 'STILL':
            source = lib.add_cube(location=(0, 0, 1))
            sources.append(source)
            lib.make_active(source)
            result = bpy.ops.aquasuite.still_water_create(preset=key)
        elif mode == 'SIMRAIN':
            result = bpy.ops.aquasuite.rain_sim_create(preset=key, area=4)
            pool = lib.add_cube(location=(0, 0, .2))
            pool.scale = (1.8, 1.8, .2)
            sources.append(pool)
            lib.make_active(pool)
            assert bpy.ops.aquasuite.rain_sim_add_pool(uuid=lib.last_uuid()) == {'FINISHED'}
        elif mode == 'HOSE':
            result = bpy.ops.aquasuite.hose_create(preset=key, simulate_liquid=True)
        else:
            result = bpy.ops.aquasuite.simulated_ocean_create(preset=key)
        assert result == {'FINISHED'}
        entry = lib.entry(lib.last_uuid())
        uid = entry.uuid
        try:
            # Only resolution is capped. Draft, viscosity, whitewater and all
            # look settings remain the preset's authored values.
            entry.base_resolution = 48
            dom, ds = presets.domain(entry)
            ds.cache_frame_start, ds.cache_frame_end = 1, 16
            with bpy.context.temp_override(active_object=dom, object=dom,
                                           selected_objects=[dom], selected_editable_objects=[dom]):
                assert bpy.ops.fluid.bake_all() == {'FINISHED'}
            counts = []
            for frame in (8, 16):
                scene.frame_set(frame)
                obj = dom.evaluated_get(bpy.context.evaluated_depsgraph_get())
                mesh = obj.to_mesh()
                try:
                    counts.append(len(mesh.vertices))
                finally:
                    obj.to_mesh_clear()
            lib.check(key + ': low-res bake contains liquid', ds.has_cache_baked_any and min(counts) > 8,
                      f'liquid mesh vertices at frames 8/16: {counts}; effective resolution {ds.resolution_max}')
        finally:
            delete.delete_assembly(scene, uid, delete_cache=True)
            for source in sources:
                bpy.data.objects.remove(source, do_unlink=True)


lib.main(globals())
