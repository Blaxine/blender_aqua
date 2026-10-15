# SPDX-License-Identifier: GPL-3.0-or-later
"""Rain Simulation — Mantaflow FLIP rain (Level 2).

Real simulated raindrops in a liquid domain: drops splash, crown, and
raise ripples in pool water because drops and pools are the SAME fluid
in one FLIP solve — no faked ripple layer.

Architecture:
  * The emitter is a plane carrying a Geometry Nodes "drop field": points
    scattered on the plane, each moved along the rain velocity with a
    per-point random phase that wraps at Fall Distance, instanced as
    small streak spheres and REALIZED into real mesh.
  * A Fluid FLOW (mesh source, INFLOW behaviour) on the same plane stamps
    liquid wherever a drop is, every frame, with the rain velocity as
    initial velocity → falling droplets that splash.
  * Angle / Direction / Speed drive the drop velocity vector; Rain Area
    sizes the emitter plane and the fitted domain together.
  * A per-assembly Pool collection: user meshes added to it become
    liquid volumes under the SAME rules as Still Water (source hidden,
    never converted, restore records, R1.4 conflict policy).
  * Resolution presets / draft / bake are the shared liquid controls.

Memory pitfalls engineered around (the ones that take Blender down):
  1. Domain volume — fitted to the pools + fall column, never a big
     generic box; small default Area (4 m).
  2. Fall Distance — drops wrap back to the ceiling just past pool
     level, otherwise they keep stamping liquid UNDERWATER (invisible
     jets that churn the pool and multiply FLIP particle counts).
  3. Live cell/RAM estimate in the panel, and a confirmation before
     bakes that would realistically exhaust memory.
"""

import math

import bpy
import bmesh
from mathutils import Vector

from .. import constants as C
from ..core import delete, naming, registry
from ..materials import mats
from ..level1 import rain as rain_mod
from ..level1 import ocean as gn_io   # generic GN-modifier input get/set
from . import still_water as sw


def _safe(o, attr, value):
    if hasattr(o, attr):
        try:
            setattr(o, attr, value)
        except Exception as exc:
            print(f"[AquaSuite] could not set {attr}: {exc}")


# ----------------------------------------------------------------------
# Lookups (rename-safe: by modifier/data type, never by name)
# ----------------------------------------------------------------------

def _is_drop_tree(ng, assembly_uuid):
    """The drop-field tree is the only GN tree a Rain Sim assembly tags, so
    the owner tag identifies it — the user may rename it freely."""
    return ng is not None and naming.owned_by(ng, assembly_uuid)


def find_emitter(entry):
    """The rain emitter carries a GN drop-field modifier plus a Fluid
    FLOW; pool sources have no drop field."""
    col = entry.root_collection
    if col is None:
        return None
    for obj in col.all_objects:
        if _drops_modifier(obj, entry.uuid) is None:
            continue
        if any(m.type == "FLUID" and getattr(m, "fluid_type", "") == "FLOW"
               for m in obj.modifiers):
            return obj
    return None


def _drops_modifier(emitter, assembly_uuid):
    if emitter is None:
        return None
    for m in emitter.modifiers:
        if m.type == "NODES" and _is_drop_tree(m.node_group, assembly_uuid):
            return m
    return None


def _flow_settings(emitter):
    if emitter is None:
        return None
    for m in emitter.modifiers:
        if m.type == "FLUID" and getattr(m, "fluid_type", "") == "FLOW":
            return m.flow_settings
    return None


def _pool_top_z(entry, default=0.0):
    top = None
    for p in entry.pool_sources:
        if p.obj is None:
            continue
        _mins, maxs = sw.world_bbox(p.obj)
        top = maxs.z if top is None else max(top, maxs.z)
    return default if top is None else top


# ----------------------------------------------------------------------
# Parameter application
# ----------------------------------------------------------------------

def rain_velocity(entry):
    """Angle (tilt from vertical) + Direction (compass) + Speed -> vector."""
    ang = math.radians(entry.rain_angle)
    drn = math.radians(entry.rain_direction)
    s = entry.rain_speed
    return Vector((s * math.sin(ang) * math.cos(drn),
                   s * math.sin(ang) * math.sin(drn),
                   -s * math.cos(ang)))


