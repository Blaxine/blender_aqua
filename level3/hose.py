# SPDX-License-Identifier: GPL-3.0-or-later
"""Water Hose (TDD §8.1): one nozzle rig, four flow regimes.

Normal, Spray and Water Blast are real-time particle jets: thousands of
small droplets fired along the nozzle's aim, falling under gravity and
bouncing off the scene's Water Obstacles.  Mist is a real-time particle
fog.  "Simulate liquid" (Beta) swaps the jet for a Mantaflow liquid
simulation instead — pools and splashes, but baked and far thicker than a
real jet, since a grid can't resolve a centimetre-wide stream.

Regime switching toggles each backend's visibility and writes its
parameters — it never deletes the other backends (§8.1.3).  The liquid
velocity clamp follows the R1.9-corrected law:
v_max = S * CFL * dx * FPS * timesteps_max.
"""

import math

import bpy
import bmesh

from .. import constants as C
from ..core import delete, naming, registry
from ..core import presets, whitewater
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


ROLE_PROP = "aqs_role"     # "jet" / "mist" on the hose's particle settings


def _psys(emitter, role):
    """(particle system, its modifier) for the jet or the mist."""
    if emitter is None:
        return None, None
    systems = list(emitter.particle_systems)
    found = next((p for p in systems
                  if p.settings and p.settings.get(ROLE_PROP) == role), None)
    if found is None and role == "mist":
        # Hoses made before the jet existed have one, unlabelled, system.
        found = next((p for p in systems
                      if p.settings and ROLE_PROP not in p.settings.keys()), None)
    if found is None:
        return None, None
    mod = next((m for m in emitter.modifiers if m.type == "PARTICLE_SYSTEM"
                and m.particle_system == found), None)
    return found, mod


def _show(mod, visible):
    if mod is not None:
        mod.show_viewport = visible
        mod.show_render = visible


def _limit_collisions(scene, ps):
    """Jet and mist particles bounce only off the Water Obstacles."""
    from ..core import obstacles
    col = obstacles.collection(scene, create=True)
    _safe(ps, "collision_collection", col)


def _configure_jet(scene, entry, ps):
    p = C.JET_PARAMS[entry.regime]
    fps = scene.render.fps / scene.render.fps_base
    v = p["velocity"] * entry.pressure
    spread = math.tan(math.radians(entry.spread))
    ps.normal_factor = v
    ps.factor_random = v * (p["random"] + p["spread_gain"] * spread)
    ps.particle_size = p["size"]
    ps.size_random = p["size_random"]
    ps.lifetime = max(1, int(round(p["lifetime"] * fps)))
    ps.drag_factor = p["drag"]
    ps.frame_start = scene.frame_start
    ps.frame_end = scene.frame_end
    seconds = (scene.frame_end - scene.frame_start + 1) / max(fps, 1e-3)
    ps.count = max(1, min(int(p["rate"] * seconds), C.MAX_JET_PARTICLES))


def apply_color(entry):
    """Tint every hose material: jet droplets (glass), mist (translucent)
    and the simulated liquid (glass)."""
    col = entry.root_collection
    if col is None:
        return
    rgba = (*entry.hose_color, 1.0)
    seen = set()
    for obj in col.all_objects:
        for slot in getattr(obj, "material_slots", []):
            mat = slot.material
            if mat is None or mat.name in seen or not mat.use_nodes:
                continue
            seen.add(mat.name)
            for node in mat.node_tree.nodes:
                if node.type in ("BSDF_GLASS", "BSDF_TRANSLUCENT"):
                    sock = node.inputs.get("Color")
                    if sock is not None:
                        sock.default_value = rgba


def blast_clamp(requested, dom, resolution, fps, ts_max, cfl, safety=0.8):
    longest = max(sw.object_dims(dom)) if dom else 8.0
    dx = longest / max(resolution, 1)
    v_max = safety * cfl * dx * fps * ts_max
    if requested <= v_max:
        return requested, None
    ts_needed = math.ceil(requested / (safety * cfl * dx * fps))
    return v_max, ts_needed


