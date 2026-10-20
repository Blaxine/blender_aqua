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


def make_domain(name, mode, uid, col, mins, maxs,
                pad_xy=1.5, pad_up=1.2, pad_dn=2.5):
    size = maxs - mins
    center = (maxs + mins) * 0.5
    half = Vector((max(size.x, 0.1) * 0.5 * pad_xy,
                   max(size.y, 0.1) * 0.5 * pad_xy, 0.0))
    top = maxs.z + max(size.z, 0.1) * (pad_up - 1.0)
    bottom = mins.z - max(size.z, 0.1) * (pad_dn - 1.0)

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    dom = naming.new_mesh_object(col, name, mesh, mode, uid)
    dom.location = (center.x, center.y, (top + bottom) * 0.5)
    dom.scale = (half.x * 2.0, half.y * 2.0, (top - bottom))
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


class AQS_OT_still_water_create(bpy.types.Operator):
    bl_idname = "aquasuite.still_water_create"
    bl_label = "Turn Into Water"
    bl_description = ("The active mesh's volume becomes actual liquid "
                      "(Mantaflow FLIP — baking is mandatory)")
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

        # Flow: one-shot GEOMETRY fill (§7.1.2 step 3)
        flow = src.modifiers.new("AQS Flow", "FLUID")
        flow.fluid_type = "FLOW"
        fs = flow.flow_settings
        fs.flow_type = "LIQUID"
        fs.flow_behavior = "GEOMETRY"
        _safe(fs, "use_initial_velocity", False)

        # Source visibility policy + restore records (§7.1.2 step 4)
        entry = registry.add(scene, C.MODE_STILL, uid, primary=dom,
                             root_collection=col)
        entry["base_resolution"] = RES_PRESETS["MEDIUM"]
        entry.source = src
        entry.src_hide_render = src.hide_render
        entry.src_display_type = src.display_type
        src.hide_render = True
        src.display_type = "WIRE"
        # Dedicated source marker — deliberately NOT the owner tag, so the
        # delete sweep can never remove a user object (even if the registry
        # entry is lost in an old file).
        src[C.SRC_PROP] = uid

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
        was_hidden = dom.hide_get() if hasattr(dom, "hide_get") else False
        if was_hidden:
            dom.hide_set(False)
        try:
            with _fluid_op_override(context, dom):
                bpy.ops.fluid.free_all()
        except Exception as exc:
            from ..core import errors
            return errors.fail(self, "AquaSuite couldn't free the bake", exc,
                               mode=entry.mode if entry else "", uuid=self.uuid)
        finally:
            if was_hidden:
                dom.hide_set(True)
        return {"FINISHED"}


CLASSES = (AQS_OT_still_water_create, AQS_OT_bake_fluid,
           AQS_OT_free_fluid)