def _drop_tree(uid, droplet_mat):
    """Build the GN drop field: points scattered on the emitter plane,
    each displaced along the rain velocity with a per-point random phase
    that wraps at Fall Distance — a steady-state field of falling drop
    spheres, REALIZED into actual mesh so Mantaflow samples it exactly
    like any animated obstacle or pool mesh (the mechanism proven to
    work).  Inputs: Density, Vx, Vy, Vz, Fall Distance, Drop Size, Seed.
    """
    nt = bpy.data.node_groups.new("AQS_GN_RainDrops", "GeometryNodeTree")
    naming.tag(nt, C.MODE_SIMRAIN, uid)
    nt.is_modifier = True
    iface = nt.interface
    iface.new_socket("Geometry", in_out="OUTPUT",
                     socket_type="NodeSocketGeometry")
    iface.new_socket("Geometry", in_out="INPUT",
                     socket_type="NodeSocketGeometry")
    for name, stype, default in (
            ("Density", "NodeSocketFloat", 6.0),
            ("Vx", "NodeSocketFloat", 0.0),
            ("Vy", "NodeSocketFloat", 0.0),
            ("Vz", "NodeSocketFloat", -9.0),
            ("Fall Distance", "NodeSocketFloat", 4.0),
            ("Drop Size", "NodeSocketFloat", 0.035),
            ("Seed", "NodeSocketInt", 0)):
        sock = iface.new_socket(name, in_out="INPUT", socket_type=stype)
        sock.default_value = default

    gin = nt.nodes.new("NodeGroupInput")
    gout = nt.nodes.new("NodeGroupOutput")

    dist = nt.nodes.new("GeometryNodeDistributePointsOnFaces")
    nt.links.new(gin.outputs["Geometry"], dist.inputs["Mesh"])
    nt.links.new(gin.outputs["Density"], dist.inputs["Density"])
    nt.links.new(gin.outputs["Seed"], dist.inputs["Seed"])

    rand = nt.nodes.new("FunctionNodeRandomValue")     # per-point phase
    rand.data_type = "FLOAT"
    nt.links.new(gin.outputs["Seed"], rand.inputs["Seed"])

    time = nt.nodes.new("GeometryNodeInputSceneTime")

    def math(op, a=None, b=None, v0=None, v1=None):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = op
        if v0 is not None:
            n.inputs[0].default_value = v0
        if v1 is not None:
            n.inputs[1].default_value = v1
        if a is not None:
            nt.links.new(a, n.inputs[0])
        if b is not None:
            nt.links.new(b, n.inputs[1])
        return n

    # T = FallDist / max(|Vz|, 0.25); phase = fract(t/T + rand)
    vz_abs = math("ABSOLUTE", a=gin.outputs["Vz"])
    vz_abs = math("MAXIMUM", a=vz_abs.outputs[0], v1=0.25)
    T = math("DIVIDE", a=gin.outputs["Fall Distance"], b=vz_abs.outputs[0])
    tt = math("DIVIDE", a=time.outputs["Seconds"], b=T.outputs[0])
    ph = math("ADD", a=tt.outputs[0], b=rand.outputs[1])
    ph = math("FRACT", a=ph.outputs[0])
    dt = math("MULTIPLY", a=ph.outputs[0], b=T.outputs[0])  # time since spawn

    ox = math("MULTIPLY", a=gin.outputs["Vx"], b=dt.outputs[0])
    oy = math("MULTIPLY", a=gin.outputs["Vy"], b=dt.outputs[0])
    oz = math("MULTIPLY", a=gin.outputs["Vz"], b=dt.outputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(ox.outputs[0], comb.inputs["X"])
    nt.links.new(oy.outputs[0], comb.inputs["Y"])
    nt.links.new(oz.outputs[0], comb.inputs["Z"])

    setpos = nt.nodes.new("GeometryNodeSetPosition")
    nt.links.new(dist.outputs["Points"], setpos.inputs["Geometry"])
    nt.links.new(comb.outputs[0], setpos.inputs["Offset"])

    ico = nt.nodes.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Subdivisions"].default_value = 1
    nt.links.new(gin.outputs["Drop Size"], ico.inputs["Radius"])

    inst = nt.nodes.new("GeometryNodeInstanceOnPoints")
    nt.links.new(setpos.outputs["Geometry"], inst.inputs["Points"])
    nt.links.new(ico.outputs["Mesh"], inst.inputs["Instance"])

    scale = nt.nodes.new("GeometryNodeScaleInstances")
    scale.inputs["Scale"].default_value = (1.0, 1.0, 1.9)  # streak shape
    nt.links.new(inst.outputs["Instances"], scale.inputs["Instances"])

    real = nt.nodes.new("GeometryNodeRealizeInstances")
    nt.links.new(scale.outputs["Instances"], real.inputs["Geometry"])

    setmat = nt.nodes.new("GeometryNodeSetMaterial")
    if droplet_mat is not None:
        setmat.inputs["Material"].default_value = droplet_mat
    nt.links.new(real.outputs["Geometry"], setmat.inputs["Geometry"])
    nt.links.new(setmat.outputs["Geometry"], gout.inputs["Geometry"])

    for idx, node in enumerate(nt.nodes):
        node.location = ((idx % 10) * 200, -(idx // 10) * 220)
    return nt


def apply_rain_params(context, entry):
    """Angle/Direction/Speed -> the GN drop field + flow velocity.

    Fall Distance auto-cuts drops just past pool level: the loop wraps
    them back to the ceiling, so nothing ever stamps liquid underwater.
    """
    emitter = find_emitter(entry)
    mod = _drops_modifier(emitter, entry.uuid)
    fs = _flow_settings(emitter)
    if emitter is None or mod is None:
        return
    v = rain_velocity(entry)
    gn_io.set_input(mod, "Vx", float(v.x))
    gn_io.set_input(mod, "Vy", float(v.y))
    gn_io.set_input(mod, "Vz", float(v.z))
    fall = max(emitter.matrix_world.translation.z
               - _pool_top_z(entry) + 0.15, 0.5)
    gn_io.set_input(mod, "Fall Distance", float(fall))
    if fs is not None:
        try:  # stamped liquid inherits the drop velocity
            fs.velocity_coord[0] = v.x
            fs.velocity_coord[1] = v.y
            fs.velocity_coord[2] = v.z
        except (TypeError, IndexError, AttributeError) as exc:
            print(f"[AquaSuite] velocity_coord write skipped: {exc}")


def tune_drop_size(entry):
    """Emission thickness >= ~1 voxel so small drops always register in
    the grid, while the VISIBLE sphere size stays exactly what the user
    chose (surface_distance inflates only the stamped liquid)."""
    dom = sw.find_domain_object(entry)
    dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
        if dom else None
    ds = getattr(dmod, "domain_settings", None)
    fs = _flow_settings(find_emitter(entry))
    if ds is None or fs is None or ds.resolution_max <= 0:
        return
    dx = max(dom.dimensions) / ds.resolution_max
    _safe(fs, "surface_distance", min(max(0.9 * dx, 0.01), 0.35))


def apply_quality(context, entry):
    """Shared liquid quality package (mirrors the hose: draft halves the
    resolution, drops mesh upres to 1x). Restored — was lost in the
    v0.13.0 refactor."""
    dom = sw.find_domain_object(entry)
    dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
        if dom else None
    ds = getattr(dmod, "domain_settings", None)
    if ds is None:
        return
    base = entry.base_resolution if entry.base_resolution >= 16 else 96
    ds.resolution_max = max(16, base // 2) if entry.draft else base
    _safe(ds, "mesh_scale", 1 if entry.draft else 2)
    if dom.display_type == "WIRE":       # heal older assemblies too
        dom.display_type = "TEXTURED"
    tune_drop_size(entry)


def fit_domain(context, entry):
    """Fit the domain to pools + rain fall column (pitfall #1).

    Bounds = union of pool AABBs, expanded by the rain area footprint
    (shifted by drift from Angle/Direction) up to the emitter plane,
    with modest padding.  Voxels never pay for air the rain can't reach.
    """
    dom = sw.find_domain_object(entry)
    emitter = find_emitter(entry)
    if dom is None or emitter is None:
        return
    e_loc = _world_matrix(emitter).translation
    # The emitter's REAL world footprint (respects manual move/scale/rotate),
    # not "location ± Rain Area / 2".
    mins, maxs = emitter_footprint(emitter)

    floor_z = None
    for p in entry.pool_sources:
        if p.obj is None:
            continue
        p_min, p_max = sw.world_bbox(p.obj)
        mins = Vector((min(mins[i], p_min[i]) for i in range(3)))
        maxs = Vector((max(maxs[i], p_max[i]) for i in range(3)))
        floor_z = p_min.z if floor_z is None else min(floor_z, p_min.z)
    if floor_z is None:
        floor_z = e_loc.z - 4.0  # no pools yet: default catch depth

    # Horizontal drift of angled rain over the fall height.
    fall = max(e_loc.z - floor_z, 0.5)
    v = rain_velocity(entry)
    vz = max(abs(v.z), 0.5)
    drift = Vector((v.x, v.y, 0.0)) * (fall / vz)
    for i in range(2):
        mins[i] = min(mins[i], mins[i] + drift[i])
        maxs[i] = max(maxs[i], maxs[i] + drift[i])

    pad = 0.25
    top = max(maxs.z, e_loc.z)
    mins = Vector((mins.x - pad, mins.y - pad, floor_z - pad))
    maxs = Vector((maxs.x + pad, maxs.y + pad, top + pad))
    dom.location = (mins + maxs) * 0.5
    dom.scale = (maxs - mins)
    dom.rotation_euler = (0.0, 0.0, 0.0)
    tune_drop_size(entry)


def memory_estimate(dom, effective_res):
    """(million_cells, est_gb) for the current domain/resolution."""
    if dom is None or effective_res <= 0:
        return 0.0, 0.0
    dims = [max(d, 1e-3) for d in dom.dimensions]
    dx = max(dims) / effective_res
    cells = 1.0
    for d in dims:
        cells *= max(d / dx, 1.0)
    # FLIP liquid ≈ 100-150 bytes/cell incl. particles & aux grids.
    return cells / 1e6, cells * 120e-9


def _world_matrix(obj):
    """World matrix from the object's CURRENT loc/rot/scale.

    obj.matrix_world is only refreshed by the next depsgraph update, so
    right after apply_area() rescales the emitter it still holds the old
    size; build the matrix from matrix_basis instead (parent-aware)."""
    mw = obj.matrix_basis.copy()
    if obj.parent is not None:
        mw = obj.parent.matrix_world @ obj.matrix_parent_inverse @ mw
    return mw


def emitter_footprint(emitter):
    """World-space (mins, maxs) of the emitter PLANE itself.

    Reads the base mesh, not bound_box: the evaluated bounds include the
    GN drop field hanging below the plane."""
    mw = _world_matrix(emitter)
    pts = [mw @ v.co for v in emitter.data.vertices]
    if not pts:
        loc = mw.translation
        return loc.copy(), loc.copy()
    mins = Vector((min(p[i] for p in pts) for i in range(3)))
    maxs = Vector((max(p[i] for p in pts) for i in range(3)))
    return mins, maxs


def apply_area(entry):
    """Rain Area -> the emitter plane's size, so the slider changes where
    rain actually falls (and fit_domain follows the real plane)."""
    emitter = find_emitter(entry)
    if emitter is None or not emitter.data.vertices:
        return
    xs = [v.co.x for v in emitter.data.vertices]
    ys = [v.co.y for v in emitter.data.vertices]
    size_x = max(max(xs) - min(xs), 1e-6)
    size_y = max(max(ys) - min(ys), 1e-6)
    emitter.scale.x = entry.rain_area / size_x
    emitter.scale.y = entry.rain_area / size_y


def build_emitter(context, col, uid, area, location, density=6.0):
    """Build the rain emitter: a plane you can move/scale, with a GN
    modifier generating a steady-state field of falling drop spheres
    (realized mesh), and a Fluid FLOW (MESH source — the SAME mechanism
    as pools and animated obstacles) so the drops physically splash into
    the domain.  Returns (emitter, gn_modifier).

    Flow behaviour is INFLOW: GEOMETRY only fills liquid once, at the
    first simulated frame (that is what Still Water relies on), so the
    rain would stop after frame 1.
    """
    emitter = rain_mod.make_plane("AQS_SimRain_Emitter", area,
                                  C.MODE_SIMRAIN, uid, col)
    emitter.location = location

    droplet_mat = mats.droplet(C.MODE_SIMRAIN, uid)
    nt = _drop_tree(uid, droplet_mat)
    mod = emitter.modifiers.new("AQS Rain Drops", "NODES")
    mod.node_group = nt
    gn_io.set_input(mod, "Density", density)

    flow = emitter.modifiers.new("AQS Flow", "FLUID")
    flow.fluid_type = "FLOW"
    fs = flow.flow_settings
    fs.flow_type = "LIQUID"
    fs.flow_behavior = "INFLOW"          # emit every frame (see docstring)
    _safe(fs, "use_initial_velocity", True)
    return emitter, mod


# ----------------------------------------------------------------------
# Operators
# ----------------------------------------------------------------------

class AQS_OT_rain_sim_create(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_create"
    bl_label = "Create Rain Simulation"
    bl_description = ("Real Mantaflow rain: drops splash and ripple in pool "
                      "water (opens a setup menu)")
    bl_options = {"REGISTER", "UNDO"}

    area: bpy.props.FloatProperty(
        name="Rain Area", default=4.0, min=1.0, max=30.0, subtype="DISTANCE",
        description="Edge length of the rained-on square. Memory scales "
                    "with area — keep it as tight as the shot allows")
    height: bpy.props.FloatProperty(
        name="Fall Height", default=4.0, min=1.0, max=20.0,
        subtype="DISTANCE", description="Emitter height above the origin")
    rate: bpy.props.IntProperty(
        name="Drops (approx)", default=100, min=1, max=2000,
        description="Approximate number of drops in the air at any moment")
    speed: bpy.props.FloatProperty(name="Speed", default=9.0, min=1.0,
                                   max=20.0, description="Drop speed (m/s)")
    angle: bpy.props.FloatProperty(
        name="Angle", default=0.0, min=0.0, max=60.0,
        description="Tilt from vertical (degrees) — wind-blown rain")
    direction: bpy.props.FloatProperty(
        name="Direction", default=0.0, min=0.0, max=360.0,
        description="Compass heading of the tilt (degrees)")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    @delete.guarded_create
    def execute(self, context):
        try:
            return self._build(context)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.report({"ERROR"},
                        f"Rain Sim creation failed: {exc} "
                        "(full traceback in the System Console)")
            return {"CANCELLED"}

    def _build(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_SIMRAIN, uid)

        pool_col = bpy.data.collections.new(
            f"AQS_RainPool_{naming.short(uid)}")
        naming.tag(pool_col, C.MODE_SIMRAIN, uid)
        col.children.link(pool_col)

        # GN drop-field emitter: drops are real mesh, sampled by the
        # fluid exactly like pools and animated obstacles (proven path).
        frames = 60
        emitter, _gnmod = build_emitter(
            context, col, uid, self.area,
            scene.cursor.location + Vector((0, 0, self.height)),
            density=max(0.2, self.rate / max(self.area ** 2, 1.0)))

        # Domain
        dmesh = bpy.data.meshes.new("AQS_SimRain_Domain")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(dmesh)
        bm.free()
        dom = naming.new_mesh_object(col, "AQS_SimRain_Domain", dmesh,
                                     C.MODE_SIMRAIN, uid)
        # NOT wireframe: the baked liquid mesh is drawn AS the domain
        # object — WIRE display makes the water invisible in the viewport.
        dom_mod = dom.modifiers.new("AQS Fluid", "FLUID")
        dom_mod.fluid_type = "DOMAIN"
        sw.setup_domain_settings(dom_mod, uid, 96)
        _safe(dom_mod.domain_settings, "cache_frame_start", scene.frame_start)
        _safe(dom_mod.domain_settings, "cache_frame_end",
              min(scene.frame_start + frames - 1, scene.frame_end))
        mats.assign(dom, mats.water_surface(C.MODE_SIMRAIN, uid,
                                            name="AQS_MAT_RainWater"))

        entry = registry.add(scene, C.MODE_SIMRAIN, uid, primary=dom,
                             root_collection=col)
        entry.pool_collection = pool_col
        entry["base_resolution"] = 96
        entry["rain_area"] = self.area
        entry["rain_speed"] = self.speed
        entry["rain_angle"] = self.angle
        entry["rain_direction"] = self.direction

        # Tail setup: each guarded so a single RNA quirk can't roll back
        # the whole creation (leaving no emitter behind).
        for step in (fit_domain, apply_rain_params, apply_quality):
            try:
                step(context, entry)
            except Exception as exc:
                print(f"[AquaSuite] rain-sim setup step {step.__name__} "
                      f"warning: {exc}")
        try:
            sw.add_effectors(scene, dom, uid, report=self.report)
        except Exception as exc:
            print(f"[AquaSuite] effector setup warning: {exc}")

        try:
            context.view_layer.objects.active = emitter
            emitter.select_set(True)
        except Exception:
            pass
        self.report({"INFO"},
                    "Rain Simulation created — rain is visible immediately "
                    "(scrub any frame). Add pool meshes and Bake to make "
                    "the drops splash into them")
        return {"FINISHED"}


class AQS_OT_rain_sim_add_pool(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_add_pool"
    bl_label = "Add Selected Mesh as Pool Water"
    bl_description = ("The active mesh's volume becomes pool water the rain "
                      "splashes into (same rules as Still Water: your object "
                      "is hidden, never converted, and restored on delete)")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == "MESH"
                and C.OWNER_PROP not in obj.keys()
                and C.SRC_PROP not in obj.keys())

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        src = context.active_object
        if entry is None:
            return {"CANCELLED"}
        if any(m.type == "FLUID" for m in src.modifiers):
            self.report({"ERROR"},
                        "AQS-W021: " + C.MSG["W021"].format(names=src.name))
            return {"CANCELLED"}
        if sw.mesh_has_open_edges(src):
            self.report({"WARNING"}, "AQS-W012: " + C.MSG["W012"])

        rec = entry.pool_sources.add()
        rec.obj = src
        rec.hide_render = src.hide_render
        rec.display_type = src.display_type

        flow = src.modifiers.new("AQS Flow", "FLUID")
        flow.fluid_type = "FLOW"
        fs = flow.flow_settings
        fs.flow_type = "LIQUID"
        fs.flow_behavior = "GEOMETRY"
        _safe(fs, "use_initial_velocity", False)

        src[C.SRC_PROP] = entry.uuid
        src.hide_render = True
        src.display_type = "WIRE"
        # Additional link into the pool collection (organizational only —
        # the object keeps all its original collection memberships).
        if entry.pool_collection is not None:
            try:
                entry.pool_collection.objects.link(src)
            except RuntimeError:
                pass

        fit_domain(context, entry)
        apply_quality(context, entry)
        self.report({"INFO"},
                    f"'{src.name}' is now pool water — re-bake to see rain "
                    "splash into it")
        return {"FINISHED"}


class AQS_OT_rain_sim_rebuild_emitter(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_rebuild_emitter"
    bl_label = "Rebuild Rain Emitter"
    bl_description = ("Delete this assembly's rain emitter (if any) and "
                      "rebuild it with the current drop-field design — "
                      "use this to repair a Rain Sim made with an older "
                      "version, no need to recreate the whole assembly")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None or entry.root_collection is None:
            return {"CANCELLED"}
        col = entry.root_collection
        dom = sw.find_domain_object(entry)
        pools = {rec.obj for rec in entry.pool_sources}
        # Remove the previous emitter rig (and any legacy seed emitters /
        # droplets).  Apart from the domain, everything this assembly owns
        # is emitter rig, so select by ownership — never by object name.
        # Pool sources are user objects (no owner tag) and are skipped too.
        doomed = set()
        for obj in list(col.all_objects):
            if naming.owned_by(obj, entry.uuid) and obj is not dom \
                    and obj not in pools:
                doomed.add(obj)
        for obj in doomed:
            bpy.data.objects.remove(obj, do_unlink=True)
        for ps in list(bpy.data.particles):
            v = ps.get(C.OWNER_PROP, "")
            if isinstance(v, str) and v.endswith(":" + entry.uuid):
                try:
                    bpy.data.particles.remove(ps)
                except Exception:
                    pass

        loc = context.scene.cursor.location + Vector((0, 0, 4.0))
        if dom is not None:
            loc = Vector((dom.location.x, dom.location.y,
                          dom.location.z + dom.dimensions.z * 0.5 - 0.15))
        emitter, _gnmod = build_emitter(
            context, col, entry.uuid, entry.rain_area, loc)
        for step in (fit_domain, apply_rain_params, apply_quality):
            try:
                step(context, entry)
            except Exception as exc:
                print(f"[AquaSuite] rebuild step {step.__name__}: {exc}")
        try:
            context.view_layer.objects.active = emitter
            emitter.select_set(True)
        except Exception:
            pass
        self.report({"INFO"},
                    "Rain emitter rebuilt (mesh drop field) — rain visible "
                    "on any frame; Free the old bake and re-bake for pool "
                    "splashes")
        return {"FINISHED"}


class AQS_OT_rain_sim_check(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_check"
    bl_label = "Check Pool Link"
    bl_description = ("Diagnose the drop-to-pool coupling chain and report "
                      "exactly what is broken (details in System Console)")

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        lines, problems = [], []

        emitter = find_emitter(entry)
        mod = _drops_modifier(emitter, entry.uuid)
        fs = _flow_settings(emitter)
        dom = sw.find_domain_object(entry)
        dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
            if dom else None
        ds = getattr(dmod, "domain_settings", None)

        lines.append(f"emitter: {emitter.name if emitter else 'MISSING'}")
        lines.append(f"drop field (GN): {'ok' if mod else 'MISSING'}")
        if mod is None:
            problems.append("GN drop field missing — click Rebuild Emitter")
        lines.append(f"flow modifier: {'ok' if fs else 'MISSING'}")
        if fs is not None:
            lines.append(f"behavior: {getattr(fs, 'flow_behavior', '?')} | "
                         f"type: {getattr(fs, 'flow_type', '?')} | "
                         f"source: mesh (evaluated GN geometry)")
            if getattr(fs, 'flow_behavior', '') != 'INFLOW':
                problems.append("flow behavior is not INFLOW (rain would "
                                "stop after the first frame) — click "
                                "Rebuild Emitter")
        else:
            problems.append("no Fluid Flow on the emitter")
        if ds is None:
            problems.append("no fluid domain")
        else:
            dx = max(dom.dimensions) / max(ds.resolution_max, 1)
            lines.append(f"resolution: {ds.resolution_max} | cell "
                         f"{dx*100:.1f} cm | emission thickness "
                         f"{getattr(fs, 'surface_distance', 0)*100:.1f} cm"
                         if fs else "")
            if emitter is not None:
                e = emitter.matrix_world.translation
                dmin, dmax = sw.world_bbox(dom)
                inside = all(dmin[i] - 1e-4 <= e[i] <= dmax[i] + 1e-4
                             for i in range(3))
                lines.append(f"emitter inside domain: "
                             f"{'yes' if inside else 'NO'}")
                if not inside:
                    problems.append("emitter outside the domain — click "
                                    "Fit Domain")
        if len(entry.pool_sources) == 0:
            lines.append("pools: none (drops collect on the domain floor)")
        if not bpy.data.filepath:
            problems.append("file not saved — bake cannot run")

        print("[AquaSuite] ---- Rain Sim coupling check ----")
        for ln in lines:
            if ln:
                print("[AquaSuite]", ln)
        if problems:
            print("[AquaSuite] PROBLEMS:", "; ".join(problems))
            self.report({"ERROR"}, "Problems: " + "; ".join(problems))
        else:
            self.report({"INFO"},
                        "Coupling chain OK — drops are real mesh geometry "
                        "emitting liquid every frame. Free + re-bake if "
                        "you changed anything")
        return {"FINISHED"}


class AQS_OT_rain_sim_fit_domain(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_fit_domain"
    bl_label = "Fit Domain"
    bl_description = ("Shrink-wrap the domain around the pools and the rain "
                      "fall column — the single biggest memory/speed saver. "
                      "Re-run after moving pools or the emitter")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        fit_domain(context, entry)
        apply_quality(context, entry)
        self.report({"INFO"}, "Domain fitted")
        return {"FINISHED"}


CLASSES = (AQS_OT_rain_sim_create, AQS_OT_rain_sim_add_pool,
           AQS_OT_rain_sim_rebuild_emitter, AQS_OT_rain_sim_check,
           AQS_OT_rain_sim_fit_domain)
