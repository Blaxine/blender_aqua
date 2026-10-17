# SPDX-License-Identifier: GPL-3.0-or-later
"""Rain Simulation — Mantaflow FLIP rain (Level 2).

Real simulated raindrops in a liquid domain: drops splash, crown, and
raise ripples in pool water because drops and pools are the SAME fluid
in one FLIP solve — no faked ripple layer.

Architecture:
  * Real raindrops (1-3 mm) are far smaller than any affordable voxel, so
    the FALL is thin rendered geometry and only the IMPACT is liquid.
  * The emitter is a plane with a Geometry Nodes "drop field": points
    scattered on the plane, each following the ballistic rain path (rain
    velocity + gravity) with a per-point random phase that wraps exactly
    when the drop reaches the water.  A child "drops" object renders that
    field at Drop Size.
  * The emitter itself runs the same field in Emit Only mode: it keeps
    only the drops in the frame before impact, at least ~1 voxel big, and
    a Fluid FLOW (mesh source, INFLOW, impact velocity) injects them —
    the FLIP solve only ever handles splashes, crowns and ripples, in a
    domain fitted to the water instead of the whole fall column.
  * Angle / Direction / Speed drive the drop velocity vector; Rain Area
    sizes the emitter plane and the fitted domain together.
  * A per-assembly Pool collection: user meshes added to it become
    liquid volumes under the SAME rules as Still Water (source hidden,
    never converted, restore records, R1.4 conflict policy).
  * Resolution presets / draft / bake are the shared liquid controls.

Memory pitfalls engineered around (the ones that take Blender down):
  1. Domain volume — fitted to the pools + impact footprint + splash
     headroom, never the fall column or a big generic box.
  2. One injection per drop — a moving flow mesh would otherwise stamp a
     new blob every frame (and underwater, multiplying FLIP particles).
  3. Live cell/RAM estimate in the panel, and a confirmation before
     bakes that would realistically exhaust memory.
"""

import math

import bpy
import bmesh
from mathutils import Vector

from .. import constants as C
from ..core import delete, naming, registry
from ..core import presets, whitewater
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


def find_rain_drops(entry):
    """The rendered rain: same drop field as the emitter, but no Fluid FLOW."""
    col = entry.root_collection
    if col is None:
        return None
    for obj in col.all_objects:
        if _drops_modifier(obj, entry.uuid) is None:
            continue
        if not any(m.type == "FLUID" for m in obj.modifiers):
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


def water_level(entry, default=0.0):
    """Height where rain meets water: the top of the highest pool mesh, or
    the world floor (z = 0) while there are no pools."""
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


# Emission radius in voxels.  Mantaflow does not register liquid flow
# meshes much smaller than a cell (3.5 cm drops in a ~10 cm grid emitted
# NOTHING; surface_distance does not inflate small closed meshes), so the
# emitter's copy of each drop is at least this big.
EMIT_MIN_VOXELS = 0.75


