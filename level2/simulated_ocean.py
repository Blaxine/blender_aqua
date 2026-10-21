# SPDX-License-Identifier: GPL-3.0-or-later
"""A closed liquid tank whose waves come from a sine-driven Wind field
acting over a full-depth zone at the left wall.

Tanks saved before 0.20 have a piston paddle instead; they keep it and
behave as they did until the user upgrades them (Upgrade Wave Maker).
"""
import math

import bpy
import bmesh
from mathutils import Vector

from .. import constants as C
from ..core import delete, naming, registry, presets, whitewater
from ..materials import mats
from . import still_water as sw

ROLE = 'aqs_tank_role'
GRAVITY = 9.81
WATER_FRACTION = 0.55   # still-water depth as a share of the tank height
STEEPNESS_MARGIN = 0.8  # share of the breaking limit a requested wave may use
# Blender passes a force field to the liquid as 0.2 * strength in metres per
# frame and Mantaflow adds it to the velocity once per solver step, so a Wind
# of strength S accelerates the water by 0.2 * S * fps m/s^2 per step per
# frame.  Measured (Blender 4.5, static tilt): 0.195 at 24 and 48 fps, the
# same at resolution 80 and 160, doubled with two steps per frame.  The tank
# takes one step per frame: its waves move far less than a cell per frame.
WIND_GAIN = 0.2
# Measured mid-tank height / linear-theory height, Blender 4.5, shipped
# presets after 12 s: Calm 1.17, Rolling 0.87, Storm 1.04 — the theory
# holds once waves span a few cells, so no fudge factor is applied.
WAVE_EFFICIENCY = 1.0
ZONE_SHARE = 0.2        # the forcing zone may use at most this share of the tank
# Wave fronts creep at ~0.7 m/s (their low leading edge is under a cell), so
# waves first reach the far end 20-24 s into the bake; new tanks cache 30 s.
CACHE_SECONDS = 30
# Blender's liquid solver puts the free surface on whole cells, so a wave
# lower than about a cell gets no restoring force and stops; coarse cells
# also damp waves roughly as cell size squared.  Measured at 720 frames:
# Calm 0.12 m crossed the tank at 5 cm cells (2.4 cells high) but stalled
# 12 m out at 10 cm (1.4 cells); Rolling 0.45 m crossed at 12.5 cm but
# stalled at Medium's 21 cm (2.2 cells, ~0.2/m decay).
CELLS_PER_WAVE = 2.4
MAX_CELL = 0.125


