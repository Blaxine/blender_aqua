# SPDX-License-Identifier: GPL-3.0-or-later
"""Reactive Plane Rain (TDD §6.3): Plane Rain + Dynamic Paint wave floor.

The rain particle system itself is the Dynamic Paint brush (§6.3.2).
Canvas substeps follow R1.10 to prevent droplet tunneling.
"""

import bpy
import bmesh

from .. import constants as C
from ..core import delete, naming, registry
from ..materials import mats
from . import rain as rain_mod


def _safe(o, attr, value):
    if hasattr(o, attr):
        try:
            setattr(o, attr, value)
        except Exception as exc:
            print(f"[AquaSuite] could not set {attr}: {exc}")


def _dpaint_toggle(context, obj, dp_type):
    """Create canvas/brush settings via the operator (required by the API).

    type_toggle only acts on an EXISTING Dynamic Paint modifier — without
    one it silently returns CANCELLED — so make sure the modifier is there.
    """
    if not any(m.type == "DYNAMIC_PAINT" for m in obj.modifiers):
        obj.modifiers.new("AQS Dynamic Paint", "DYNAMIC_PAINT")
    with context.temp_override(active_object=obj, object=obj,
                               selected_objects=[obj]):
        bpy.ops.dpaint.type_toggle(type=dp_type)


def make_floor(context, uid, col, detail=256, size=10.0):
    mesh = bpy.data.meshes.new("AQS_RRain_Floor")
    bm = bmesh.new()
    seg = max(2, detail)
    bmesh.ops.create_grid(bm, x_segments=seg, y_segments=seg, size=size * 0.5)
    bm.to_mesh(mesh)
    bm.free()
    floor = naming.new_mesh_object(col, "AQS_RRain_Floor", mesh,
                                   C.MODE_RRAIN, uid)
    return floor


def configure_canvas(context, floor, fall_speed=9.0):
    _dpaint_toggle(context, floor, "CANVAS")
    mod = next((m for m in floor.modifiers if m.type == "DYNAMIC_PAINT"), None)
    if mod is None or mod.canvas_settings is None:
        raise RuntimeError("Dynamic Paint canvas could not be created")
    surfaces = mod.canvas_settings.canvas_surfaces
    surf = surfaces[0] if len(surfaces) else None
    if surf is None:
        raise RuntimeError("No Dynamic Paint surface")
    surf.name = "AQS_DP_RippleSurface"
    surf.surface_format = "VERTEX"
    surf.surface_type = "WAVE"
    _safe(surf, "use_wave_open_border", True)
    _safe(surf, "wave_timescale", 1.0)
    _safe(surf, "wave_speed", 1.2)
    _safe(surf, "wave_damping", 0.045)
    _safe(surf, "wave_spring", 0.18)
    _safe(surf, "wave_smoothness", 1.0)
    _safe(surf, "use_antialiasing", True)
    # R1.10 substep formula against droplet tunneling.
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    substeps = int(round(fall_speed / (fps * 0.15)))
    _safe(surf, "frame_substeps", max(2, min(substeps, 6)))
    if fps < 12:
        print("[AquaSuite] W009:", C.MSG["W009"])
    return surf


def configure_brush(context, emitter, psys):
    _dpaint_toggle(context, emitter, "BRUSH")
    mod = next((m for m in emitter.modifiers if m.type == "DYNAMIC_PAINT"), None)
    brush = getattr(mod, "brush_settings", None)
    if brush is None:
        raise RuntimeError("Dynamic Paint brush could not be created")
    brush.paint_source = "PARTICLE_SYSTEM"
    brush.particle_system = psys
    _safe(brush, "solid_radius", 0.012)
    _safe(brush, "particle_radius", 0.012)
    _safe(brush, "wave_factor", 0.6)          # x Ripple Strength (§6.3.3)
    _safe(brush, "wave_clamp", 0.15)          # stability clamp
    return brush


class AQS_OT_rain_reactive_create(bpy.types.Operator):
    bl_idname = "aquasuite.rain_reactive_create"
    bl_label = "Create Reactive Rain"
    bl_description = ("Rain falling on a floor; every hit spawns an expanding "
                      "ripple (Dynamic Paint waves)")
    bl_options = {"REGISTER", "UNDO"}

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_RRAIN, uid)

        emitter = rain_mod.make_plane("AQS_RRain_Emitter", 10.0,
                                      C.MODE_RRAIN, uid, col)
        emitter.show_instancer_for_render = False
        emitter.location.z = 6.0
        droplet = rain_mod.make_droplet("AQS_RRain_Droplet",
                                        C.MODE_RRAIN, uid, col)
        mats.assign(droplet, mats.droplet(C.MODE_RRAIN, uid))

        _mod, psys, ps = rain_mod.add_particle_system(
            emitter, "AQS_PS_RRain", C.MODE_RRAIN, uid)
        rain_mod.configure_rain_settings(ps, droplet)
        ps.lifetime = 40  # emitter sits 6 m up; safety cap past the floor
        _safe(ps, "use_die_on_collision", True)

        floor = make_floor(context, uid, col)
        mats.assign(floor, mats.ripple_floor(C.MODE_RRAIN, uid))
        # The floor must stop droplets: Collision modifier (the universal
        # obstacle switch) + die-on-hit, or drops rain through it forever.
        floor.modifiers.new("Collision", "COLLISION")
        if floor.collision:
            floor.collision.damping_factor = 1.0
            floor.collision.friction_factor = 1.0
        try:
            configure_canvas(context, floor)
            configure_brush(context, emitter, psys)
        except RuntimeError as exc:
            from ..core import errors
            return errors.fail(self, "AquaSuite couldn't create Reactive Rain",
                               exc, mode=C.MODE_RRAIN)

        registry.add(scene, C.MODE_RRAIN, uid, primary=floor,
                     root_collection=col)
        context.view_layer.objects.active = floor
        self.report({"INFO"},
                    "AquaSuite: Reactive Rain created — press Play "
                    "(bake ripples before scrubbing)")
        return {"FINISHED"}


class AQS_OT_bake_ripples(bpy.types.Operator):
    bl_idname = "aquasuite.bake_ripples"
    bl_label = "Bake Ripples"
    bl_description = "Point-cache bake of the ripple canvas (scrub-safe after)"

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        floor = entry.primary if entry else None
        if floor is None:
            return {"CANCELLED"}
        mod = next((m for m in floor.modifiers if m.type == "DYNAMIC_PAINT"), None)
        surf = mod.canvas_settings.canvas_surfaces[0] if mod and mod.canvas_settings else None
        if surf is None:
            self.report({"ERROR"}, "No ripple canvas found")
            return {"CANCELLED"}
        try:
            with context.temp_override(active_object=floor, object=floor,
                                       point_cache=surf.point_cache):
                # A background job (progress bar, Esc stops it); blocking
                # only when headless.
                bpy.ops.ptcache.bake(
                    "EXEC_DEFAULT" if bpy.app.background else "INVOKE_DEFAULT",
                    bake=True)
        except Exception as exc:
            from ..core import errors
            return errors.fail(self, "AquaSuite couldn't bake the ripples", exc,
                               mode=C.MODE_RRAIN, uuid=self.uuid)
        if bpy.app.background:
            self.report({"INFO"}, "Ripples baked")
        else:
            from ..core import bakes
            bakes.watch()
            self.report({"INFO"}, "Baking ripples in the background — "
                                  "press Esc to stop")
        return {"FINISHED"}


CLASSES = (AQS_OT_rain_reactive_create, AQS_OT_bake_ripples)
