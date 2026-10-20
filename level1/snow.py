# SPDX-License-Identifier: GPL-3.0-or-later
"""Snow Plane (TDD §6.4): slow-fall particles instancing 1 snowball + 6
procedurally built, deterministic snowflake meshes (dendrite recipe)."""

import math

import bpy
import bmesh
from mathutils import Matrix, Vector

from .. import constants as C
from ..core import delete, naming, registry
from ..materials import mats
from . import rain as rain_mod


# Flake type tables (§6.4.2): (spine_width, [(pos_along, length, width), ...],
#                              plate_radius)
FLAKE_TYPES = {
    "A": (0.05, [], 0.0),                                        # simple stellar
    "B": (0.05, [(0.45, 0.35, 0.04), (0.70, 0.25, 0.035)], 0.0), # stellar dendrite
    "C": (0.045, [(0.30, 0.45, 0.035), (0.50, 0.40, 0.035),
                  (0.68, 0.30, 0.03), (0.84, 0.20, 0.03)], 0.0), # fern dendrite
    "D": (0.16, [], 0.55),                                       # plate, notched edge
    "E": (0.06, [(0.75, 0.18, 0.05)], 0.45),                     # sectored plate
    "F": (0.14, [(0.50, 0.30, 0.10)], 0.0),                      # broad-branch
}
BRANCH_ANGLE = math.radians(52.0)
FLAKE_RADIUS = 0.012  # metres, matches ball


def _quad(verts, faces, x0, y0, x1, y1, w):
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy) or 1.0
    px, py = -dy / ln * w * 0.5, dx / ln * w * 0.5
    base = len(verts)
    verts += [(x0 + px, y0 + py, 0), (x0 - px, y0 - py, 0),
              (x1 - px, y1 - py, 0), (x1 + px, y1 + py, 0)]
    faces.append((base, base + 1, base + 2, base + 3))


def _arm(verts, faces, spine_w, branches):
    _quad(verts, faces, 0.0, 0.0, 1.0, 0.0, spine_w)
    for pos, length, w in branches:
        for sgn in (1.0, -1.0):
            x1 = pos + length * math.cos(BRANCH_ANGLE)
            y1 = sgn * length * math.sin(BRANCH_ANGLE)
            _quad(verts, faces, pos, 0.0, x1, y1, w)


def build_flake_mesh(name, ftype):
    spine_w, branches, plate_r = FLAKE_TYPES[ftype]
    verts, faces = [], []
    _arm(verts, faces, spine_w, branches)

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    src_geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    for i in range(1, 6):  # array x6 at 60 deg (§6.4.2)
        rot = Matrix.Rotation(math.radians(60.0 * i), 4, "Z")
        ret = bmesh.ops.duplicate(bm, geom=src_geom)
        dup_verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.rotate(bm, verts=dup_verts, cent=Vector((0, 0, 0)), matrix=rot)
    if plate_r > 0.0:
        bmesh.ops.create_circle(bm, cap_ends=True, radius=plate_r, segments=6)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.scale(bm, verts=bm.verts,
                    vec=(FLAKE_RADIUS, FLAKE_RADIUS, FLAKE_RADIUS))
    bm.to_mesh(mesh)
    bm.free()
    return mesh


class AQS_OT_snow_create(bpy.types.Operator):
    bl_idname = "aquasuite.snow_create"
    bl_label = "Create Snow Plane"
    bl_description = "Soft-falling, tumbling snow with 7 instanced flake shapes"
    bl_options = {"REGISTER", "UNDO"}

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_SNOW, uid)

        emitter = rain_mod.make_plane("AQS_Snow_Emitter", 10.0,
                                      C.MODE_SNOW, uid, col)
        emitter.show_instancer_for_render = False
        emitter.location.z = 5.0

        shapes = bpy.data.collections.new("AQS_COL_SnowShapes")
        naming.tag(shapes, C.MODE_SNOW, uid)
        col.children.link(shapes)

        snow_mat = mats.snow(C.MODE_SNOW, uid)
        flake_mat = mats.flake(C.MODE_SNOW, uid)

        ball_mesh = bpy.data.meshes.new("AQS_Snow_Ball")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=FLAKE_RADIUS)
        bm.to_mesh(ball_mesh)
        bm.free()
        ball = naming.new_mesh_object(shapes, "AQS_Snow_Ball", ball_mesh,
                                      C.MODE_SNOW, uid)
        mats.assign(ball, snow_mat)

        for ftype in "ABCDEF":
            mesh = build_flake_mesh(f"AQS_Snow_Flake_{ftype}", ftype)
            naming.tag(mesh, C.MODE_SNOW, uid)
            fobj = naming.new_mesh_object(shapes, f"AQS_Snow_Flake_{ftype}",
                                          mesh, C.MODE_SNOW, uid)
            solid = fobj.modifiers.new("Solidify", "SOLIDIFY")
            solid.thickness = 0.0006
            mats.assign(fobj, flake_mat)

        for obj in shapes.objects:
            obj.hide_render = True

        _mod, _psys, ps = rain_mod.add_particle_system(
            emitter, "AQS_PS_Snow", C.MODE_SNOW, uid)
        # Authored deltas vs rain (§6.4.3)
        ps.count = 2500
        ps.frame_start = scene.frame_start
        ps.frame_end = scene.frame_end
        ps.lifetime = 240
        ps.emit_from = "FACE"
        ps.normal_factor = 0.0
        ps.object_align_factor[2] = -0.35 * 0.7   # x Fall Speed (default 0.7)
        ps.effector_weights.gravity = 0.08        # the slow-fall trick
        ps.brownian_factor = 0.35
        ps.drag_factor = 0.6
        ps.render_type = "COLLECTION"
        ps.instance_collection = shapes
        if hasattr(ps, "use_collection_pick_random"):
            ps.use_collection_pick_random = True
        ps.particle_size = 1.0
        ps.size_random = 0.5
        ps.use_rotations = True
        ps.rotation_factor_random = 1.0
        if hasattr(ps, "angular_velocity_mode"):
            ps.angular_velocity_mode = "RAND"
        ps.phase_factor_random = 2.0
        ps.display_percentage = 100

        registry.add(scene, C.MODE_SNOW, uid, primary=emitter,
                     root_collection=col)
        context.view_layer.objects.active = emitter
        self.report({"INFO"}, "AquaSuite: Snow Plane created — press Play")
        return {"FINISHED"}


CLASSES = (AQS_OT_snow_create,)