def effective_resolution(entry):
    """The resolution the bake uses: Draft halves it."""
    return max(16, entry.base_resolution // 2) if entry.draft else entry.base_resolution


def min_resolution(entry):
    """The lowest resolution whose cells let this tank's waves cross it."""
    height, _amplitude = wave_plan(entry)
    cell = min(height / CELLS_PER_WAVE, MAX_CELL)
    return math.ceil(round(max(entry.tank_size) / max(cell, 1e-6), 3))


def resolution_warning(entry, buttons=()):
    """'' when the waves can cross the tank, else what to change.  `buttons`
    are the panel's (label, resolution) presets, to name the one that works."""
    if is_legacy(entry):
        return ''
    need = min_resolution(entry)
    if effective_resolution(entry) >= need:
        return ''
    if entry.draft and entry.base_resolution >= need:
        return (f'Draft halves the resolution to {effective_resolution(entry)}: waves this '
                f'small die out part-way. Turn Draft off to bake waves that cross the tank')
    button = next((label for label, res in sorted(buttons, key=lambda b: b[1]) if res >= need),
                  'Custom')
    return (f'Waves this small need resolution {need} or more ({button}) to cross the '
            f'tank; at {effective_resolution(entry)} they die out part-way')


def wave_number(period, depth):
    """Solve the linear dispersion relation w^2 = g k tanh(k h) for k."""
    omega = 2 * math.pi / period
    k = max(omega * omega / GRAVITY, 1e-6)  # deep-water first guess
    for _ in range(60):
        t = math.tanh(k * depth)
        step = (GRAVITY * k * t - omega * omega) / (
            GRAVITY * (t + k * depth * (1 - t * t)))
        k -= step
        if abs(step) < 1e-9 * k:
            break
    return k


def wave_plan(entry):
    """(achievable wave height, legacy paddle amplitude) for the request.

    The request is capped below the Miche breaking limit
    H = 0.142 L tanh(kh): a steeper wave breaks where it is made and never
    travels.  The amplitude is the stroke of the pre-0.20 piston paddle from
    linear piston-wavemaker theory, H = S * 2(cosh 2kh - 1) / (sinh 2kh + 2kh);
    only tanks that still have a paddle use it.
    """
    length, _width, depth = entry.tank_size
    h = depth * WATER_FRACTION
    k = wave_number(entry.wave_period, h)
    kh = k * h
    limit = STEEPNESS_MARGIN * 0.142 * (2 * math.pi / k) * math.tanh(kh)
    height = min(entry.wave_height, limit)
    gain = 2.0 if kh > 10 else \
        2 * (math.cosh(2 * kh) - 1) / (math.sinh(2 * kh) + 2 * kh)
    return height, min(height / gain / 2, length * 0.08)


def forcing_plan(entry, fps):
    """(achievable wave height, zone length m, Wind strength amplitude).

    A horizontal force F uniform over the depth is curl-free, so it acts on
    the water exactly like a surface pressure p = -rho * integral(F dx): a
    zone of length l against the wall is a triangular pressure patch.  Linear
    theory for an oscillating surface pressure in depth h gives a wave of
    height H = 4 w F sin^2(k l / 2) / (g k^2 c_g) travelling away from it,
    most efficiently when l is half a wavelength.
    """
    height, _amplitude = wave_plan(entry)
    length, _width, depth = entry.tank_size
    h = depth * WATER_FRACTION
    k = wave_number(entry.wave_period, h)
    omega = 2 * math.pi / entry.wave_period
    kh = k * h
    group = omega / k * 0.5 * (1 + (2 * kh / math.sinh(2 * kh) if kh < 10 else 0))
    zone = min(math.pi / k, length * ZONE_SHARE)
    accel = height * GRAVITY * k * k * group / (4 * omega * math.sin(k * zone / 2) ** 2)
    return height, zone, accel / (WAVE_EFFICIENCY * WIND_GAIN * fps)


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


def is_legacy(entry):
    """A tank saved before 0.20: it still makes waves with a paddle."""
    return _part(entry, 'wavemaker') is None and _part(entry, 'paddle') is not None


def _curve(obj, entry, path, index=None):
    """The F-curve animating obj.<path> (element `index` of an array
    property), created on first use."""
    animation = obj.animation_data
    if animation is None or animation.action is None:
        if index is None:
            obj.keyframe_insert(data_path=path, frame=1)
        else:
            obj.keyframe_insert(data_path=path, index=index, frame=1)
        animation = obj.animation_data
    action = animation.action
    naming.tag(action, entry.mode, entry.uuid)
    # Blender 4.4+ uses slots/channelbags; 4.2 uses legacy fcurves.
    if hasattr(action, 'slots') and getattr(animation, 'action_slot', None):
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        bag = action_get_channelbag_for_slot(action, animation.action_slot)
        curves = bag.fcurves if bag else ()
    else:
        curves = action.fcurves
    curve = next((f for f in curves if f.data_path == path
                  and f.array_index == (index or 0)), None)
    if curve is None:
        raise RuntimeError('Could not find the wave maker animation channel.')
    return curve


def _paddle_curve(paddle, entry):
    return _curve(paddle, entry, 'location', 0)


def _strength_curve(field_obj, entry):
    """The driver F-curve on field.strength, created on first use.

    A driver, not an action: Blender links every keyframed force field to
    the rigid body world and, when the scene has none, prints 'Failed to add
    relation "Animation -> Rigid Body"' at every relations rebuild.  The
    driver feeds the frame to the curve (a simple expression, so it runs
    without Python auto-run), and the curve is the one 0.20.0 keyframed: a
    constant 0 key plus the sine modifier, so the strength is unchanged.
    A 0.20.0 tank's action is replaced here, at its next bake or edit."""
    animation = field_obj.animation_data
    curve = next((d for d in animation.drivers if d.data_path == 'field.strength'),
                 None) if animation else None
    if curve is None:
        action = animation.action if animation else None
        if action is not None and naming.owned_by(action, entry.uuid):
            animation.action = None
            if not action.users:
                bpy.data.actions.remove(action)
        curve = field_obj.driver_add('field.strength')
        for modifier in list(curve.modifiers):  # driver_add adds a Generator
            curve.modifiers.remove(modifier)
        curve.keyframe_points.insert(1, 0)
    driver = curve.driver
    driver.type = 'SCRIPTED'
    driver.expression = 'frame'
    return curve


def _sine(curve, amplitude, period, fps, start):
    modifier = next((m for m in curve.modifiers if m.type == 'FNGENERATOR'), None)
    if modifier is None:
        modifier = curve.modifiers.new('FNGENERATOR')
    modifier.function_type = 'SIN'
    modifier.use_additive = True
    modifier.amplitude = amplitude
    modifier.phase_multiplier = 2 * math.pi / (period * fps)
    modifier.phase_offset = -start * modifier.phase_multiplier
    modifier.value_offset = 0
    return modifier


# --- pre-0.20 paddle tanks -------------------------------------------------

def _place_parts(entry, paddle, source, amplitude, dx):
    """A finite piston kept inside the walls through its full stroke, and
    the initial water block one cell in front of it.  Both depend on the
    stroke, which depends on the period — so period edits re-place them."""
    length, width, depth = entry.tank_size
    origin = Vector(entry.get('tank_origin', (0, 0, 0)))
    water_depth = depth * WATER_FRACTION
    thick = max(0.2, dx * 1.5)
    center_x = -length / 2 + thick / 2 + amplitude + dx
    paddle.location = origin + Vector((center_x, 0, depth * 0.5))
    paddle.scale = (thick, max(width - dx, dx), depth * 0.98)
    curve = _paddle_curve(paddle, entry)
    for key in curve.keyframe_points:  # animation overrides .location
        key.co.y = paddle.location.x
        key.interpolation = 'CONSTANT'
    source.location = origin + Vector((thick / 2 + amplitude / 2 + dx / 2, 0, water_depth / 2))
    source.scale = (max(length - thick - amplitude - 3 * dx, dx),
                    max(width - 2 * dx, dx), max(water_depth - dx, dx))
    return curve


def _apply_paddle(entry, scene, ds, source, paddle):
    _height, amplitude = wave_plan(entry)
    dx = max(entry.tank_size) / max(ds.resolution_max, 1)
    curve = _place_parts(entry, paddle, source, amplitude, dx)
    fps = scene.render.fps / scene.render.fps_base
    _sine(curve, amplitude, entry.wave_period, fps, scene.frame_start)
    effector = next(m.effector_settings for m in paddle.modifiers if m.type == 'FLUID')
    effector.use_effector = True
    effector.subframes = min(8, max(2, math.ceil(amplitude * 2 * math.pi / entry.wave_period / (dx * fps))))
    paddle.update_tag()


# --- force-field wave maker ------------------------------------------------


def _apply_wavemaker(entry, scene, ds, source, field_obj):
    """Fill the tank with still water and drive the Wind field: full depth
    and width, `zone` metres from the left wall, strength a sine at the wave
    period that fades in over the first period of the bake."""
    length, width, depth = entry.tank_size
    origin = Vector(entry.get('tank_origin', (0, 0, 0)))
    water_depth = depth * WATER_FRACTION
    dx = max(entry.tank_size) / max(ds.resolution_max, 1)
    source.location = origin + Vector((0, 0, water_depth / 2))
    source.scale = (max(length - 2 * dx, dx), max(width - 2 * dx, dx),
                    max(water_depth - dx, dx))
    fps = scene.render.fps / scene.render.fps_base
    _height, zone, strength = forcing_plan(entry, fps)
    field_obj.location = origin + Vector((-length / 2, 0, depth / 2))
    field_obj.rotation_euler = (0, math.pi / 2, 0)  # field +Z along tank +X
    field = field_obj.field
    field.type = 'WIND'
    field.shape = 'PLANE'
    field.falloff_type = 'TUBE'
    field.z_direction = 'POSITIVE'      # nothing behind the left wall
    field.use_max_distance = True
    field.distance_max = zone
    field.use_radial_max = True         # the tank cross-section, no further
    field.radial_max = math.hypot(width / 2, depth / 2) + dx
    field.falloff_power = 0
    field.radial_falloff = 0
    field.flow = 0
    field.noise = 0
    field.strength = 0
    curve = _strength_curve(field_obj, entry)
    for key in curve.keyframe_points:
        key.co.y = 0
        key.interpolation = 'CONSTANT'
    start = ds.cache_frame_start
    modifier = _sine(curve, strength, entry.wave_period, fps, start)
    # A sudden full-strength start kicks the whole tank into a slow sloshing
    # mode; fading in over one period avoids it.
    modifier.use_restricted_range = True
    modifier.frame_start = start
    modifier.frame_end = start + 1000000
    modifier.blend_in = entry.wave_period * fps
    modifier.blend_out = 0
    # Only this tank's own fields push its water, and the Wind is limited to
    # the tank, so neither scene fields nor this one leak across.
    ds.effector_weights.collection = entry.root_collection
    field_obj.update_tag()


def _add_wavemaker(col, uid):
    obj = naming.new_mesh_object(col, 'AQS_Tank_Wavemaker', None, C.MODE_SIMOCEAN, uid)
    obj[ROLE] = 'wavemaker'
    obj.empty_display_type = 'SINGLE_ARROW'
    obj.empty_display_size = 2.0
    obj.hide_render = True
    # Object.field is only allocated by the force-field operator.
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.forcefield_toggle()
    obj.field.type = 'WIND'
    return obj


def apply_settings(context, entry):
    dom, ds = presets.domain(entry)
    source = _part(entry, 'water')
    maker = _part(entry, 'wavemaker') or _part(entry, 'paddle')
    if dom is None or source is None or maker is None:
        raise RuntimeError('The wave tank is incomplete. Recreate this setup.')
    length, width, depth = entry.tank_size
    origin = Vector(entry.get('tank_origin', (0, 0, 0)))
    resolution = max(16, entry.base_resolution // 2) if entry.draft else entry.base_resolution
    dom.location = origin + Vector((0, 0, depth / 2))
    dom.scale = (length, width, depth)
    ds.resolution_max = resolution
    ds.mesh_scale = 1 if entry.draft else 2
    for side in ('front', 'back', 'left', 'right', 'top', 'bottom'):
        setattr(ds, 'use_collision_border_' + side, True)
    apply_period(entry)  # places the wave maker + water block
    whitewater.apply(entry)
    dom.update_tag()


def apply_period(entry):
    """Update the wave maker's timing and strength (or the legacy paddle's
    stroke and subframes) without touching the domain or liquid settings."""
    dom, ds = presets.domain(entry)
    source = _part(entry, 'water')
    field_obj, paddle = _part(entry, 'wavemaker'), _part(entry, 'paddle')
    if dom is None or ds is None or source is None or (field_obj or paddle) is None:
        raise RuntimeError('The wave tank is incomplete. Recreate this setup.')
    scene = presets.scene_for(entry)
    if field_obj is not None:
        _apply_wavemaker(entry, scene, ds, source, field_obj)
    else:
        _apply_paddle(entry, scene, ds, source, paddle)


def upgrade(context, entry):
    """Replace a pre-0.20 paddle with the force-field wave maker.  The bake
    is not touched; Bake Again shows the new waves."""
    paddle = _part(entry, 'paddle')
    if paddle is None:
        return False
    action = paddle.animation_data.action if paddle.animation_data else None
    bpy.data.objects.remove(paddle, do_unlink=True)
    if action is not None and naming.owned_by(action, entry.uuid) and not action.users:
        bpy.data.actions.remove(action)
    _add_wavemaker(entry.root_collection, entry.uuid)
    with presets.applying(entry):
        apply_settings(context, entry)
    return True


class AQS_OT_simulated_ocean_create(bpy.types.Operator):
    bl_idname = 'aquasuite.simulated_ocean_create'
    bl_label = 'Create Ocean (Simulated)'
    bl_description = 'Beta: a liquid wave tank driven by a wave maker; bake to see waves'
    bl_options = {'REGISTER', 'UNDO'}
    preset: bpy.props.EnumProperty(name='Preset', items=presets.ITEMS[C.MODE_SIMOCEAN],
                                   default='OCEAN_ROLLING')

    def invoke(self, context, event):
        return self.execute(context)

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_SIMOCEAN, uid)
        dom = _box(col, uid, 'domain')
        mod = dom.modifiers.new('AQS Fluid', 'FLUID')
        mod.fluid_type = 'DOMAIN'
        ds = sw.setup_domain_settings(mod, uid, 96)
        fps = scene.render.fps / scene.render.fps_base
        ds.cache_frame_start = scene.frame_start
        ds.cache_frame_end = scene.frame_start + round(CACHE_SECONDS * fps) - 1
        extended = scene.frame_end < ds.cache_frame_end
        if extended:  # the bake is only played back inside the scene range
            scene.frame_end = ds.cache_frame_end
        mats.assign(dom, mats.water_surface(C.MODE_SIMOCEAN, uid, name='AQS_Tank_Liquid'))
        source = _box(col, uid, 'water')
        flow = source.modifiers.new('AQS Water Fill', 'FLUID')
        flow.fluid_type = 'FLOW'
        flow.flow_settings.flow_type = 'LIQUID'
        flow.flow_settings.flow_behavior = 'GEOMETRY'
        source.hide_render = True
        source.display_type = 'WIRE'
        _add_wavemaker(col, uid)
        entry = registry.add(scene, C.MODE_SIMOCEAN, uid, primary=dom, root_collection=col)
        entry['tank_origin'] = list(scene.cursor.location)
        presets.apply(context, entry, self.preset)
        sw.add_effectors(scene, dom, uid)
        sw.sync_flows(entry)
        context.view_layer.objects.active = dom
        self.report({'INFO'}, f'Wave tank created — save and bake; the bake covers {CACHE_SECONDS} s '
                    f'({ds.cache_frame_end - ds.cache_frame_start + 1} frames)'
                    + (', so the timeline was extended' if extended else '')
                    + '; Draft suspends whitewater')
        return {'FINISHED'}


class AQS_OT_simulated_ocean_upgrade(bpy.types.Operator):
    bl_idname = 'aquasuite.simulated_ocean_upgrade'
    bl_label = 'Upgrade Wave Maker'
    bl_description = ("Replace this tank's paddle with the force-field wave maker, "
                      'whose waves travel down the tank. Bake Again afterwards')
    bl_options = {'REGISTER', 'UNDO'}
    uuid: bpy.props.StringProperty()

    def execute(self, context):
        from ..core import bakes, errors
        entry = registry.get(context.scene, self.uuid)
        if entry is None or entry.mode != C.MODE_SIMOCEAN:
            self.report({'ERROR'}, 'No wave tank found.')
            return {'CANCELLED'}
        if bakes.is_baking(entry):
            self.report({'ERROR'}, 'Stop the current bake first.')
            return {'CANCELLED'}
        try:
            changed = upgrade(context, entry)
        except Exception as exc:
            return errors.fail(self, "AquaSuite couldn't upgrade the wave maker", exc,
                               mode=entry.mode, uuid=self.uuid)
        self.report({'INFO'}, 'Wave maker upgraded — Bake Again to see the new waves'
                    if changed else 'This tank already uses the new wave maker')
        return {'FINISHED'}


CLASSES = (AQS_OT_simulated_ocean_create, AQS_OT_simulated_ocean_upgrade)
