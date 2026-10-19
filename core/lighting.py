# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in, reversible scene lighting. No access to scenes at registration."""
import json
import math
import bpy
from . import naming, registry, delete, presets
from .. import constants as C


def existing(scene):
    return next((e for e in scene.aqs_assemblies if e.mode == C.MODE_LIGHTING), None)


def suggested(scene):
    if existing(scene) or any(o.type == 'LIGHT' and not o.hide_render for o in scene.objects):
        return False
    world = scene.world
    if world is None:
        return True
    if not world.use_nodes:
        color = world.color
        return max(color) - min(color) < 1e-5 and max(color) <= .1
    output = next((n for n in world.node_tree.nodes if n.type == 'OUTPUT_WORLD' and n.is_active_output), None)
    if output is None or not output.inputs['Surface'].links:
        return False
    background = output.inputs['Surface'].links[0].from_node
    if background.type != 'BACKGROUND' or any(s.is_linked for s in background.inputs):
        return False
    color = background.inputs['Color'].default_value[:3]
    return max(color) - min(color) < 1e-5 and max(color) <= .1 and background.inputs['Strength'].default_value <= 1


def sky_node(entry):
    world = entry.light_world
    return next((n for n in world.node_tree.nodes if n.get('aqs_sky')), None) if world and world.use_nodes else None


def update(entry, _context=None):
    sun = entry.primary
    if sun and sun.type == 'LIGHT':
        sun.data.energy = entry.sun_strength
        sun.rotation_euler = (math.pi / 2 - entry.sun_angle, 0, -.5)
    sky = sky_node(entry)
    if sky:
        if hasattr(sky, 'sun_elevation'):
            sky.sun_elevation = entry.sun_angle
        if hasattr(sky, 'sun_rotation'):
            sky.sun_rotation = -.5
        sky.sun_direction = (math.cos(entry.sun_angle) * math.sin(-.5),
                             -math.cos(entry.sun_angle) * math.cos(-.5), math.sin(entry.sun_angle))


def _setting(scene, path):
    parent, name = path.split('.')
    obj = getattr(scene, parent, None)
    return (obj, name) if obj is not None and hasattr(obj, name) else (None, name)


def restore(scene, entry):
    if entry.mode != C.MODE_LIGHTING:
        return
    scene.world = entry.light_previous_world
    for path, value in json.loads(entry.light_restore or '{}').items():
        obj, name = _setting(scene, path)
        if obj is not None:
            setattr(obj, name, value)


def create(scene):
    if existing(scene):
        raise RuntimeError('This scene already has Water Lighting.')
    uid = naming.new_uuid()
    col = naming.new_assembly_collection(scene, C.MODE_LIGHTING, uid)
    entry = registry.add(scene, C.MODE_LIGHTING, uid, root_collection=col)
    entry.light_previous_world = scene.world
    settings = {}
    changes = {}
    for path, value in (('eevee.use_raytracing', True), ('eevee.use_ssr', True),
                        ('eevee.use_ssr_refraction', True), ('cycles.max_bounces', 12),
                        ('cycles.transmission_bounces', 8), ('cycles.transparent_max_bounces', 8)):
        obj, name = _setting(scene, path)
        if obj is None:
            continue
        old = getattr(obj, name)
        new = value if isinstance(value, bool) else max(old, value)
        if old != new:
            settings[path], changes[path] = old, new
    entry.light_restore = json.dumps(settings)
    world = bpy.data.worlds.new('AQS_Water_Sky')
    naming.tag(world, C.MODE_LIGHTING, uid)
    entry.light_world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    nodes.clear()
    sky = nodes.new('ShaderNodeTexSky')
    sky['aqs_sky'] = True
    choices = {i.identifier for i in sky.bl_rna.properties['sky_type'].enum_items}
    sky.sky_type = next(v for v in ('MULTIPLE_SCATTERING', 'NISHITA', 'HOSEK_WILKIE', 'PREETHAM') if v in choices)
    if hasattr(sky, 'sun_disc'):
        sky.sun_disc = False  # The owned Sun supplies the direct light.
    background = nodes.new('ShaderNodeBackground')
    background.inputs['Strength'].default_value = .3
    output = nodes.new('ShaderNodeOutputWorld')
    world.node_tree.links.new(sky.outputs['Color'], background.inputs['Color'])
    world.node_tree.links.new(background.outputs[0], output.inputs['Surface'])
    data = bpy.data.lights.new('AQS_Water_Sun', 'SUN')
    naming.tag(data, C.MODE_LIGHTING, uid)
    data.angle = math.radians(5)
    sun = bpy.data.objects.new(data.name, data)
    naming.tag(sun, C.MODE_LIGHTING, uid)
    col.objects.link(sun)
    entry.primary = sun
    update(entry)
    for path, value in changes.items():
        obj, name = _setting(scene, path)
        setattr(obj, name, value)
    scene.world = world
    return entry


class AQS_OT_water_lighting(bpy.types.Operator):
    bl_idname = 'aquasuite.water_lighting'
    bl_label = 'Add Water Lighting'
    bl_description = 'Add a removable sky and sun with water-friendly render settings'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and existing(context.scene) is None

    @delete.guarded_create
    def execute(self, context):
        create(context.scene)
        self.report({'INFO'}, 'Water Lighting added — use Rendered shading, or enable Scene World and Scene Lights in Material Preview')
        return {'FINISHED'}


CLASSES = (AQS_OT_water_lighting,)
