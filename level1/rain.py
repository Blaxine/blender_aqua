# SPDX-License-Identifier: GPL-3.0-or-later
"""Plane Rain (TDD §6.2)."""

import bpy
import bmesh

from .. import constants as C
from ..core import delete, naming, registry
from ..materials import mats


def _safe(obj, attr, value):
    if hasattr(obj, attr):
        try:
            setattr(obj, attr, value)
        except Exception as exc:
            print(f"[AquaSuite] could not set {attr}: {exc}")


def make_plane(name, size, mode, uid, col):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size * 0.5)
    bm.to_mesh(mesh)
    bm.free()
    return naming.new_mesh_object(col, name, mesh, mode, uid)


def make_droplet(name, mode, uid, col, streak=True):
    """UV sphere 8x6 stretched 2.4x along local X: perceived streak shape
    (§6.2.2).  X, because particle rotation mode VEL points the instance's
    X axis along the velocity."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=0.008)
    if streak:
        for v in bm.verts:
            v.co.x *= 2.4
    bm.to_mesh(mesh)
    bm.free()
    obj = naming.new_mesh_object(col, name, mesh, mode, uid)
    obj.hide_render = True
    obj.hide_set(True) if hasattr(obj, "hide_set") else None
    return obj


def configure_rain_settings(ps, droplet, intensity=1.0, area=10.0,
                            fall_speed=9.0, wind=0.0):
    """Authored settings table §6.2.3 (area-normalized count §6.2.4)."""
    scene = bpy.context.scene
    ps.count = int(4000 * intensity * (area / 10.0) ** 2)
    ps.frame_start = scene.frame_start
    ps.frame_end = scene.frame_end
    ps.lifetime = 60
    ps.emit_from = "FACE"
    _safe(ps, "distribution", "RAND")
    ps.normal_factor = 0.0
    ps.object_align_factor[0] = wind
    ps.object_align_factor[2] = -fall_speed
    # Raindrops fall at terminal velocity: constant speed, no further
    # acceleration.  A constant velocity also keeps each streak (aligned
    # to the velocity at birth by rotation mode VEL) along its path.
    ps.effector_weights.gravity = 0.0
    ps.brownian_factor = 0.02
    ps.render_type = "OBJECT"
    ps.instance_object = droplet
    ps.particle_size = 1.0
    ps.size_random = 0.35
    ps.use_rotations = True
    _safe(ps, "rotation_mode", "VEL")
    ps.use_dynamic_rotation = False
    ps.display_percentage = 100
    _safe(ps, "use_die_on_collision", True)  # universal obstacle rule


def add_particle_system(emitter, ps_name, mode, uid):
    psys_mod = emitter.modifiers.new(ps_name, "PARTICLE_SYSTEM")
    psys = emitter.particle_systems[-1]
    ps = psys.settings
    ps.name = ps_name
    naming.tag(ps, mode, uid)
    return psys_mod, psys, ps


class AQS_OT_rain_create(bpy.types.Operator):
    bl_idname = "aquasuite.rain_create"
    bl_label = "Create Plane Rain"
    bl_description = "A plane that rains — press Play"
    bl_options = {"REGISTER", "UNDO"}

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_RAIN, uid)

        emitter = make_plane("AQS_Rain_Emitter", 10.0, C.MODE_RAIN, uid, col)
        emitter.show_instancer_for_render = False
        droplet = make_droplet("AQS_Rain_Droplet", C.MODE_RAIN, uid, col)
        mats.assign(droplet, mats.droplet(C.MODE_RAIN, uid))

        _mod, _psys, ps = add_particle_system(emitter, "AQS_PS_Rain",
                                              C.MODE_RAIN, uid)
        configure_rain_settings(ps, droplet)

        registry.add(scene, C.MODE_RAIN, uid, primary=emitter,
                     root_collection=col)
        context.view_layer.objects.active = emitter
        self.report({"INFO"}, "AquaSuite: Plane Rain created — press Play")
        return {"FINISHED"}


CLASSES = (AQS_OT_rain_create,)
