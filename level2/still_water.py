# SPDX-License-Identifier: GPL-3.0-or-later
"""Still Water — Object-to-Water (TDD §7.1).

The user's mesh becomes the initial liquid volume of a Mantaflow FLIP
sim.  The source is hidden (never converted, §7.1.3) and its prior state
recorded for restore.  Effectors follow the R1.4 refcount + conflict
policy.
"""


import bpy
import bmesh
from mathutils import Vector

from .. import constants as C
from ..core import delete, naming, registry
from ..core import presets, whitewater
from ..materials import mats

RES_PRESETS = {"PREVIEW": 48, "MEDIUM": 96, "HIGH": 160, "ULTRA": 256}


def _safe(o, attr, value):
    if hasattr(o, attr):
        try:
            setattr(o, attr, value)
        except Exception as exc:
            print(f"[AquaSuite] could not set {attr}: {exc}")


def set_flag(o, attr, value):
    """Write a bool only when it differs from the current value.

    Blender's secondary-particle switches (use_spray/foam/bubble_particles)
    TOGGLE on every write, whatever value is written: writing False to an
    off flag turns it ON (verified on 4.1 and 5.1).  Never write them
    directly — always go through this helper.
    """
    if hasattr(o, attr) and bool(getattr(o, attr)) != bool(value):
        _safe(o, attr, value)


SECONDARY_FLAGS = ("use_spray_particles", "use_foam_particles",
                   "use_bubble_particles")


def world_matrix(obj):
    """World matrix from the object's CURRENT loc/rot/scale.

    obj.matrix_world is only refreshed by the next depsgraph update, so
    right after an operator moves/rescales an object (or creates it) it
    still holds the old transform; build it from matrix_basis instead
    (parent-aware)."""
    mw = obj.matrix_basis.copy()
    if obj.parent is not None:
        mw = world_matrix(obj.parent) @ obj.matrix_parent_inverse @ mw
    return mw


def object_dims(obj):
    """Size of a (domain) object from its CURRENT scale and BASE mesh.

    obj.dimensions comes from the evaluated bounding box: it is stale
    (often zero) until the next depsgraph update — e.g. right after a
    domain is created or refitted in the same operator — and once baked
    it measures the liquid, not the domain.  Domains are unrotated boxes,
    so scale x mesh extent is exact.
    """
    me = getattr(obj, "data", None)
    verts = getattr(me, "vertices", None)
    if not verts:
        return Vector(obj.dimensions)
    sca = obj.matrix_basis.to_scale()
    return Vector((abs(sca[i]) * (max(v.co[i] for v in verts)
                                  - min(v.co[i] for v in verts))
                   for i in range(3)))


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mins = Vector((min(c[i] for c in corners) for i in range(3)))
    maxs = Vector((max(c[i] for c in corners) for i in range(3)))
    return mins, maxs


def _bbox_intersect(a_min, a_max, b_min, b_max):
    return all(a_min[i] <= b_max[i] and b_min[i] <= a_max[i] for i in range(3))


def domain_box(mins, maxs, pad_xy=1.5, pad_up=1.2, pad_dn=2.5):
    """(location, scale) of a unit-cube domain padded around a bbox."""
    size = maxs - mins
    center = (maxs + mins) * 0.5
    half = Vector((max(size.x, 0.1) * 0.5 * pad_xy,
                   max(size.y, 0.1) * 0.5 * pad_xy, 0.0))
    top = maxs.z + max(size.z, 0.1) * (pad_up - 1.0)
    bottom = mins.z - max(size.z, 0.1) * (pad_dn - 1.0)
    return (Vector((center.x, center.y, (top + bottom) * 0.5)),
            Vector((half.x * 2.0, half.y * 2.0, (top - bottom))))


def make_domain(name, mode, uid, col, mins, maxs,
                pad_xy=1.5, pad_up=1.2, pad_dn=2.5):
    location, scale = domain_box(mins, maxs, pad_xy, pad_up, pad_dn)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    dom = naming.new_mesh_object(col, name, mesh, mode, uid)
    dom.location = location
    dom.scale = scale
    return dom