CLAMP_PROP = "aqs_clamp"   # (velocity, timesteps_needed) while clamped
NOZZLE_MIN_VOXELS = 0.75   # smallest emitting nozzle radius, in grid cells


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
    """World-space jet direction: the nozzle empty's local -Z (from its
    current transform — matrix_world is stale right after creation)."""
    from mathutils import Vector
    return (sw.world_matrix(nozzle).to_3x3()
            @ Vector((0.0, 0.0, -1.0))).normalized()


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
    p0 = sw.world_matrix(nozzle).translation.copy()
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
    scene = context.scene
    dom = _find_domain(entry)
    emitter = _find_emitter(entry)
    if emitter is None:
        return

    is_mist = regime == C.REGIME_MIST
    liquid = entry.hose_liquid and not is_mist

    # Nozzle radius scales the emitter disc (built at r = 0.03); the
    # liquid path enlarges it below when the grid needs a bigger source.
    emitter.scale = (entry.nozzle_radius / 0.03,) * 3
    # Particles render only if their emitter does; the disc stays hidden
    # (heals hoses built when the emitter was hidden from renders).
    emitter.hide_render = False
    emitter.show_instancer_for_render = False

    jet, jet_mod = _psys(emitter, "jet")
    mist, mist_mod = _psys(emitter, "mist")
    flow_mod = next((m for m in emitter.modifiers if m.type == "FLUID"), None)
    dom_mod = next((m for m in dom.modifiers if m.type == "FLUID"), None)         if dom else None

    _show(mist_mod, is_mist)
    _show(jet_mod, not is_mist and not liquid)
    _show(flow_mod, liquid)
    _show(dom_mod, liquid)
    if dom:
        dom.hide_render = not liquid

    if mist is not None:
        ps = mist.settings
        ps.normal_factor = 2.5 * entry.pressure
        ps.factor_random = 0.3 + (entry.spread / 45.0) * 1.5
        _limit_collisions(scene, ps)
    if jet is not None:
        _limit_collisions(scene, jet.settings)
        if not is_mist:
            _configure_jet(scene, entry, jet.settings)

    if not liquid or flow_mod is None or dom_mod is None:
        _set_clamp(entry, None)
        return

    p = C.REGIME_PARAMS[regime]
    fps = scene.render.fps / scene.render.fps_base

    # The entry's base_resolution is authoritative (regime switches seed
    # it; the panel presets/slider own it afterwards).  Draft halves it.
    base_res = entry.base_resolution if entry.base_resolution >= 16 \
        else p["resolution"]
    resolution = max(16, base_res // 2) if entry.draft else base_res
    secondaries = p["secondaries"] and not entry.draft

    # Mantaflow ignores flow geometry much smaller than a grid cell (a 3 cm
    # nozzle in 9-19 cm cells emitted ~nothing): the EMITTING disc is never
    # below NOZZLE_MIN_VOXELS cells; Nozzle Radius keeps the user's value.
    dx = max(sw.object_dims(dom)) / max(resolution, 1)
    emit_radius = max(entry.nozzle_radius, NOZZLE_MIN_VOXELS * dx)
    emitter.scale = (emit_radius / 0.03,) * 3

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
    if entry.ww_managed:
        whitewater.apply(entry)
    else:
        # Preserve the behavior of old setups until explicitly adopted.
        for flag in sw.SECONDARY_FLAGS:
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
    bl_description = ("A nozzle you can aim and keyframe, with four "
                      "real-time flow regimes: Normal, Mist, Spray, Water "
                      "Blast")
    bl_options = {"REGISTER", "UNDO"}

    simulate_liquid: bpy.props.BoolProperty(name="Simulate Liquid (Beta)", default=False)
    preset: bpy.props.EnumProperty(name="Liquid Preset", items=presets.ITEMS[C.MODE_HOSE],
                                   default='HOSE_GARDEN')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, 'simulate_liquid')
        row = self.layout.row()
        row.enabled = self.simulate_liquid
        row.prop(self, 'preset')

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
        # Unrotated: the aim is the nozzle's local -Z, i.e. straight down.
        # (A 180-degree X rotation here turned the aim UP while the domain
        # was fitted downward.)
        nozzle.rotation_euler = (0.0, 0.0, 0.0)

        # Single -Z-facing disc: a double-capped cylinder emits along BOTH
        # cap normals, spraying half the inflow backwards at the nozzle.
        # Local -Z is the aim (see _aim_direction); emitter and nozzle
        # share that axis.
        emesh = bpy.data.meshes.new("AQS_Hose_Emitter")
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, segments=12, radius=0.03)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])  # normal -> local -Z
        bm.to_mesh(emesh)
        bm.free()
        emitter = naming.new_mesh_object(col, "AQS_Hose_Emitter", emesh,
                                         C.MODE_HOSE, uid)
        emitter.parent = nozzle
        emitter.display_type = "WIRE"
        # The disc itself never renders, but its particles must: hiding the
        # emitter from renders would hide the jet and mist too.
        emitter.show_instancer_for_render = False

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
        ps[ROLE_PROP] = "mist"
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

        # Jet backend (Normal / Spray / Blast): small droplets fired along
        # the aim, falling under gravity, bouncing off Water Obstacles.
        emitter.modifiers.new("AQS_PS_HoseJet", "PARTICLE_SYSTEM")
        jet = emitter.particle_systems[-1].settings
        jet.name = "AQS_PS_HoseJet"
        naming.tag(jet, C.MODE_HOSE, uid)
        jet[ROLE_PROP] = "jet"
        jet.emit_from = "FACE"
        _safe(jet, "distribution", "RAND")
        jet.effector_weights.gravity = 1.0
        jet.brownian_factor = 0.0
        jet.render_type = "OBJECT"
        jet.use_rotations = True
        _safe(jet, "rotation_mode", "VEL")     # streak (local X) along motion
        jet.use_dynamic_rotation = False
        _safe(jet, "use_die_on_collision", False)
        jet.display_percentage = 100
        dmesh_jet = bpy.data.meshes.new("AQS_Hose_Droplet")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=1.0)
        for v in bm.verts:
            v.co.x *= 1.8                      # short streak along local X
        bm.to_mesh(dmesh_jet)
        bm.free()
        droplet = naming.new_mesh_object(col, "AQS_Hose_Droplet", dmesh_jet,
                                         C.MODE_HOSE, uid)
        droplet.hide_render = True
        droplet.hide_set(True)
        mats.assign(droplet, mats.droplet(C.MODE_HOSE, uid))
        jet.instance_object = droplet

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
        apply_color(entry)
        if self.simulate_liquid:
            presets.apply(context, entry, self.preset)
        else:
            # Store the selected liquid recipe for explicit application later;
            # keep the default real-time hose path.
            whitewater.initialize(entry)
            entry.ww_managed = True
            entry.preset_choice = self.preset

        context.view_layer.objects.active = nozzle
        self.report({"INFO"},
                    "AquaSuite: Water Hose created — press Play; rotate or "
                    "keyframe the nozzle to aim it")
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
        whitewater.seed_regime(entry)
        apply_regime(context, entry, report=self.report)
        presets.note_edit(entry)
        return {"FINISHED"}


CLASSES = (AQS_OT_hose_create, AQS_OT_hose_set_regime,
           AQS_OT_hose_fit_domain)
