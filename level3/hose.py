# SPDX-License-Identifier: GPL-3.0-or-later
"""Water Hose (TDD §8.1): one nozzle rig, four flow regimes.

Regime switching toggles backend objects' visibility flags and writes
the parameter package — it never deletes the other backend's objects
(§8.1.3).  The Blast velocity clamp follows the R1.9-corrected law:
v_max = S * CFL * dx * FPS * timesteps_max.
"""

import math

import bpy
import bmesh

from .. import constants as C
from ..core import delete, naming, registry
from ..materials import mats
from ..level2 import still_water as sw


def _safe(o, attr, value):
    if hasattr(o, attr):
        try:
            setattr(o, attr, value)
        except Exception as exc:
            print(f"[AquaSuite] could not set {attr}: {exc}")


def _find_domain(entry):
    """Rename-safe: identify by FLUID DOMAIN modifier, never by name."""
    col = entry.root_collection
    if col is None:
        return None
    for obj in col.all_objects:
        for m in obj.modifiers:
            if m.type == "FLUID" and getattr(m, "fluid_type", "") == "DOMAIN":
                return obj
    return None


def _find_emitter(entry):
    """Rename-safe: the emitter carries the FLUID FLOW modifier."""
    col = entry.root_collection
    if col is None:
        return None
    for obj in col.all_objects:
        for m in obj.modifiers:
            if m.type == "FLUID" and getattr(m, "fluid_type", "") == "FLOW":
                return obj
    return None


def blast_clamp(requested, dom, resolution, fps, ts_max, cfl, safety=0.8):
    longest = max(dom.dimensions) if dom else 8.0
    dx = longest / max(resolution, 1)
    v_max = safety * cfl * dx * fps * ts_max
    if requested <= v_max:
        return requested, None
    ts_needed = math.ceil(requested / (safety * cfl * dx * fps))
    return v_max, ts_needed


CLAMP_PROP = "aqs_clamp"   # (velocity, timesteps_needed) while clamped


def _set_clamp(entry, value):
    if value is None:
        if CLAMP_PROP in entry.keys():
            del entry[CLAMP_PROP]
    else:
        entry[CLAMP_PROP] = [float(value[0]), int(value[1])]


def clamp_state(entry):
    """(velocity, timesteps_needed) when the jet is being slowed, else None."""
    v = entry.get(CLAMP_PROP)
    return (float(v[0]), int(v[1])) if v else None