def setup_domain_settings(dom_mod, uid, resolution, cfl=4.0,
                          ts_min=1, ts_max=4, secondaries=False):
    ds = dom_mod.domain_settings
    ds.domain_type = "LIQUID"
    ds.resolution_max = resolution
    _safe(ds, "use_mesh", True)
    _safe(ds, "cfl_condition", cfl)
    _safe(ds, "timesteps_min", ts_min)
    _safe(ds, "timesteps_max", ts_max)
    for flag in SECONDARY_FLAGS:
        set_flag(ds, flag, secondaries)
    _safe(ds, "cache_type", "MODULAR")
    _safe(ds, "cache_data_format", "OPENVDB")
    ds.cache_directory = f"//aquasuite_cache/{uid}"
    return ds


def add_effectors(scene, domain, uid, report=None):
    """Obstacles come from the scene's Water Obstacles collection only
    (core/obstacles.py): bring them in line with it."""
    from ..core import obstacles
    obstacles.sync(scene)


def refresh_obstacles(scene, entry, report=None):
    """Runs before every bake: objects added to Water Obstacles since the
    setup was created become obstacles, and effector thickness follows
    this domain's voxel size.  Returns the number of obstacles."""
    from ..core import obstacles
    return obstacles.sync(scene)


def mesh_has_open_edges(obj):
    me = obj.data
    edge_users = {}
    for poly in me.polygons:
        for ek in poly.edge_keys:
            edge_users[ek] = edge_users.get(ek, 0) + 1
    return any(n < 2 for n in edge_users.values())


# --------------------------------------------------------------------------
# Water meshes.  The active mesh at creation is entry.source; meshes added
# with Add Mesh to Water are pool_sources records (the same restore record
# Rain Sim keeps for its pools).  core/delete.py restores both, so old
# single-mesh setups need nothing new.
# --------------------------------------------------------------------------

def water_sources(entry):
    """Every user mesh this setup takes water from (missing ones skipped)."""
    objs = [entry.source] if entry.source is not None else []
    return objs + [rec.obj for rec in entry.pool_sources if rec.obj is not None]


def _is_flow(obj):
    return any(m.type == "FLUID" and getattr(m, "fluid_type", "") == "FLOW"
               for m in obj.modifiers)


def flow_objects(entry):
    """What may pour liquid into this setup's domain: its listed water
    meshes and the Fluid FLOW objects it made (emitters, fill boxes)."""
    objs = water_sources(entry)
    if entry.root_collection is not None:
        objs += [o for o in entry.root_collection.all_objects
                 if naming.owned_by(o, entry.uuid) and _is_flow(o)
                 and o not in objs]
    return objs


def sync_flows(entry):
    """Point the domain at a Flow collection holding only this setup's
    flows.  Without one, Mantaflow takes every Fluid FLOW object in the
    scene that lies inside the domain: other setups' water meshes and
    emitters, and the user's own Fluid flows.  Runs whenever the flows
    change and before every bake (which also mends setups from older
    files).  Returns the collection."""
    dom = find_domain_object(entry)
    mod = next((m for m in dom.modifiers if m.type == "FLUID"
                and m.fluid_type == "DOMAIN"), None) if dom else None
    if mod is None or entry.root_collection is None:
        return None
    col = entry.flow_collection
    if col is None:
        col = bpy.data.collections.new(f"AQS_Flows_{naming.short(entry.uuid)}")
        naming.tag(col, entry.mode, entry.uuid)
        entry.flow_collection = col
    if col.name not in entry.root_collection.children:
        # Linked into the scene: an unlinked collection is lost on save.
        entry.root_collection.children.link(col)
    want = flow_objects(entry)
    for obj in list(col.objects):
        if obj not in want:
            col.objects.unlink(obj)
    for obj in want:
        if obj.name not in col.objects:
            col.objects.link(obj)
    ds = mod.domain_settings
    if ds.fluid_group != col:
        ds.fluid_group = col
    return col


def source_problem(obj):
    """Why a mesh can't become water, or '' when it can.  Open meshes can:
    AQS-W012 only warns."""
    if obj.type != "MESH":
        return "not a mesh"
    if C.OWNER_PROP in obj.keys():
        return "made by AquaSuite"
    if C.SRC_PROP in obj.keys():
        return "already water"
    from ..core import floating, obstacles
    if floating.is_member(obj):
        return "it is a Floating Object"
    if obstacles.is_member(obj):
        return "it is a Water Obstacle"
    # R1.4: never touch a user-owned Fluid setup.
    if any(m.type == "FLUID" for m in obj.modifiers):
        return "W021"
    return ""


