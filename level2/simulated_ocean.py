# SPDX-License-Identifier: GPL-3.0-or-later
"""A closed liquid tank with an animated piston paddle."""
import math

import bpy
import bmesh
from mathutils import Vector

from .. import constants as C
from ..core import delete, naming, registry, presets, whitewater
from ..materials import mats
from . import still_water as sw

ROLE = 'aqs_tank_role'


def _box(col, uid, role):
    mesh = bpy.data.meshes.new('AQS_Tank_' + role.title())
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(mesh)
    finally:
        bm.free()
    obj = naming.new_mesh_object(col, mesh.name, mesh, C.MODE_SIMOCEAN, uid)
    obj[ROLE] = role
    return obj


def _part(entry, role):
    col = entry.root_collection
    return next((o for o in col.all_objects if naming.owned_by(o, entry.uuid)
                 and o.get(ROLE) == role), None) if col else None


def _paddle_curve(paddle, entry):
    animation = paddle.animation_data
    if animation is None or animation.action is None:
        paddle.keyframe_insert(data_path='location', index=0, frame=1)
        animation = paddle.animation_data
    action = animation.action
    naming.tag(action, entry.mode, entry.uuid)
    # Blender 4.4+ uses slots/channelbags; 4.2 uses legacy fcurves.
    if hasattr(action, 'slots') and getattr(animation, 'action_slot', None):
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(action, animation.action_slot)
        curves = bag.fcurves if bag else ()
    else:
        curves = action.fcurves
    curve = next((f for f in curves if f.data_path == 'location' and f.array_index == 0), None)
    if curve is None:
        raise RuntimeError('Could not find the wave paddle animation channel.')
    return curve


def apply_settings(context, entry):
    dom, ds = presets.domain(entry)
    source, paddle = _part(entry, 'water'), _part(entry, 'paddle')
    if dom is None or source is None or paddle is None:
        raise RuntimeError('The wave tank is incomplete. Recreate this setup.')
    length, width, depth = entry.tank_size
    scene = presets.scene_for(entry)
    origin = Vector(entry.get('tank_origin', (0, 0, 0)))
    resolution = max(16, entry.base_resolution // 2) if entry.draft else entry.base_resolution
    dx = max(entry.tank_size) / resolution
    # A finite piston, kept inside the walls through its full stroke.
    amplitude = min(entry.wave_height * 0.5, length * 0.08)
    thick = max(0.2, dx * 1.5)
    center_x = -length / 2 + thick / 2 + amplitude + dx
    water_depth = depth * 0.55
    dom.location = origin + Vector((0, 0, depth / 2))
    dom.scale = (length, width, depth)
    ds.resolution_max = resolution
    ds.mesh_scale = 1 if entry.draft else 2
    for side in ('front', 'back', 'left', 'right', 'top', 'bottom'):
        setattr(ds, 'use_collision_border_' + side, True)
    source.location = origin + Vector((thick / 2 + amplitude / 2 + dx / 2, 0, water_depth / 2))
    source.scale = (max(length - thick - amplitude - 3 * dx, dx),
                    max(width - 2 * dx, dx), max(water_depth - dx, dx))
    paddle.location = origin + Vector((center_x, 0, depth * 0.5))
    paddle.scale = (thick, max(width - dx, dx), depth * 0.98)
    curve = _paddle_curve(paddle, entry)
    for key in curve.keyframe_points:
        key.co.y = paddle.location.x
        key.interpolation = 'CONSTANT'
    modifier = next((m for m in curve.modifiers if m.type == 'FNGENERATOR'), None)
    if modifier is None:
        modifier = curve.modifiers.new('FNGENERATOR')
    fps = scene.render.fps / scene.render.fps_base
    modifier.function_type = 'SIN'
    modifier.use_additive = True
    modifier.amplitude = amplitude
    modifier.phase_multiplier = 2 * math.pi / (entry.wave_period * fps)
    modifier.phase_offset = -scene.frame_start * modifier.phase_multiplier
    modifier.value_offset = 0
    effector = next(m.effector_settings for m in paddle.modifiers if m.type == 'FLUID')
    effector.use_effector = True
    effector.subframes = min(8, max(2, math.ceil(amplitude * 2 * math.pi / entry.wave_period / (dx * fps))))
    whitewater.apply(entry)
    dom.update_tag()
    paddle.update_tag()


class AQS_OT_simulated_ocean_create(bpy.types.Operator):
    bl_idname = 'aquasuite.simulated_ocean_create'
    bl_label = 'Create Ocean (Simulated)'
    bl_description = 'Beta: a liquid wave tank with a moving paddle; bake to see waves'
    bl_options = {'REGISTER', 'UNDO'}
    preset: bpy.props.EnumProperty(name='Preset', items=presets.ITEMS[C.MODE_SIMOCEAN],
                                   default='OCEAN_ROLLING')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_SIMOCEAN, uid)
        dom = _box(col, uid, 'domain')
        mod = dom.modifiers.new('AQS Fluid', 'FLUID')
        mod.fluid_type = 'DOMAIN'
        ds = sw.setup_domain_settings(mod, uid, 96)
        ds.cache_frame_start = scene.frame_start
        ds.cache_frame_end = min(scene.frame_end, scene.frame_start + 143)
        mats.assign(dom, mats.water_surface(C.MODE_SIMOCEAN, uid, name='AQS_Tank_Liquid'))
        source = _box(col, uid, 'water')
        flow = source.modifiers.new('AQS Water Fill', 'FLUID')
        flow.fluid_type = 'FLOW'
        flow.flow_settings.flow_type = 'LIQUID'
        flow.flow_settings.flow_behavior = 'GEOMETRY'
        source.hide_render = True
        source.display_type = 'WIRE'
        paddle = _box(col, uid, 'paddle')
        mod = paddle.modifiers.new('AQS Wave Paddle', 'FLUID')
        mod.fluid_type = 'EFFECTOR'
        mod.effector_settings.effector_type = 'COLLISION'
        paddle.hide_render = True
        paddle.display_type = 'WIRE'
        entry = registry.add(scene, C.MODE_SIMOCEAN, uid, primary=dom, root_collection=col)
        entry['tank_origin'] = list(scene.cursor.location)
        presets.apply(context, entry, self.preset)
        sw.add_effectors(scene, dom, uid)
        context.view_layer.objects.active = dom
        self.report({'INFO'}, 'Wave tank created — save and bake; Draft suspends whitewater')
        return {'FINISHED'}


CLASSES = (AQS_OT_simulated_ocean_create,)
