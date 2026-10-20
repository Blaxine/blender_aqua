# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression checks for repository verification findings."""
import os
import sys
import statistics

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib
import bpy
import bmesh
from aquasuite.core import quality, errors
from aquasuite.level1 import ocean
from aquasuite.level2 import rain_sim


def cleanup():
    for u in [e.uuid for e in lib.scene().aqs_assemblies]:
        bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_unsaved_bake_report():
    lib.make_active(lib.add_cube())
    bpy.ops.aquasuite.still_water_create()
    u = lib.last_uuid()
    errors.reset_session()
    try:
        bpy.ops.aquasuite.bake_fluid(uuid=u)
    except RuntimeError:
        pass  # Blender promotes ERROR reports to RuntimeError for scripts.
    err = errors.last_error()
    lib.check("unsaved bake records a report and queues its popup",
              len(errors.pending()) == 1 and err is not None
              and err['uuid'] == u and err['mode'] == 'STILL'
              and 'Save the .blend first' in errors.build_report(err))
    cleanup()


def test_buoy_constraint_identity():
    for action in ('detach', 'delete', 'orphan'):
        bpy.ops.aquasuite.ocean_create()
        u = lib.last_uuid()
        boat = lib.add_cube(name='RegressionBoat')
        bpy.ops.aquasuite.ocean_attach_buoy(uuid=u)
        boat.constraints[0].name = 'Renamed location'
        boat.constraints[1].name = 'Renamed tilt'
        user = boat.constraints.new('LIMIT_LOCATION')
        user.name = 'AQS Buoy Z'
        name = boat.name
        if action == 'delete':
            # Driver pointers must survive serialization, not only a session.
            path = lib.save_blend('constraint_identity')
            bpy.ops.wm.open_mainfile(filepath=path)
            boat = bpy.data.objects[name]
        if action == 'detach':
            bpy.ops.aquasuite.ocean_detach_buoy(uuid=u, buoy_index=0)
        elif action == 'delete':
            bpy.ops.aquasuite.assembly_delete(uuid=u)
        else:
            bpy.data.objects.remove(lib.entry(u).primary, do_unlink=True)
            lib.scene().frame_set(lib.scene().frame_current + 1)
        lib.check(f'{action}: renamed buoy constraints removed, user constraint preserved',
                  [(c.name, c.type) for c in boat.constraints]
                  == [('AQS Buoy Z', 'LIMIT_LOCATION')])
        cleanup()


def test_scene_isolation():
    a = lib.scene()
    a.aqs_quality = 'FINAL'
    # A user collection with the conventional name must not become ours.
    user_root = bpy.data.collections.new('AQS_Assemblies')
    a.collection.children.link(user_root)
    bpy.ops.aquasuite.rain_create()
    ua = lib.last_uuid()
    ra = lib.entry(ua).primary
    pa = ra.particle_systems[0].settings
    pa.display_percentage = 73
    b = bpy.data.scenes.new('Independent scene')
    try:
        bpy.context.window.scene = b
        bpy.ops.aquasuite.rain_create()
        ub = lib.last_uuid()
        rb = lib.entry(ub).primary
        pb = rb.particle_systems[0].settings
        lib.check('assemblies belong only to their independently created scenes',
                  rb.name not in a.objects and ra.name not in b.objects)
        bpy.context.window.scene = a
        b.aqs_quality = 'PREVIEW'  # callback owner differs from context.scene
        lib.check('inactive scene quality changes only its own particles',
                  pa.display_percentage == 73 and pb.display_percentage == 25
                  and a.aqs_quality == 'FINAL')
        b.aqs_quality = 'FINAL'
        lib.check('quality restores authored particle percentages',
                  pa.display_percentage == 73 and pb.display_percentage == 100)
        bpy.context.window.scene = b
        cleanup()
        lib.check('deleting scene B assemblies preserves scene A',
                  ra.name in a.objects and len(a.aqs_assemblies) == 1)
    finally:
        bpy.context.window.scene = a
        bpy.data.scenes.remove(b)
        cleanup()
    lib.check('user collection with conventional root name survives teardown',
              user_root.name in a.collection.children)
    bpy.data.collections.remove(user_root)


def test_preview_creation_and_reapplication():
    scene = lib.scene()
    scene.aqs_quality = 'PREVIEW'
    bpy.ops.aquasuite.ocean_create()
    u = lib.last_uuid()
    mod = ocean.find_ocean_modifier(lib.entry(u).primary, u)
    lib.check('ocean created in Preview uses half resolution',
              ocean.get_input(mod, 'Resolution') == 64)
    for op in ('rain_create', 'rain_reactive_create', 'snow_create', 'hose_create'):
        getattr(bpy.ops.aquasuite, op)()
    particles = list(quality._tagged_particles(scene))
    lib.check('all particle modes created in Preview use 25 percent',
              len(particles) >= 5 and all(p.display_percentage == 25 for p in particles))
    quality.apply_tier(scene)
    quality.apply_tier(scene)
    lib.check('repeated Preview application preserves ocean resolution',
              ocean.get_input(mod, 'Resolution') == 64)
    scene.aqs_quality = 'FINAL'
    lib.check('Final restores newly created effects to authored quality',
              ocean.get_input(mod, 'Resolution') == 128
              and all(p.display_percentage == 100 for p in particles))
    cleanup()


def drop_centers(obj, frame):
    lib.scene().frame_set(frame)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    instances = sorted((tuple(i.persistent_id), i.matrix_world.translation.x)
                       for i in depsgraph.object_instances if i.is_instance
                       and i.parent and i.parent.original == obj)
    if instances:
        return [x for _id, x in instances]
    bm = bmesh.new()
    bm.from_mesh(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data)
    bm.verts.ensure_lookup_table()
    seen, centers = set(), []
    for vertex in bm.verts:
        if vertex.index in seen:
            continue
        stack, island = [vertex], []
        seen.add(vertex.index)
        while stack:
            v = stack.pop()
            island.append(obj.matrix_world @ v.co)
            for edge in v.link_edges:
                other = edge.other_vert(v)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        if len(island) == 12:
            centers.append(sum(p.x for p in island) / 12)
    bm.free()
    return centers


def test_rain_area_preserves_velocity():
    bpy.ops.aquasuite.rain_sim_create(angle=45)
    u = lib.last_uuid()
    e = lib.entry(u)
    emitter = rain_sim.find_emitter(e)
    # Include an assembly saved with the former scale-based area control.
    emitter.scale.x = emitter.scale.y = 2
    for area in (8.0, 3.0):
        e.rain_area = area
        drops = rain_sim.find_rain_drops(e)
        xs1, xs2 = drop_centers(drops, 12), drop_centers(drops, 13)
        fps = lib.scene().render.fps / lib.scene().render.fps_base
        vx = [(b-a)*fps for a, b in zip(xs1, xs2) if b > a]
        measured = statistics.median(vx) if vx else 0
        expected = rain_sim.rain_velocity(e).x
        mn, mx = rain_sim.emitter_footprint(emitter)
        lib.check(f'Rain Area {area}: correct world size and velocity',
                  abs(mx.x-mn.x-area) < 1e-4 and abs(measured-expected) < 1e-3,
                  f'area {mx.x-mn.x}, velocity {measured}, expected {expected}')
    cleanup()


lib.main(globals())