def make_source(obj, uid):
    """One-shot GEOMETRY liquid flow (§7.1.2 step 3) and the source
    visibility policy (step 4).  Record hide_render and display_type
    first."""
    flow = obj.modifiers.new("AQS Flow", "FLUID")
    flow.fluid_type = "FLOW"
    fs = flow.flow_settings
    fs.flow_type = "LIQUID"
    fs.flow_behavior = "GEOMETRY"
    _safe(fs, "use_initial_velocity", False)
    obj.hide_render = True
    obj.display_type = "WIRE"
    # Dedicated source marker — deliberately NOT the owner tag, so the
    # delete sweep can never remove a user object (even if the registry
    # entry is lost in an old file).
    obj[C.SRC_PROP] = uid


def add_sources(entry, objs):
    """Make the eligible meshes extra water.  Returns (added, skipped),
    skipped as [(obj, reason)]."""
    added, skipped = [], []
    for obj in objs:
        why = source_problem(obj)
        if why:
            skipped.append((obj, why))
            continue
        rec = entry.pool_sources.add()
        rec.obj = obj
        rec.hide_render = obj.hide_render
        rec.display_type = obj.display_type
        make_source(obj, entry.uuid)
        added.append(obj)
    return added, skipped


def report_sources(op, skipped, leaky):
    """Say which meshes were left out and which may leak."""
    fluid = [o.name for o, why in skipped if why == "W021"]
    other = [f"{o.name} ({why})" for o, why in skipped if why != "W021"]
    if fluid:
        op.report({"WARNING"},
                  "AQS-W021: " + C.MSG["W021"].format(names=", ".join(fluid)))
    if other:
        op.report({"WARNING"}, "Not turned into water: " + ", ".join(other))
    leaky = [o.name for o in leaky if mesh_has_open_edges(o)]
    if leaky:
        op.report({"WARNING"}, "AQS-W012: " + C.MSG["W012"]
                  + f" ({', '.join(leaky)})")


def selected_meshes(context):
    objs = list(context.selected_objects) or (
        [context.active_object] if context.active_object else [])
    return [o for o in objs if o.type == "MESH"]


def sources_bbox(objs):
    boxes = [world_bbox(o) for o in objs]
    return (Vector((min(b[0][i] for b in boxes) for i in range(3))),
            Vector((max(b[1][i] for b in boxes) for i in range(3))))


def domain_bounds(dom):
    """World bbox of the domain box.  From the base mesh: once baked, the
    evaluated mesh (and bound_box) is the liquid."""
    mw = world_matrix(dom)
    pts = [mw @ v.co for v in dom.data.vertices]
    return (Vector((min(p[i] for p in pts) for i in range(3))),
            Vector((max(p[i] for p in pts) for i in range(3))))


def _fitted_bounds(objs):
    """The domain Turn Into Water makes around these meshes."""
    loc, sca = domain_box(*sources_bbox(objs))
    return loc - sca * 0.5, loc + sca * 0.5


def _set_domain_bounds(dom, lo, hi):
    verts = dom.data.vertices
    lmin = Vector((min(v.co[i] for v in verts) for i in range(3)))
    lmax = Vector((max(v.co[i] for v in verts) for i in range(3)))
    sca = Vector((max(hi[i] - lo[i], 1e-4) / max(lmax[i] - lmin[i], 1e-6)
                  for i in range(3)))
    dom.rotation_euler = (0.0, 0.0, 0.0)
    dom.scale = sca
    dom.location = (lo + hi) * 0.5 - Vector(
        (sca[i] * (lmin[i] + lmax[i]) * 0.5 for i in range(3)))


def _same_bounds(a, b):
    tol = 1e-4 * max(1.0, max(a[1][i] - a[0][i] for i in range(3)))
    return all(abs(a[k][i] - b[k][i]) <= tol for k in range(2) for i in range(3))