def _aim_direction(nozzle):
    """World-space jet direction: the nozzle empty's local -Z."""
    from mathutils import Vector
    return (nozzle.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def fit_domain(context, entry):
    """Shrink-wrap the domain to the jet's capsule sweep (TDD §8.1.2).

    An oversized domain wastes voxels on empty air — the #1 avoidable
    bake cost.  The box becomes the axis-aligned bounds of a capsule
    from the nozzle to nozzle + aim * Range, with a radius derived from
    the spread cone, plus padding for splash-back.
    """
    from mathutils import Vector
    nozzle = entry.primary
    dom = _find_domain(entry)
    if nozzle is None or dom is None:
        return
    rng = entry.hose_range
    p0 = nozzle.matrix_world.translation.copy()
    p1 = p0 + _aim_direction(nozzle) * rng
    radius = 0.25 + rng * math.tan(math.radians(max(entry.spread, 1.0)))
    pad = 0.3 + rng * 0.05  # splash-back margin

    mins = Vector((min(p0[i], p1[i]) - radius - pad for i in range(3)))
    maxs = Vector((max(p0[i], p1[i]) + radius + pad for i in range(3)))
    dom.location = (mins + maxs) * 0.5
    dom.scale = (maxs - mins)
    dom.rotation_euler = (0.0, 0.0, 0.0)


def apply_regime(context, entry, report=None):
    regime = entry.regime
    dom = _find_domain(entry)
    emitter = _find_emitter(entry)
    if emitter is None:
        return

    # Nozzle radius scales the emitter geometry (built at r = 0.03).
    emitter.scale = (entry.nozzle_radius / 0.03,) * 3

    mist_mod = next((m for m in emitter.modifiers
                     if m.type == "PARTICLE_SYSTEM"), None)
    flow_mod = next((m for m in emitter.modifiers if m.type == "FLUID"), None)
    dom_mod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
        if dom else None

    is_mist = regime == C.REGIME_MIST
    if mist_mod:
        mist_mod.show_viewport = is_mist
        mist_mod.show_render = is_mist
        # Pressure and spread drive the particle cone too.
        psys = next((p for p in emitter.particle_systems
                     if p.settings and C.OWNER_PROP in p.settings.keys()), None)
        if psys:
            ps = psys.settings
            ps.normal_factor = 2.5 * entry.pressure
            ps.factor_random = 0.3 + (entry.spread / 45.0) * 1.5
    for mod, obj in ((flow_mod, emitter), (dom_mod, dom)):
        if mod:
            mod.show_viewport = not is_mist
            mod.show_render = not is_mist
    if dom:
        dom.hide_render = is_mist

    if is_mist or flow_mod is None or dom_mod is None:
        _set_clamp(entry, None)
        return

    p = C.REGIME_PARAMS[regime]
    scene = context.scene
    fps = scene.render.fps / scene.render.fps_base

    # The entry's base_resolution is authoritative (regime switches seed
    # it; the panel presets/slider own it afterwards).  Draft halves it.
    base_res = entry.base_resolution if entry.base_resolution >= 16 \
        else p["resolution"]
    resolution = max(16, base_res // 2) if entry.draft else base_res
    secondaries = p["secondaries"] and not entry.draft

    requested = p["velocity"] * entry.pressure
    velocity, ts_needed = blast_clamp(requested, dom, resolution, fps,
                                      p["ts_max"], p["cfl"])
    # Slider update callbacks have no report(), so the clamp is also stored
    # on the entry and drawn by the panel — it can never apply silently.
    _set_clamp(entry, (velocity, ts_needed) if ts_needed else None)
    if ts_needed and report:
        report({"WARNING"}, "AQS-W018: " + C.MSG["W018"].format(
            v=velocity, ts=ts_needed))

    fs = flow_mod.flow_settings
    _safe(fs, "velocity_normal", velocity)
    _safe(fs, "use_initial_velocity", True)
    # Spread breaks the jet up: randomized emission velocity.
    _safe(fs, "velocity_random",
          velocity * (entry.spread / 45.0) * 0.6)

    ds = dom_mod.domain_settings
    ds.resolution_max = resolution
    if dom.display_type == "WIRE":       # heal older assemblies too
        dom.display_type = "TEXTURED"
    _safe(ds, "cfl_condition", p["cfl"])
    _safe(ds, "timesteps_min", p["ts_min"])
    _safe(ds, "timesteps_max", p["ts_max"])
    for flag in sw.SECONDARY_FLAGS:          # toggle-on-write: see set_flag
        sw.set_flag(ds, flag, secondaries)
    _safe(ds, "mesh_scale", 1 if entry.draft else 2)  # mesh upres cost
    if secondaries and report:
        report({"WARNING"}, "AQS-W015: " + C.MSG["W015"])


class AQS_OT_hose_fit_domain(bpy.types.Operator):
    bl_idname = "aquasuite.hose_fit_domain"
    bl_label = "Fit Domain to Nozzle"
    bl_description = ("Shrink-wrap the simulation domain around the jet's "
                      "current aim and Range — a tight domain bakes several "
                      "times faster than an oversized one. Re-run after "
                      "re-aiming the nozzle")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        fit_domain(context, entry)
        apply_regime(context, entry, report=self.report)
        self.report({"INFO"}, "Domain fitted to jet sweep")
        return {"FINISHED"}


class AQS_OT_hose_create(bpy.types.Operator):
    bl_idname = "aquasuite.hose_create"
    bl_label = "Create Water Hose"
    bl_description = ("A nozzle you can aim and keyframe, with four flow "
                      "regimes: Normal, Mist, Spray, Water Blast")
    bl_options = {"REGISTER", "UNDO"}

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_HOSE, uid)
        cursor = scene.cursor.location.copy()
        rng = 6.0  # Range (§8.1.4)

        nozzle = bpy.data.objects.new("AQS_Hose_Nozzle", None)
        nozzle.empty_display_type = "CONE"
        nozzle.empty_display_size = 0.15
        naming.tag(nozzle, C.MODE_HOSE, uid)
        naming.link_object(col, nozzle)
        nozzle.location = cursor + type(cursor)((0.0, 0.0, 1.5))
        nozzle.rotation_euler = (math.pi, 0.0, 0.0)  # aim -Z (down)

        # Single -Z-facing disc: a double-capped cylinder emits along BOTH
        # cap normals, spraying half the inflow backwards at the nozzle.
        emesh = bpy.data.meshes.new("AQS_Hose_Emitter")
        bm = bmesh.new()
        ret = bmesh.ops.create_circle(bm, cap_ends=True, segments=12,
                                      radius=0.03)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])  # normal -> -Z (aim)
        bm.to_mesh(emesh)
        bm.free()
        emitter = naming.new_mesh_object(col, "AQS_Hose_Emitter", emesh,
                                         C.MODE_HOSE, uid)
        emitter.parent = nozzle
        emitter.hide_render = True
        emitter.display_type = "WIRE"

        # Domain: a unit cube placed and sized by fit_domain() to the jet's
        # capsule sweep (refits on Range/Spread; Fit Domain after re-aiming).
        dmesh = bpy.data.meshes.new("AQS_Hose_Domain")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(dmesh)
        bm.free()
        dom = naming.new_mesh_object(col, "AQS_Hose_Domain", dmesh,
                                     C.MODE_HOSE, uid)
        # NOT wireframe: the baked liquid mesh IS the domain object's
        # display — WIRE would hide the water. Placed/sized by fit_domain.

        dom_mod = dom.modifiers.new("AQS Fluid", "FLUID")
        dom_mod.fluid_type = "DOMAIN"
        sw.setup_domain_settings(dom_mod, uid, 96)
        mats.assign(dom, mats.water_surface(C.MODE_HOSE, uid,
                                            name="AQS_MAT_HoseWater"))

        flow = emitter.modifiers.new("AQS Flow", "FLUID")
        flow.fluid_type = "FLOW"
        fs = flow.flow_settings
        fs.flow_type = "LIQUID"
        fs.flow_behavior = "INFLOW"
        _safe(fs, "use_plane_init", True)   # flat emitter geometry
        _safe(fs, "use_initial_velocity", True)
        _safe(fs, "velocity_normal", 6.0)

        # Mist backend (particles), pre-built and toggled by regime.
        pmod = emitter.modifiers.new("AQS_PS_HoseMist", "PARTICLE_SYSTEM")
        psys = emitter.particle_systems[-1]
        ps = psys.settings
        ps.name = "AQS_PS_HoseMist"
        naming.tag(ps, C.MODE_HOSE, uid)
        ps.count = 12000
        ps.frame_start = scene.frame_start
        ps.frame_end = scene.frame_end
        ps.lifetime = 90
        ps.emit_from = "FACE"
        ps.normal_factor = 2.5
        ps.factor_random = 0.8
        ps.effector_weights.gravity = 0.05
        ps.drag_factor = 0.9
        ps.render_type = "OBJECT"
        ps.particle_size = 1.0
        ps.size_random = 0.5
        ps.display_percentage = 100

        # Mist puff instance (R1.12: sphere, not billboard)
        puffmesh = bpy.data.meshes.new("AQS_Hose_MistPuff")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.004)
        bm.to_mesh(puffmesh)
        bm.free()
        puff = naming.new_mesh_object(col, "AQS_Hose_MistPuff", puffmesh,
                                      C.MODE_HOSE, uid)
        puff.hide_render = True
        mats.assign(puff, mats.mist(C.MODE_HOSE, uid))
        ps.instance_object = puff

        entry = registry.add(scene, C.MODE_HOSE, uid, primary=nozzle,
                             root_collection=col)
        entry.regime = C.REGIME_NORMAL
        entry["base_resolution"] = C.REGIME_PARAMS[C.REGIME_NORMAL]["resolution"]
        entry.hose_range = rng
        # Short default cache range: bake cost is linear in frames.
        _safe(dom_mod.domain_settings, "cache_frame_start", scene.frame_start)
        _safe(dom_mod.domain_settings, "cache_frame_end",
              min(scene.frame_start + 59, scene.frame_end))
        fit_domain(context, entry)
        apply_regime(context, entry, report=self.report)

        context.view_layer.objects.active = nozzle
        self.report({"INFO"},
                    "AquaSuite: Water Hose created — keyframe the nozzle; "
                    "liquid regimes require a bake")
        return {"FINISHED"}


class AQS_OT_hose_set_regime(bpy.types.Operator):
    bl_idname = "aquasuite.hose_set_regime"
    bl_label = "Set Hose Regime"
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()
    regime: bpy.props.EnumProperty(items=C.REGIME_ITEMS)

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        entry.regime = self.regime
        if self.regime in C.REGIME_PARAMS:
            # Seed the suggested resolution for this regime; the panel's
            # presets/slider own it from here on.
            entry["base_resolution"] = C.REGIME_PARAMS[self.regime]["resolution"]
        apply_regime(context, entry, report=self.report)
        return {"FINISHED"}


CLASSES = (AQS_OT_hose_create, AQS_OT_hose_set_regime,
           AQS_OT_hose_fit_domain)
