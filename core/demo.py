# SPDX-License-Identifier: GPL-3.0-or-later
"""Build an isolated, disposable real-time showcase using public operators."""
import math
import bpy
import bmesh
from mathutils import Matrix, Vector
from . import lighting, obstacles, delete
from ..level1 import ocean


def _box(scene, name, location, scale, color):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.location, obj.scale = location, scale
    mat = bpy.data.materials.new(name + ' Material')
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (*color, 1)
    mesh.materials.append(mat)
    return obj


def _require(result):
    if result != {'FINISHED'}:
        raise RuntimeError('A demo effect could not be created. The incomplete demo was removed.')


def build(context):
    # Snapshot IDs only for failure rollback. Never alter a pre-existing scene.
    groups = ('objects', 'collections', 'meshes', 'materials', 'worlds', 'lights',
              'cameras', 'particles', 'node_groups', 'actions')
    before = {name: set(getattr(bpy.data, name)) for name in groups}
    scene = bpy.data.scenes.new('AquaSuite Demo')
    scene['aqs_demo'] = True
    scene.frame_start, scene.frame_end = 1, 180
    scene.render.fps = 24
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    try:
        with context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            _require(bpy.ops.aquasuite.ocean_create())
            water = scene.aqs_assemblies[-1]
            water.primary.location = (-5, 0, 0)
            modifier = ocean.find_ocean_modifier(water.primary, water.uuid)
            ocean.set_input(modifier, 'Size', 9.0)
            ocean.set_input(modifier, 'Resolution', 64)
            ocean.set_input(modifier, 'Amplitude', .35)
            floater = _box(scene, 'Demo Floater', (-5, 0, .3), (1.1, 1.1, .6), (.8, .22, .05))
            context.view_layer.objects.active = floater
            context.view_layer.update()
            with context.temp_override(active_object=floater, object=floater,
                                       selected_objects=[floater], selected_editable_objects=[floater]):
                _require(bpy.ops.aquasuite.ocean_attach_buoy(uuid=water.uuid))
            _require(bpy.ops.aquasuite.rain_create())
            rain = scene.aqs_assemblies[-1].primary
            rain.location = (-5, 0, 4)
            rain.scale = (.7, .7, 1)
            rain.particle_systems[0].settings.count = 3000
            scene.cursor.location = (1.5, 0, 2)
            _require(bpy.ops.aquasuite.hose_create())
            hose = scene.aqs_assemblies[-1]
            # Cone (+Y) tipped down, then swung 75 degrees toward +X: the jet
            # leaves slightly downward at the wall.
            hose.primary.rotation_euler = (Matrix.Rotation(math.radians(-75), 3, 'Y')
                                           @ Matrix.Rotation(-math.pi / 2, 3, 'X')).to_euler()
            hose.pressure = .7
            wall = _box(scene, 'Demo Obstacle Wall', (5, 0, 1.2), (.35, 4, 2.4), (.22, .28, .32))
            ground = _box(scene, 'Demo Ground', (2, 0, -.2), (8, 7, .25), (.12, .15, .18))
            obstacles.add(scene, [wall, ground])
            lighting.create(scene)
            camera_data = bpy.data.cameras.new('Demo Camera')
            camera = bpy.data.objects.new('Demo Camera', camera_data)
            scene.collection.objects.link(camera)
            camera.location = (16, -24, 17)
            camera.rotation_euler = (Vector((-1.5, 0, .5)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
            camera_data.lens = 45
            scene.camera = camera
            scene.cursor.location = (0, 0, 0)
            scene.frame_set(1)
        return scene
    except Exception:
        for uid in [e.uuid for e in scene.aqs_assemblies]:
            delete.delete_assembly(scene, uid)
        bpy.data.scenes.remove(scene)
        # References between new node trees/materials/particle settings may
        # release users only after another group has been swept.
        removed = True
        while removed:
            removed = False
            for name in groups:
                collection = getattr(bpy.data, name)
                for item in list(collection):
                    if item not in before[name] and (name in ('objects', 'collections') or item.users == 0):
                        collection.remove(item)
                        removed = True
        raise


class AQS_OT_load_demo(bpy.types.Operator):
    bl_idname = 'aquasuite.load_demo'
    bl_label = 'Load Demo'
    bl_description = 'Create a separate real-time showcase scene; your current scene is preserved'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = build(context)
        if context.window is not None and not bpy.app.background:
            context.window.scene = scene
        self.report({'INFO'}, 'AquaSuite Demo ready — press Play; select the demo scene if it did not open automatically')
        return {'FINISHED'}


CLASSES = (AQS_OT_load_demo,)