def grow_domain(entry):
    """Grow the domain to hold every water mesh with the creation padding.
    Never shrinks it, so a domain the user enlarged keeps its size.  True
    when it changed."""
    dom = find_domain_object(entry)
    objs = water_sources(entry)
    if dom is None or not objs:
        return False
    want = _fitted_bounds(objs)
    cur = domain_bounds(dom)
    new = (Vector((min(want[0][i], cur[0][i]) for i in range(3))),
           Vector((max(want[1][i], cur[1][i]) for i in range(3))))
    if _same_bounds(new, cur):
        return False
    _set_domain_bounds(dom, *new)
    return True


def mark_sources_changed(entry):
    """A bake made before the water meshes changed no longer matches them."""
    from ..core import bakes
    if bakes.has_bake(entry):
        entry.sources_changed = True


def remove_source(context, entry, obj):
    """Give one water mesh back exactly as it was: Flow modifier, render
    visibility, display type, source tag and pool-collection link.
    Returns '' or why it can't."""
    objs = water_sources(entry)
    if obj is None or obj not in objs:
        return "That mesh isn't water in this setup"
    if len(objs) == 1 and entry.mode == C.MODE_STILL:
        return ("Still Water needs at least one water mesh — Delete removes "
                "the whole setup")
    dom = find_domain_object(entry)
    # Refit only a domain still at its automatic size; keep one the user
    # resized.
    refit = (entry.mode == C.MODE_STILL and dom is not None
             and _same_bounds(_fitted_bounds(objs), domain_bounds(dom)))
    if obj == entry.source:
        delete._restore_one_source(obj, entry.uuid, entry.src_hide_render,
                                   entry.src_display_type)
        # The next mesh takes its place as the setup's main source.
        i = next(i for i, rec in enumerate(entry.pool_sources)
                 if rec.obj is not None)
        rec = entry.pool_sources[i]
        entry.source = rec.obj
        entry.src_hide_render = rec.hide_render
        entry.src_display_type = rec.display_type
        entry.pool_sources.remove(i)
    else:
        i = next(i for i, rec in enumerate(entry.pool_sources)
                 if rec.obj == obj)
        rec = entry.pool_sources[i]
        delete._restore_one_source(obj, entry.uuid, rec.hide_render,
                                   rec.display_type)
        col = entry.pool_collection
        if col is not None and obj.name in col.objects:
            col.objects.unlink(obj)
        entry.pool_sources.remove(i)
    if refit:
        _set_domain_bounds(dom, *_fitted_bounds(water_sources(entry)))
    elif entry.mode == C.MODE_SIMRAIN:
        from . import rain_sim
        rain_sim.fit_domain(context, entry)
        rain_sim.apply_quality(context, entry)
    sync_flows(entry)
    mark_sources_changed(entry)
    return ""


class AQS_OT_still_water_add_source(bpy.types.Operator):
    bl_idname = "aquasuite.still_water_add_source"
    bl_label = "Add Mesh to Water"
    bl_description = ("The selected meshes' volumes become more water in "
                      "this setup's simulation (hidden, never converted, "
                      "restored on delete). Only listed meshes become water. "
                      "The domain grows to hold them; re-bake")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return bool(selected_meshes(context))

    def execute(self, context):
        from ..core import bakes
        entry = registry.get(context.scene, self.uuid)
        if entry is None or entry.mode != C.MODE_STILL:
            return {"CANCELLED"}
        if bakes.is_baking(entry):
            self.report({"ERROR"}, "Stop the bake before changing the water meshes")
            return {"CANCELLED"}
        added, skipped = add_sources(entry, selected_meshes(context))
        report_sources(self, skipped, added)
        if not added:
            if not skipped:
                self.report({"INFO"}, "Select the meshes to turn into water first")
            return {"CANCELLED"}
        grow_domain(entry)
        sync_flows(entry)
        mark_sources_changed(entry)
        self.report({"INFO"},
                    f"{len(added)} water mesh(es) added — "
                    + ("Bake Again to include them" if bakes.has_bake(entry)
                       else "bake required"))
        return {"FINISHED"}