def _drop_tree(uid, droplet_mat):
    """Build the GN drop field shared by the rain-drops and emitter objects.

    Points are scattered on the emitter plane; each follows the ballistic
    rain path  p = v*dt + (0, 0, -g*dt^2/2)  with a per-point random phase
    that wraps every Fall Time (= the moment it reaches the water
    surface).  Drops are instanced as small streak spheres and REALIZED
    into real mesh.

    Emit Only (emitter object): keep just the drops whose age dt lies in
    [Emit Start, Emit Start + Emit Window).  With Emit Start = Fall Time -
    one frame, each drop is injected into the simulation ONCE, in the
    frame before it hits the water — the solver only ever sees impacts.
    Real raindrops (1-3 mm) are far below any affordable voxel size, so
    the FALL is rendered as thin geometry and only the SPLASH is liquid.
    (A flow mesh that moves every frame would otherwise stamp a new blob
    every frame — a trail of liquid per drop.)

    The plane's edges are kept (faces removed) so the emitter stays
    visible and selectable; loose edges emit no liquid.
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
            ("Gravity", "NodeSocketFloat", 9.81),
            ("Fall Time", "NodeSocketFloat", 0.4),
            ("Drop Size", "NodeSocketFloat", 0.0025),
            ("Seed", "NodeSocketInt", 0),
            ("Emit Only", "NodeSocketBool", False),
            ("Emit Start", "NodeSocketFloat", 0.0),
            ("Emit Window", "NodeSocketFloat", 1.0 / 24.0),
            ("Splash Fraction", "NodeSocketFloat", 1.0)):
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

    def m(op, a=None, b=None, v0=None, v1=None):
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

    # T = max(Fall Time, 1e-3); dt = fract(t/T + rand) * T  (time since spawn)
    T = m("MAXIMUM", a=gin.outputs["Fall Time"], v1=1e-3)
    tt = m("DIVIDE", a=time.outputs["Seconds"], b=T.outputs[0])
    ph = m("ADD", a=tt.outputs[0], b=rand.outputs[1])
    ph = m("FRACT", a=ph.outputs[0])
    dt = m("MULTIPLY", a=ph.outputs[0], b=T.outputs[0])

    ox = m("MULTIPLY", a=gin.outputs["Vx"], b=dt.outputs[0])
    oy = m("MULTIPLY", a=gin.outputs["Vy"], b=dt.outputs[0])
    vzt = m("MULTIPLY", a=gin.outputs["Vz"], b=dt.outputs[0])
    dt2 = m("MULTIPLY", a=dt.outputs[0], b=dt.outputs[0])
    half_g = m("MULTIPLY", a=gin.outputs["Gravity"], v1=0.5)
    drop = m("MULTIPLY", a=half_g.outputs[0], b=dt2.outputs[0])
    oz = m("SUBTRACT", a=vzt.outputs[0], b=drop.outputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(ox.outputs[0], comb.inputs["X"])
    nt.links.new(oy.outputs[0], comb.inputs["Y"])
    nt.links.new(oz.outputs[0], comb.inputs["Z"])

    setpos = nt.nodes.new("GeometryNodeSetPosition")
    nt.links.new(dist.outputs["Points"], setpos.inputs["Geometry"])
    nt.links.new(comb.outputs[0], setpos.inputs["Offset"])

    # Emit Only: delete drops whose age is outside
    # [Emit Start, Emit Start + Emit Window).
    early = nt.nodes.new("FunctionNodeCompare")
    early.data_type = "FLOAT"
    early.operation = "LESS_THAN"
    nt.links.new(dt.outputs[0], early.inputs[0])
    nt.links.new(gin.outputs["Emit Start"], early.inputs[1])
    w_end = m("ADD", a=gin.outputs["Emit Start"], b=gin.outputs["Emit Window"])
    late = nt.nodes.new("FunctionNodeCompare")
    late.data_type = "FLOAT"
    late.operation = "GREATER_EQUAL"
    nt.links.new(dt.outputs[0], late.inputs[0])
    nt.links.new(w_end.outputs[0], late.inputs[1])
    outside = nt.nodes.new("FunctionNodeBooleanMath")
    outside.operation = "OR"
    nt.links.new(early.outputs[0], outside.inputs[0])
    nt.links.new(late.outputs[0], outside.inputs[1])
    # Splash Fraction: only that share of drops is injected.  Each grid
    # blob carries far more water than a real raindrop, so injecting every
    # drop fills the domain.  An independent random value per point picks
    # the splashing drops (stable per drop: same seed + index each frame).
    seed2 = m("ADD", a=gin.outputs["Seed"], v1=7919.0)
    pick = nt.nodes.new("FunctionNodeRandomValue")
    pick.data_type = "FLOAT"
    nt.links.new(seed2.outputs[0], pick.inputs["Seed"])
    skip = nt.nodes.new("FunctionNodeCompare")
    skip.data_type = "FLOAT"
    skip.operation = "GREATER_EQUAL"
    nt.links.new(pick.outputs[1], skip.inputs[0])
    nt.links.new(gin.outputs["Splash Fraction"], skip.inputs[1])
    unwanted = nt.nodes.new("FunctionNodeBooleanMath")
    unwanted.operation = "OR"
    nt.links.new(outside.outputs[0], unwanted.inputs[0])
    nt.links.new(skip.outputs[0], unwanted.inputs[1])
    cull = nt.nodes.new("FunctionNodeBooleanMath")
    cull.operation = "AND"
    nt.links.new(gin.outputs["Emit Only"], cull.inputs[0])
    nt.links.new(unwanted.outputs[0], cull.inputs[1])
    keep = nt.nodes.new("GeometryNodeDeleteGeometry")
    keep.domain = "POINT"
    nt.links.new(setpos.outputs["Geometry"], keep.inputs["Geometry"])
    nt.links.new(cull.outputs[0], keep.inputs["Selection"])

    ico = nt.nodes.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Subdivisions"].default_value = 1
    nt.links.new(gin.outputs["Drop Size"], ico.inputs["Radius"])

    # Streak along the drop's CURRENT velocity (v - g*dt along Z): the
    # instance's local Z is aligned to it, then Scale Instances stretches
    # local Z.  Align Euler to Vector exists in 4.1 through 5.x.
    g_dt = m("MULTIPLY", a=gin.outputs["Gravity"], b=dt.outputs[0])
    vz_now = m("SUBTRACT", a=gin.outputs["Vz"], b=g_dt.outputs[0])
    vel = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(gin.outputs["Vx"], vel.inputs["X"])
    nt.links.new(gin.outputs["Vy"], vel.inputs["Y"])
    nt.links.new(vz_now.outputs[0], vel.inputs["Z"])
    align = nt.nodes.new("FunctionNodeAlignEulerToVector")
    align.axis = "Z"
    nt.links.new(vel.outputs[0], align.inputs["Vector"])

    inst = nt.nodes.new("GeometryNodeInstanceOnPoints")
    nt.links.new(keep.outputs["Geometry"], inst.inputs["Points"])
    nt.links.new(ico.outputs["Mesh"], inst.inputs["Instance"])
    nt.links.new(align.outputs[0], inst.inputs["Rotation"])

    scale = nt.nodes.new("GeometryNodeScaleInstances")
    # Streak shape.  The emitter's blobs keep it too: a round blob of
    # 0.75 cells is below what Mantaflow registers; the stretched one isn't.
    scale.inputs["Scale"].default_value = (1.0, 1.0, 1.9)
    nt.links.new(inst.outputs["Instances"], scale.inputs["Instances"])

    real = nt.nodes.new("GeometryNodeRealizeInstances")
    nt.links.new(scale.outputs["Instances"], real.inputs["Geometry"])

    setmat = nt.nodes.new("GeometryNodeSetMaterial")
    if droplet_mat is not None:
        setmat.inputs["Material"].default_value = droplet_mat
    nt.links.new(real.outputs["Geometry"], setmat.inputs["Geometry"])

    # Plane outline (edges only) so the emitter can be seen and selected.
    outline = nt.nodes.new("GeometryNodeDeleteGeometry")
    outline.domain = "FACE"
    outline.mode = "ONLY_FACE"
    nt.links.new(gin.outputs["Geometry"], outline.inputs["Geometry"])

    join = nt.nodes.new("GeometryNodeJoinGeometry")
    nt.links.new(outline.outputs["Geometry"], join.inputs["Geometry"])
    nt.links.new(setmat.outputs["Geometry"], join.inputs["Geometry"])
    nt.links.new(join.outputs["Geometry"], gout.inputs["Geometry"])

    for idx, node in enumerate(nt.nodes):
        node.location = ((idx % 10) * 200, -(idx // 10) * 220)
    return nt


def _fall_time(fall, vz_abs, g):
    """Seconds for a drop launched down at vz_abs (m/s) under gravity g to
    fall `fall` metres:  fall = vz*T + g*T^2/2."""
    vz_abs = max(vz_abs, 0.25)
    if g <= 1e-6:
        return fall / vz_abs
    return (-vz_abs + math.sqrt(vz_abs * vz_abs + 2.0 * g * fall)) / g


def _voxel_size(entry):
    dom = sw.find_domain_object(entry)
    dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
        if dom else None
    ds = getattr(dmod, "domain_settings", None)
    if ds is None or ds.resolution_max <= 0:
        return None
    return max(sw.object_dims(dom)) / ds.resolution_max


def emission_radius(entry):
    """Drop radius the EMITTER uses: the user's Drop Size, but never below
    EMIT_MIN_VOXELS cells — smaller drops are invisible to Mantaflow."""
    dx = _voxel_size(entry)
    size = entry.drop_size
    return size if dx is None else max(size, EMIT_MIN_VOXELS * dx)


def is_legacy_tree(mod):
    """Drop trees older than the current emitter (v0.16.0 and before:
    every drop injected as a stretched blob, filling the domain)."""
    return gn_io._socket_identifier(mod, "Splash Fraction") is None


def rain_timing(entry, scene):
    """(velocity at release, gravity, fall time to the water surface,
    velocity at impact) for the current emitter placement."""
    emitter = find_emitter(entry)
    v = rain_velocity(entry)
    g = max(-scene.gravity.z, 0.0) if scene.use_gravity else 0.0
    # Fresh transform: right after creation matrix_world is still identity
    # (the "rain only falls 0.5 m until you tweak something" bug).
    top = _world_matrix(emitter).translation.z if emitter else 4.0
    fall = max(top - water_level(entry), 0.5)
    t_fall = _fall_time(fall, abs(v.z), g)
    v_hit = Vector((v.x, v.y, v.z - g * t_fall))
    return v, g, t_fall, v_hit


def apply_rain_params(context, entry):
    """Rain settings -> both drop-field modifiers + flow velocity.

    Drops wrap exactly when they reach the water surface: the rendered
    drop disappears into the water in the same frame the emitter injects
    its liquid copy (with the impact velocity) for the splash.
    """
    emitter = find_emitter(entry)
    if emitter is None:
        return
    rain = find_rain_drops(entry)
    scene = context.scene if context is not None else bpy.context.scene
    v, g, t_fall, v_hit = rain_timing(entry, scene)
    fps = scene.render.fps / scene.render.fps_base
    window = 1.0 / max(fps, 1e-3)
    sca = _world_matrix(emitter).to_scale()
    # Density is per m^2 of the scaled plane; GN distributes in local space.
    density = entry.rain_density * abs(sca.x * sca.y)

    for obj, emit in ((emitter, True), (rain, False)):
        mod = _drops_modifier(obj, entry.uuid)
        if mod is None:
            continue
        legacy = is_legacy_tree(mod)
        gn_io.set_input(mod, "Vx", float(v.x))
        gn_io.set_input(mod, "Vy", float(v.y))
        gn_io.set_input(mod, "Vz", float(v.z))
        gn_io.set_input(mod, "Gravity", float(g))
        gn_io.set_input(mod, "Fall Time", float(t_fall))
        gn_io.set_input(mod, "Density", float(density))
        gn_io.set_input(mod, "Seed", int(entry.rain_seed))
        gn_io.set_input(mod, "Emit Only", bool(emit))
        # The frame before impact: the solver only ever sees splashes.
        gn_io.set_input(mod, "Emit Start", float(max(t_fall - window, 0.0)))
        gn_io.set_input(mod, "Emit Window", float(window))
        gn_io.set_input(mod, "Splash Fraction",
                        float(entry.splash_amount) if emit else 1.0)
        size = emission_radius(entry) if (emit and not legacy) \
            else entry.drop_size
        gn_io.set_input(mod, "Drop Size", float(size))

    fs = _flow_settings(emitter)
    if fs is not None:
        try:  # injected liquid hits the water at the real impact velocity
            fs.velocity_coord[0] = v_hit.x
            fs.velocity_coord[1] = v_hit.y
            fs.velocity_coord[2] = v_hit.z
        except (TypeError, IndexError, AttributeError) as exc:
            print(f"[AquaSuite] velocity_coord write skipped: {exc}")


def tune_drop_size(entry):
    """Resolution or domain size changed: re-derive the emission radius
    (>= EMIT_MIN_VOXELS cells) and keep a ~1 voxel emission layer."""
    dx = _voxel_size(entry)
    fs = _flow_settings(find_emitter(entry))
    if dx is not None and fs is not None:
        _safe(fs, "surface_distance", min(max(0.9 * dx, 0.01), 0.35))
    apply_rain_params(None, entry)


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
    whitewater.apply(entry)


SPLASH_HEADROOM = 0.6   # metres of air above the water for splash crowns


def fit_domain(context, entry):
    """Fit the domain to where the rain HITS the water (pitfall #1).

    The fall is rendered geometry, not liquid, so the domain no longer
    spans the fall column: it covers the pools plus the rain footprint at
    water level (shifted by the Angle/Direction drift), from the pool
    bottom to SPLASH_HEADROOM above the surface — tall enough that the
    drops injected one frame before impact start inside it.  Far fewer
    cells than a domain reaching up to the emitter.
    """
    dom = sw.find_domain_object(entry)
    emitter = find_emitter(entry)
    if dom is None or emitter is None:
        return
    scene = context.scene if context is not None else bpy.context.scene
    level = water_level(entry)
    v, _g, t_fall, v_hit = rain_timing(entry, scene)
    fps = scene.render.fps / scene.render.fps_base

    # Rain footprint where drops reach the water: the emitter's REAL world
    # footprint (respects manual move/scale/rotate) shifted by the drift.
    e_min, e_max = emitter_footprint(emitter)
    dx_, dy_ = v.x * t_fall, v.y * t_fall
    mins = Vector((e_min.x + dx_, e_min.y + dy_, level))
    maxs = Vector((e_max.x + dx_, e_max.y + dy_, level))

    bottom = None
    for p in entry.pool_sources:
        if p.obj is None:
            continue
        p_min, p_max = sw.world_bbox(p.obj)
        mins = Vector((min(mins[i], p_min[i]) for i in range(3)))
        maxs = Vector((max(maxs[i], p_max[i]) for i in range(3)))
        bottom = p_min.z if bottom is None else min(bottom, p_min.z)
    if bottom is None:
        bottom = level - 0.3  # no pool meshes: drops collect on the floor

    # One frame of impact travel (+ the drop itself) must fit above water.
    entry_height = 1.5 * abs(v_hit.z) / max(fps, 1e-3) + 0.1
    top = level + max(SPLASH_HEADROOM, entry_height + 0.2)

    pad = 0.15
    mins = Vector((mins.x - pad, mins.y - pad, bottom - pad))
    maxs = Vector((maxs.x + pad, maxs.y + pad, top))
    dom.location = (mins + maxs) * 0.5
    dom.scale = (maxs - mins)
    dom.rotation_euler = (0.0, 0.0, 0.0)
    tune_drop_size(entry)


def memory_estimate(dom, effective_res):
    """(million_cells, est_gb) for the current domain/resolution."""
    if dom is None or effective_res <= 0:
        return 0.0, 0.0
    dims = [max(d, 1e-3) for d in sw.object_dims(dom)]
    dx = max(dims) / effective_res
    cells = 1.0
    for d in dims:
        cells *= max(d / dx, 1.0)
    # FLIP liquid ≈ 100-150 bytes/cell incl. particles & aux grids.
    return cells / 1e6, cells * 120e-9


_world_matrix = sw.world_matrix


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
    # Resize the base plane, which is shared by the visible drops. Scaling
    # the object also scales GN velocity, streaks and splash blobs.
    for vertex in emitter.data.vertices:
        vertex.co.x *= entry.rain_area / size_x
        vertex.co.y *= entry.rain_area / size_y
    emitter.scale.x = 1.0
    emitter.scale.y = 1.0
    emitter.data.update()


def build_emitter(context, col, uid, area, location):
    """Build the rain rig from one plane you can move/scale/keyframe:

    * DROPS (child of the emitter, sharing its mesh): the full falling
      drop field at the user's Drop Size (real raindrops are 1-3 mm) —
      this is the rain you see and render.  Unselectable: move the
      emitter, the drops follow.
    * EMITTER (the plane): the same drop field in Emit Only mode + Fluid
      FLOW (mesh source, INFLOW).  Each drop is injected once, in the
      frame before it reaches the water, at least ~1 cell big and with
      its impact velocity — the solver only simulates splashes/ripples.
      Not rendered (the baked liquid is).

    INFLOW, not GEOMETRY: GEOMETRY fills liquid once, at the first
    simulated frame (what Still Water relies on).  Returns (emitter,
    drops).
    """
    emitter = rain_mod.make_plane("AQS_SimRain_Emitter", area,
                                  C.MODE_SIMRAIN, uid, col)
    emitter.location = location
    emitter.hide_render = True

    droplet_mat = mats.droplet(C.MODE_SIMRAIN, uid)
    nt = _drop_tree(uid, droplet_mat)
    mod = emitter.modifiers.new("AQS Rain Emit", "NODES")
    mod.node_group = nt

    flow = emitter.modifiers.new("AQS Flow", "FLUID")
    flow.fluid_type = "FLOW"
    fs = flow.flow_settings
    fs.flow_type = "LIQUID"
    fs.flow_behavior = "INFLOW"
    _safe(fs, "use_initial_velocity", True)
    # Velocity comes ONLY from velocity_coord: the emitted mesh changes
    # every frame, so "velocity from mesh motion" would pair unrelated
    # drops between frames and inject garbage velocities.
    _safe(fs, "velocity_factor", 0.0)
    _safe(fs, "velocity_normal", 0.0)

    drops = naming.new_mesh_object(col, "AQS_SimRain_Drops", emitter.data,
                                   C.MODE_SIMRAIN, uid)
    drops.parent = emitter
    drops.hide_select = True   # select/move the emitter; the drops follow
    dmod = drops.modifiers.new("AQS Rain Drops", "NODES")
    dmod.node_group = nt
    return emitter, drops


# ----------------------------------------------------------------------
# Operators
# ----------------------------------------------------------------------

class AQS_OT_rain_sim_create(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_create"
    bl_label = "Create Rain Simulation"
    bl_description = ("Real Mantaflow rain: drops splash and ripple in pool "
                      "water (opens a setup menu)")
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(name="Preset", items=presets.ITEMS[C.MODE_SIMRAIN],
                                   default='RAIN_RAIN')

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
        return self._build(context)

    def _build(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_SIMRAIN, uid)

        pool_col = bpy.data.collections.new(
            f"AQS_RainPool_{naming.short(uid)}")
        naming.tag(pool_col, C.MODE_SIMRAIN, uid)
        col.children.link(pool_col)

        # GN drop field: emitter (injects impacts) + rendered rain drops.
        frames = 60
        emitter, _drops = build_emitter(
            context, col, uid, self.area,
            scene.cursor.location + Vector((0, 0, self.height)))

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
        entry["rain_density"] = max(0.2, self.rate / max(self.area ** 2, 1.0))

        # Create parameters that are not in the preset (area/height/heading)
        # remain authored; speed and density come from the selected recipe.
        presets.apply(context, entry, self.preset)
        # Explicit Create/redo overrides remain useful for scripts and artists.
        # Untouched controls take their values from the selected preset.
        if self.properties.is_property_set('speed'):
            entry.rain_speed = self.speed
        if self.properties.is_property_set('rate'):
            entry.rain_density = max(0.2, self.rate / max(self.area ** 2, 1.0))

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
                    "Rain Simulation created — the drops render right away; "
                    "add pool meshes and Bake for the splashes and ripples")
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
        old = find_emitter(entry)
        old_loc = _world_matrix(old).translation.copy() if old else None
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

        # Keep the old emitter's placement (the domain now only covers the
        # water, so it no longer tells us where the rain starts).
        loc = old_loc if old_loc is not None else Vector(
            (0.0, 0.0, water_level(entry) + 4.0))
        emitter, _drops = build_emitter(
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
                    "Rain emitter rebuilt (drops + impact emitter) — "
                    "Free the old bake and re-bake")
        return {"FINISHED"}


class AQS_OT_rain_sim_check(bpy.types.Operator):
    bl_idname = "aquasuite.rain_sim_check"
    bl_label = "Check Pool Link"
    bl_description = ("Diagnose the drop-to-pool coupling chain and report "
                      "exactly what is broken")

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
        elif is_legacy_tree(mod):
            problems.append("emitter is from an older version (it doesn't "
                            "inject drops at impact) — click Rebuild "
                            "Emitter")
        lines.append(f"rain drops object: "
                     f"{'ok' if find_rain_drops(entry) else 'none'}")
        if mod is not None:
            lines.append(f"emission drop radius: "
                         f"{emission_radius(entry)*100:.1f} cm "
                         f"(visible {entry.drop_size*100:.1f} cm)")
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
            dx = max(sw.object_dims(dom)) / max(ds.resolution_max, 1)
            lines.append(f"resolution: {ds.resolution_max} | cell "
                         f"{dx*100:.1f} cm | emission thickness "
                         f"{getattr(fs, 'surface_distance', 0)*100:.1f} cm"
                         if fs else "")
            if emitter is not None:
                # The domain covers only the water: check that the point
                # where the rain lands (emitter centre + drift, at water
                # level) is inside it.
                v, _g, t_fall, _v_hit = rain_timing(entry, context.scene)
                e = _world_matrix(emitter).translation
                hit = Vector((e.x + v.x * t_fall, e.y + v.y * t_fall,
                              water_level(entry)))
                dmin, dmax = sw.world_bbox(dom)
                inside = all(dmin[i] - 1e-4 <= hit[i] <= dmax[i] + 1e-4
                             for i in range(3))
                lines.append(f"rain lands inside domain: "
                             f"{'yes' if inside else 'NO'}")
                if not inside:
                    problems.append("the rain lands outside the domain — "
                                    "click Fit Domain")
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
                        "Coupling chain OK — each drop is injected once "
                        "at spawn. Free + re-bake if you changed anything")
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