class AQS_OT_water_source_remove(bpy.types.Operator):
    bl_idname = "aquasuite.water_source_remove"
    bl_label = "Remove Water Mesh"
    bl_description = ("This mesh stops being water and is given back exactly "
                      "as it was")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()
    name: bpy.props.StringProperty()

    def execute(self, context):
        from ..core import bakes
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        if bakes.is_baking(entry):
            self.report({"ERROR"}, "Stop the bake before changing the water meshes")
            return {"CANCELLED"}
        why = remove_source(context, entry, bpy.data.objects.get(self.name))
        if why:
            self.report({"ERROR"}, why)
            return {"CANCELLED"}
        self.report({"INFO"}, f"'{self.name}' is no longer water")
        return {"FINISHED"}


class AQS_OT_still_water_create(bpy.types.Operator):
    bl_idname = "aquasuite.still_water_create"
    bl_label = "Turn Into Water"
    bl_description = ("The active mesh's volume becomes actual liquid "
                      "(Mantaflow FLIP — baking is mandatory). Add Mesh to "
                      "Water adds more meshes to the same simulation")
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(name="Preset", items=presets.ITEMS[C.MODE_STILL],
                                   default='STILL_CALM')

    def invoke(self, context, event):
        return self.execute(context)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" \
            and C.OWNER_PROP not in obj.keys() \
            and C.SRC_PROP not in obj.keys()

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        src = context.active_object
        # R1.4 conflict policy: one Fluid modifier per object; never touch
        # a user-owned Fluid setup.
        if any(m.type == "FLUID" for m in src.modifiers):
            self.report({"ERROR"},
                        "This object already has a Fluid modifier — AquaSuite "
                        "won't modify existing Fluid setups (AQS-W021).")
            return {"CANCELLED"}
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_STILL, uid)

        if mesh_has_open_edges(src):
            self.report({"WARNING"}, "AQS-W012: " + C.MSG["W012"])

        mins, maxs = world_bbox(src)
        dom = make_domain("AQS_Still_Domain", C.MODE_STILL, uid, col,
                          mins, maxs)
        dom_mod = dom.modifiers.new("AQS Fluid", "FLUID")
        dom_mod.fluid_type = "DOMAIN"
        setup_domain_settings(dom_mod, uid, RES_PRESETS["MEDIUM"])
        # Short default cache range: bake cost is linear in frames.
        _safe(dom_mod.domain_settings, "cache_frame_start", scene.frame_start)
        _safe(dom_mod.domain_settings, "cache_frame_end",
              min(scene.frame_start + 59, scene.frame_end))
        mats.assign(dom, mats.water_surface(C.MODE_STILL, uid,
                                            name="AQS_MAT_WaterVolume"))

        # Restore records, then the Flow and visibility policy
        # (§7.1.2 steps 3-4).
        entry = registry.add(scene, C.MODE_STILL, uid, primary=dom,
                             root_collection=col)
        entry["base_resolution"] = RES_PRESETS["MEDIUM"]
        entry.source = src
        entry.src_hide_render = src.hide_render
        entry.src_display_type = src.display_type
        make_source(src, uid)
        sync_flows(entry)

        add_effectors(scene, dom, uid, report=self.report)
        presets.apply(context, entry, self.preset)

        context.view_layer.objects.active = dom
        self.report({"INFO"},
                    "AquaSuite: Still Water created — bake required (amber banner)")
        return {"FINISHED"}


def find_domain_object(entry):
    """Locate the assembly's Fluid DOMAIN object.

    The primary object is the domain for Still Water but the *nozzle
    empty* for the Hose — so never assume; scan the assembly collection
    for the object actually carrying a Fluid modifier of type DOMAIN.
    """
    candidates = []
    if entry is None:
        return None
    if entry.primary is not None:
        candidates.append(entry.primary)
    if entry.root_collection is not None:
        candidates.extend(entry.root_collection.all_objects)
    for obj in candidates:
        for mod in obj.modifiers:
            if mod.type == "FLUID" and getattr(mod, "fluid_type", "") == "DOMAIN":
                return obj
    return None


import contextlib
import os
import shutil
import sys

MEMORY_CONFIRM_GB = 2.0
# Windows refuses paths of 260 characters or more.  Mantaflow then skips the
# file without an error: Bake All "completes", the shorter data files are
# all there, and the liquid mesh or whitewater is simply missing (measured
# on Blender 4.5: mesh paths of 257 characters written, 260-262 not).
WINDOWS_PATH_LIMIT = 260
_CACHE_EXT = {"OPENVDB": ".vdb", "UNI": ".uni", "RAW": ".raw",
              "BOBJECT": ".bobj.gz", "OBJECT": ".obj"}


def longest_cache_path(ds):
    """The longest file path this domain's bake will write (Mantaflow's
    modular cache names: <dir>/fluid_<dir>_<frame>.<ext>)."""
    root = os.path.normpath(bpy.path.abspath(ds.cache_directory))
    frame = "0" * max(4, len(str(ds.cache_frame_end)))
    data = getattr(ds, "cache_data_format", "OPENVDB")
    outputs = [("data", "data", data)]
    if getattr(ds, "use_mesh", False):
        outputs.append(("mesh", "mesh", getattr(ds, "cache_mesh_format", "BOBJECT")))
    if any(getattr(ds, f, False) for f in ("use_spray_particles", "use_foam_particles",
                                           "use_bubble_particles", "use_tracer_particles")):
        # A dynamic enum that reads '' on 4.5/5.2; the files follow the data format.
        outputs.append(("particles", "particles",
                        getattr(ds, "cache_particle_format", "") or data))
    if getattr(ds, "use_guide", False):
        outputs.append(("guiding", "guiding", data))
    if getattr(ds, "use_noise", False) and ds.domain_type == "GAS":
        outputs.append(("noise", "noise", getattr(ds, "cache_noise_format", "OPENVDB")))
    # An unknown format counts as the longest known extension.
    paths = [os.path.join(root, folder, f"fluid_{name}_{frame}{_CACHE_EXT.get(fmt, '.bobj.gz')}")
             for folder, name, fmt in outputs]
    return max(paths, key=len)


def cache_path_too_long(ds):
    """Length of the longest cache path when Windows would silently drop
    it, else 0."""
    if sys.platform != "win32":
        return 0
    n = len(longest_cache_path(ds))
    return n if n >= WINDOWS_PATH_LIMIT else 0


# What Blender's Free All deletes inside the cache folder; anything else
# there (the user's own files) is left alone.
_CACHE_SUBDIRS = ("config", "data", "noise", "mesh", "particles", "guiding")
_CACHE_KINDS = ("data", "noise", "mesh", "particles", "guide")


def free_bake(entry, ds):
    """Free the bake now and leave the domain ready for a clean bake.
    Returns the cache folders that could not be deleted (files in use).

    Never fluid.free_all: it runs as a job, and on Blender 4.5 a bake (or,
    headless, any evaluation) that starts before the job ends crashes in
    MANTA::initLiquid after "name 'sm5' is not defined" (5.2 is fine).
    Pointing the domain at another folder resets the solver at once; Bake
    All on a domain that was not reset starts from the old solver state
    and bakes a different result.  The domain then goes back to its own
    folder (//aquasuite_cache/<id>, which Delete and the path-length check
    rely on), emptied."""
    folder = ds.cache_directory
    # Unsaved, "//" would point at Blender's working folder: delete nothing.
    unsaved = folder.startswith("//") and not bpy.data.filepath
    root = None if unsaved else bpy.path.abspath(folder)
    base = folder.rstrip("/\\") + "_free"
    detour, n = base, 1
    while os.path.exists(bpy.path.abspath(detour)):
        detour, n = f"{base}{n}", n + 1
    failed = []
    ds.cache_directory = detour  # nothing is written there
    try:
        for name in _CACHE_SUBDIRS if root else ():
            path = os.path.join(root, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                if os.path.isdir(path):
                    failed.append(path)
    finally:
        ds.cache_directory = folder
    # Without the pause reset the next bake resumes at the last frame and
    # writes only that frame.
    for kind in _CACHE_KINDS:
        _safe(ds, f"cache_frame_pause_{kind}", 0)
        _safe(ds, f"has_cache_baked_{kind}", False)
    from ..core import delete
    own = delete.cache_dir(entry.uuid)
    if own and root and os.path.normcase(os.path.abspath(own)) == os.path.normcase(os.path.abspath(root)):
        try:
            os.rmdir(root)  # only when empty
        except OSError:
            pass
    return failed


def estimated_memory_gb(entry):
    """Upper planning allowance; includes other active liquid assemblies."""
    from ..core import memory, presets
    return memory.scene_allowance(presets.scene_for(entry))[1]


@contextlib.contextmanager
def _fluid_op_override(context, dom):
    """Make `dom` the genuinely active+selected object for the duration
    of a fluid bake/free operator, then restore the user's selection.

    Fluid operators resolve their target from the active object; a
    temp_override alone is not sufficient on all code paths, so we set
    the real view-layer state (with restore) *and* provide the override.
    """
    vl = context.view_layer
    prev_active = vl.objects.active
    prev_sel = [o for o in vl.objects if o.select_get()]
    for o in prev_sel:
        o.select_set(False)
    try:
        dom.select_set(True)
    except RuntimeError:
        pass  # not selectable in this view layer; the override still applies
    try:
        vl.objects.active = dom
    except Exception:
        pass
    try:
        with context.temp_override(active_object=dom, object=dom,
                                   selected_objects=[dom],
                                   selected_editable_objects=[dom]):
            yield
    finally:
        try:
            dom.select_set(False)
        except RuntimeError:
            pass
        for o in prev_sel:
            try:
                o.select_set(True)
            except (RuntimeError, ReferenceError):
                pass
        try:
            vl.objects.active = prev_active
        except Exception:
            pass


class AQS_OT_bake_fluid(bpy.types.Operator):
    bl_idname = "aquasuite.bake_fluid"
    bl_label = "Bake Liquid"
    bl_description = "Bake the Mantaflow simulation for this assembly"

    uuid: bpy.props.StringProperty()

    def invoke(self, context, event):
        """Above the RAM threshold, ask before baking.  A warning that the
        bake starts anyway (and that the next status message hides) is no
        protection against an out-of-memory crash."""
        try:
            entry = registry.get(context.scene, self.uuid)
            gb = estimated_memory_gb(entry)
            # Don't ask to confirm a bake that execute() will refuse.
            from ..core import presets
            _dom, ds = presets.domain(entry)
            if ds is not None and cache_path_too_long(ds):
                gb = 0.0
        except Exception:
            gb = 0.0
        if gb <= MEMORY_CONFIRM_GB:
            return self.execute(context)
        msg = C.MSG["W022"].format(gb=gb)
        wm = context.window_manager
        try:
            return wm.invoke_confirm(self, event,
                                     title="Bake with this much memory?",
                                     message=msg, confirm_text="Bake Anyway",
                                     icon="WARNING")
        except TypeError:  # older API without a custom message
            self.report({"WARNING"}, "AQS-W022: " + msg)
            return wm.invoke_confirm(self, event)

    def execute(self, context):
        if not bpy.data.filepath:
            from ..core import errors
            entry = registry.get(context.scene, self.uuid)
            return errors.fail(self, "AquaSuite couldn't start the bake",
                               message="AQS-E020: " + C.MSG["E020"],
                               mode=entry.mode if entry else "", uuid=self.uuid)
        entry = registry.get(context.scene, self.uuid)
        dom = find_domain_object(entry)
        if dom is None:
            self.report({"ERROR"},
                        "No fluid domain found in this assembly — was it "
                        "modified or partially deleted?")
            return {"CANCELLED"}
        # Hose in Mist regime disables the fluid backend; guard it.
        dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None)
        if dmod is not None and not dmod.show_viewport:
            self.report({"ERROR"},
                        "The liquid backend is disabled in the current "
                        "regime (Mist is particle-based and needs no bake). "
                        "Switch to Normal, Spray, or Blast first.")
            return {"CANCELLED"}
        # Ensure the domain is selectable/visible for the operator.
        # Rebind render instances if Mantaflow recreated any secondary systems.
        whitewater.apply(entry)
        # After whitewater.apply: its flags decide whether particle files
        # (the longest names) are written.
        too_long = cache_path_too_long(dmod.domain_settings) if dmod is not None else 0
        if too_long:
            from ..core import errors
            return errors.fail(self, "AquaSuite couldn't start the bake",
                               message="AQS-E021: " + C.MSG["E021"].format(
                                   n=too_long, limit=WINDOWS_PATH_LIMIT - 1),
                               mode=entry.mode, uuid=self.uuid)
        was_hidden = dom.hide_get() if hasattr(dom, "hide_get") else False
        if was_hidden:
            dom.hide_set(False)
        from . import simulated_ocean
        if entry.mode == C.MODE_SIMOCEAN and not simulated_ocean.is_legacy(entry):
            # The wave maker's strength depends on fps and its fade-in on
            # the cache start, which may have changed since it was set.
            simulated_ocean.apply_period(entry)
            # Warn, don't block: a coarse or Draft bake is still a valid
            # layout preview, its waves just die out part-way down the tank.
            warning = simulated_ocean.resolution_warning(entry)
            if warning:
                self.report({'WARNING'}, warning)
        # Only this setup's own flows pour into its domain.
        sync_flows(entry)
        # Living obstacle rule: (re)register Collision-enabled meshes as
        # effectors NOW, so objects added after creation block the water.
        try:
            n = refresh_obstacles(context.scene, entry, report=self.report)
            if n:
                self.report({"INFO"},
                            f"{n} obstacle(s) registered for this bake")
        except Exception as exc:
            print(f"[AquaSuite] obstacle refresh warning: {exc}")

        # RAM guard (the UI path already confirmed in invoke(); this keeps
        # scripted calls informed too).
        try:
            gb = estimated_memory_gb(entry)
            if gb > MEMORY_CONFIRM_GB:
                self.report({"WARNING"},
                            "AQS-W022: " + C.MSG["W022"].format(gb=gb))
        except Exception:
            pass
        ds = dmod.domain_settings if dmod is not None else None
        if ds is not None and ds.has_cache_baked_any:
            # Bake Again: free first, so the bake starts from a reset solver.
            failed = free_bake(entry, ds)
            if failed:
                self.report({"WARNING"}, _in_use_message(failed))
        try:
            with _fluid_op_override(context, dom):
                # INVOKE_DEFAULT runs the bake as a background job: the UI
                # stays responsive, a progress bar appears, and Esc cancels.
                # (A blocking bake looks exactly like a crash — it isn't,
                # but an animator shouldn't have to know that.)
                # Headless (render farms, scripts): a blocking bake.
                bpy.ops.fluid.bake_all(
                    "EXEC_DEFAULT" if bpy.app.background else "INVOKE_DEFAULT")
        except Exception as exc:
            from ..core import errors
            return errors.fail(self, "AquaSuite couldn't start the bake", exc,
                               mode=entry.mode, uuid=self.uuid)
        finally:
            if was_hidden:
                dom.hide_set(True)
        entry.sources_changed = False
        from ..core import bakes
        bakes.watch()
        self.report({"INFO"},
                    "Baking in the background — Cancel Bake in the panel "
                    "(or Esc) stops it")
        return {"FINISHED"}


class AQS_OT_free_fluid(bpy.types.Operator):
    bl_idname = "aquasuite.free_fluid"
    bl_label = "Free Bake"

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        dom = find_domain_object(entry)
        if dom is None:
            self.report({"ERROR"},
                        "No fluid domain found in this assembly.")
            return {"CANCELLED"}
        ds = next(m for m in dom.modifiers if m.type == "FLUID").domain_settings
        if ds.is_cache_baking_any:
            self.report({"WARNING"}, "Cancel the bake first, then Free Bake")
            return {"CANCELLED"}
        try:
            failed = free_bake(entry, ds)
            entry.sources_changed = False
        except Exception as exc:
            from ..core import errors
            return errors.fail(self, "AquaSuite couldn't free the bake", exc,
                               mode=entry.mode, uuid=self.uuid)
        if failed:
            self.report({"WARNING"}, _in_use_message(failed))
        return {"FINISHED"}


def _in_use_message(failed):
    return (f"{len(failed)} cache folder(s) could not be fully deleted — "
            f"a file is in use ({failed[0]})")


CLASSES = (AQS_OT_still_water_create, AQS_OT_still_water_add_source,
           AQS_OT_water_source_remove, AQS_OT_bake_fluid, AQS_OT_free_fluid)
