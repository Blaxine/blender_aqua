# SPDX-License-Identifier: GPL-3.0-or-later
"""Floating Objects: one collection per scene, like Water Obstacles.

Objects in it float (or sink) on the baked water of the liquid setup whose
tank they are in: Bake Floaters reads the liquid frame by frame and keys
their motion (level2/floaters.py does the physics).  Each object has a
material (its density) or a mass, and may "push water": then it is also a
collision effector, and Bake Floaters bakes the water and the floaters
together, so the water splashes and makes wakes around them.

Membership is the rule.  Removing an object from the collection — with the
panel's button or by hand in the Outliner — removes its keys and effector
and puts it back where it was, with its own animation.  So do Clear
Floaters, freeing the liquid's bake and deleting the liquid setup.
"""

import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty

from .. import constants as C
from . import registry

COLLECTION_NAME = "AQS Floating Objects"
WATER_PROP = "aqs_floater_water"      # uuid of the liquid setup that keyed it
MIN_CELLS = 5                         # smaller objects can't push water
_cache = {}                           # scene name -> frozenset of member names

# Liquid setups whose water floaters can ride.
LIQUID_MODES = (C.MODE_STILL, C.MODE_SIMOCEAN, C.MODE_SIMRAIN, C.MODE_HOSE)

DENSITY = {key: rho for key, _label, rho in C.FLOAT_MATERIALS}


# ---------------------------------------------------------------------------
# Per-object settings
# ---------------------------------------------------------------------------

def _material_update(self, context):
    if self.material in DENSITY:
        self.density = DENSITY[self.material]


def _pushes_update(self, context):
    obj = self.id_data
    scene = context.scene if context else bpy.context.scene
    if obj.name in _member_names(scene):
        from ..level2 import floaters
        floaters.set_pushes_water(obj, self.pushes_water)


class AQS_FloatSettings(bpy.types.PropertyGroup):
    material: EnumProperty(
        name="Material", items=C.float_material_items(), default="WOOD",
        update=_material_update,
        description="What the object is made of: sets its density")
    density: FloatProperty(
        name="Density", default=600.0, min=1.0, soft_max=10000.0,
        precision=0, unit="NONE",
        description="kg/m³. Water is 1000: lighter floats, heavier sinks")
    use_mass: BoolProperty(
        name="Mass Override", default=False,
        description="Give the mass directly instead of the density "
                    "(hollow objects, boats)")
    mass: FloatProperty(
        name="Mass", default=10.0, min=0.001, soft_max=10000.0, unit="MASS",
        description="kg")
    pushes_water: BoolProperty(
        name="Pushes Water", default=False, update=_pushes_update,
        description="The object also moves the water: splashes when it "
                    "drops in, wakes when it drifts. Bake Floaters then "
                    "bakes the water too (it takes as long as a liquid bake)")


def mass_of(obj):
    """(mass kg, density kg/m³) or (None, None) for meshes without volume."""
    from ..level2 import floaters
    if not floaters.is_closed(obj):
        return None, None
    s = obj.aqs_float
    volume = floaters.mesh_volume(obj)
    if volume <= 0.0:
        return None, None
    mass = s.mass if s.use_mass else s.density * volume
    return mass, mass / volume


def buoyancy_note(obj):
    """'75 kg · floats ~60% submerged' / '... · sinks'."""
    mass, density = mass_of(obj)
    if mass is None:
        return ""
    from ..level2 import floaters
    if density >= floaters.RHO_WATER:
        return f"{mass:.3g} kg · sinks"
    return f"{mass:.3g} kg · floats ~{density / floaters.RHO_WATER * 100:.0f}% submerged"


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collection(scene, create=False):
    col = getattr(scene, "aqs_floating", None)
    if col is None and create:
        col = bpy.data.collections.new(COLLECTION_NAME)
        col["aqs_floating"] = True
        scene.collection.children.link(col)
        scene.aqs_floating = col
    return col


def members(scene):
    col = collection(scene)
    return list(col.objects) if col is not None else []


def _member_names(scene):
    col = collection(scene)
    return frozenset(o.name for o in col.objects) if col is not None else frozenset()


def is_member(obj):
    for scene in bpy.data.scenes:
        col = getattr(scene, "aqs_floating", None)
        if col is not None and obj.name in col.objects:
            return True
    return False


def eligible(obj):
    """(ok, reason)."""
    from ..level2 import floaters
    from . import obstacles
    ok, why = floaters.eligible(obj)
    if not ok:
        return ok, why
    if obstacles.is_member(obj):
        return False, "it is a Water Obstacle"
    fluid = next((m for m in obj.modifiers if m.type == "FLUID"), None)
    if fluid is not None and getattr(fluid, "fluid_type", "") != "EFFECTOR":
        return False, "it already has a Fluid setup"
    return True, ""


def _release(obj):
    """Undo everything AquaSuite did to a (former) floater."""
    from ..level2 import floaters
    floaters.clear(obj)
    floaters.set_pushes_water(obj, False)
    if WATER_PROP in obj.keys():
        del obj[WATER_PROP]


def _ours(obj):
    from ..level2 import floaters
    return any(p in obj.keys() for p in (floaters.RESTORE_PROP,
                                          floaters.EFFECTOR_PROP, WATER_PROP))


def sync(scene):
    """Make the scene's floaters match its collection.  Returns the number
    of floaters."""
    from ..level2 import floaters
    objs = members(scene)
    for obj in objs:
        want = obj.aqs_float.pushes_water and eligible(obj)[0]
        if want != bool(obj.get(floaters.EFFECTOR_PROP)):
            floaters.set_pushes_water(obj, want)
    for obj in bpy.data.objects:
        if _ours(obj) and not is_member(obj):
            _release(obj)
    _cache[scene.name] = _member_names(scene)
    return len(objs)


def add(scene, objs):
    """Add objects; returns (added names, [(name, reason)] skipped)."""
    col = collection(scene, create=True)
    added, skipped = [], []
    for obj in objs:
        ok, why = eligible(obj)
        if not ok:
            skipped.append((obj.name, why))
            continue
        if obj.name not in col.objects:
            col.objects.link(obj)
        added.append(obj.name)
    sync(scene)
    return added, skipped


def remove(scene, objs):
    col = collection(scene)
    removed = []
    if col is not None:
        for obj in objs:
            if obj.name in col.objects:
                col.objects.unlink(obj)
                removed.append(obj.name)
    sync(scene)
    return removed


# ---------------------------------------------------------------------------
# Which water an object floats on
# ---------------------------------------------------------------------------

def domain_of(entry):
    from ..level2 import still_water as sw
    if entry is None or entry.mode not in LIQUID_MODES:
        return None
    if entry.mode == C.MODE_HOSE and not entry.hose_liquid:
        return None
    return sw.find_domain_object(entry)


def _inside(obj, dom):
    from ..level2 import still_water as sw
    dims = sw.object_dims(dom)
    c = dom.matrix_world.translation
    p = obj.matrix_world.translation
    return all(abs(p[i] - c[i]) <= dims[i] / 2 for i in range(3))


def floaters_of(entry, scene=None):
    """Floating objects inside this liquid setup's tank."""
    dom = domain_of(entry)
    if dom is None:
        return []
    scene = scene or bpy.context.scene
    return [o for o in members(scene) if _inside(o, dom)]


def outside(scene):
    """Floating objects that are in no liquid tank."""
    doms = [d for d in (domain_of(e) for e in registry.entries(scene)) if d]
    return [o for o in members(scene) if not any(_inside(o, d) for d in doms)]


def warnings(obj, entry=None):
    """Why this floater can't float (or push water) as it is."""
    from ..level2 import floaters
    out = []
    if obj.type != "MESH":
        return ["not a mesh"]
    if obj.parent is not None:
        out.append("has a parent: unparent it")
    if not floaters.is_closed(obj):
        out.append("mesh has holes: it has no volume")
    dom = domain_of(entry) if entry is not None else None
    if dom is not None and obj.aqs_float.pushes_water:
        from ..level2 import still_water as sw
        mod = next((m for m in dom.modifiers if m.type == "FLUID"), None)
        ds = getattr(mod, "domain_settings", None)
        if ds is not None and ds.resolution_max > 0:
            cell = max(sw.object_dims(dom)) / ds.resolution_max
            size = min(obj.dimensions)
            if size < MIN_CELLS * cell:
                out.append(f"only {size / cell:.0f} cells across: too small "
                           f"to push water at this resolution")
    return out


def keyed(entry):
    """Objects this liquid setup's bake keyed."""
    return [o for o in bpy.data.objects if o.get(WATER_PROP) == entry.uuid]


def clear_water(assembly_uuid):
    """Remove the keys a liquid setup's bake gave its floaters (they stay
    floating objects)."""
    from ..level2 import floaters
    n = 0
    for obj in list(bpy.data.objects):
        if obj.get(WATER_PROP) == assembly_uuid:
            floaters.clear(obj)
            del obj[WATER_PROP]
            n += 1
    return n


# ---------------------------------------------------------------------------
# Baking
# ---------------------------------------------------------------------------

def _wave_params(entry, dom):
    """Ocean (Simulated): wave number and still level for the decay of the
    wave's push with depth."""
    if entry.mode != C.MODE_SIMOCEAN:
        return {}
    from ..level2 import simulated_ocean as so
    from ..level2 import still_water as sw
    _length, _width, depth = entry.tank_size
    water = depth * so.WATER_FRACTION
    bottom = dom.matrix_world.translation.z - sw.object_dims(dom).z / 2
    return dict(wave_number=so.wave_number(entry.wave_period, water),
                rest_level=bottom + water)


def pushes_water(entry, scene=None):
    return [o for o in floaters_of(entry, scene) if o.aqs_float.pushes_water]


def _progress(wm, first):
    def report(frame):
        try:
            wm.progress_update(frame - first)
        except Exception:
            pass
    return report


def bake_one_way(context, entry):
    """Float the setup's floaters on its baked water.  Returns
    (floaters baked, seconds)."""
    from ..level2 import floaters
    scene = context.scene
    dom = domain_of(entry)
    objs = [o for o in floaters_of(entry, scene) if eligible(o)[0]]
    if dom is None or not objs:
        return 0, 0.0
    clear_water(entry.uuid)
    for obj in objs:
        floaters.clear(obj)  # start from where the user put it
    ds = next(m for m in dom.modifiers if m.type == "FLUID").domain_settings
    first, last = ds.cache_frame_start, ds.cache_frame_end
    frame = scene.frame_current
    wm = context.window_manager
    wm.progress_begin(0, max(last - first, 1))
    t = time.perf_counter()
    try:
        floaters.bake(scene, dom, objs, first, last, params=_wave_params(entry, dom),
                      progress=_progress(wm, first))
    finally:
        wm.progress_end()
        scene.frame_set(frame)
    for obj in objs:
        obj[WATER_PROP] = entry.uuid
    return len(objs), time.perf_counter() - t


def _free_liquid(context, entry, ds):
    """Free the liquid bake before baking it again with the floaters."""
    if not ds.has_cache_baked_any:
        return
    from ..level2 import still_water as sw
    free_bake = getattr(sw, "free_bake", None)
    if free_bake is not None:
        free_bake(entry, ds)
    else:
        bpy.ops.aquasuite.free_fluid(uuid=entry.uuid)


def bake_coupled(context, entry, report):
    """Bake the liquid and its floaters together (some push water).

    A blocking bake: Blender runs frame_change_pre before every frame it
    bakes, after the previous frame's liquid mesh is on disk.  The handler
    reads that mesh, moves the floaters one frame and writes their pose
    into keys made before the bake, so their effectors push the water.
    Returns (floaters baked, seconds) or raises."""
    from ..level2 import floaters
    from ..level2 import still_water as sw
    from ..level2 import simulated_ocean
    from . import whitewater
    scene = context.scene
    dom = domain_of(entry)
    objs = [o for o in floaters_of(entry, scene) if eligible(o)[0]]
    if dom is None or not objs:
        return 0, 0.0
    mod = next(m for m in dom.modifiers if m.type == "FLUID")
    ds = mod.domain_settings
    clear_water(entry.uuid)
    for obj in objs:
        floaters.clear(obj)
    sync(scene)
    # What Bake Liquid does before it bakes.
    sw.sync_flows(entry)
    whitewater.apply(entry)
    if entry.mode == C.MODE_SIMOCEAN and not simulated_ocean.is_legacy(entry):
        simulated_ocean.apply_period(entry)
    try:
        sw.refresh_obstacles(scene, entry, report=report)
    except Exception as exc:
        print(f"[AquaSuite] obstacle refresh warning: {exc}")
    # Moving obstacles lose water with fractions on (-11% measured).  Only
    # ever written right before the synchronous free below: written after
    # a bake and freed with Free All, it broke the next 4.5 bake.
    if ds.use_fractions:
        ds.use_fractions = False
    _free_liquid(context, entry, ds)
    first, last = ds.cache_frame_start, ds.cache_frame_end
    frame = scene.frame_current
    wm = context.window_manager
    wm.progress_begin(0, max(last - first, 1))
    was_hidden = dom.hide_get() if hasattr(dom, "hide_get") else False
    if was_hidden:
        dom.hide_set(False)
    t = time.perf_counter()
    try:
        with floaters.CoupledBake(scene, dom, objs, params=_wave_params(entry, dom),
                                  progress=_progress(wm, first)):
            with sw._fluid_op_override(context, dom):
                bpy.ops.fluid.bake_all("EXEC_DEFAULT")
    finally:
        wm.progress_end()
        if was_hidden:
            dom.hide_set(True)
        scene.frame_set(frame)
    for obj in objs:
        obj[WATER_PROP] = entry.uuid
    return len(objs), time.perf_counter() - t


def estimate_minutes(entry):
    """Rough length of a coupled bake: the liquid bake plus ~0.05 s/frame."""
    dom = domain_of(entry)
    mod = next((m for m in dom.modifiers if m.type == "FLUID"), None) if dom else None
    ds = getattr(mod, "domain_settings", None)
    if ds is None:
        return 0.0
    frames = ds.cache_frame_end - ds.cache_frame_start + 1
    # Measured: 0.67 s/frame for 0.59 M cells (3x3x2 m tank at 96),
    # 0.47 s/frame for 0.33 M (Rolling Waves at 160).
    from ..level2.rain_sim import memory_estimate
    mcells, _gb = memory_estimate(dom, ds.resolution_max)
    per_frame = 1.2 * max(mcells, 0.05) + 0.05
    return frames * per_frame * 1.3 / 60.0


# ---------------------------------------------------------------------------
# Keeping in sync when the collection is edited by hand
# ---------------------------------------------------------------------------

@persistent
def _on_depsgraph(scene, _depsgraph=None):
    if _cache.get(scene.name) != _member_names(scene):
        try:
            sync(scene)
        except Exception as exc:
            from . import errors
            errors.record("AquaSuite couldn't update the floating objects", exc)
            errors.schedule()


@persistent
def _on_load(_dummy=None):
    _cache.clear()
    for scene in bpy.data.scenes:
        try:
            sync(scene)
        except Exception as exc:
            print(f"[AquaSuite] floating objects sync on load failed: {exc}")


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class AQS_OT_floating_add(bpy.types.Operator):
    bl_idname = "aquasuite.floating_add"
    bl_label = "Add to Floating Objects"
    bl_description = ("Selected closed meshes float or sink on the liquid "
                      "they are in when you Bake Floaters")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objs = list(context.selected_objects) or (
            [context.active_object] if context.active_object else [])
        if not objs:
            self.report({"INFO"}, "Select the objects that should float first")
            return {"CANCELLED"}
        added, skipped = add(context.scene, objs)
        msg = f"{len(added)} object(s) added to Floating Objects"
        if skipped:
            msg += "; skipped " + ", ".join(f"{n} ({why})" for n, why in skipped)
        self.report({"WARNING"} if skipped else {"INFO"}, msg)
        return {"FINISHED"} if added else {"CANCELLED"}


class AQS_OT_floating_remove(bpy.types.Operator):
    bl_idname = "aquasuite.floating_remove"
    bl_label = "Remove from Floating Objects"
    bl_description = ("Selected objects stop floating: their floater keys "
                      "go and they are put back where they were")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = remove(context.scene, list(context.selected_objects))
        self.report({"INFO"}, f"{len(removed)} object(s) removed from Floating Objects")
        return {"FINISHED"} if removed else {"CANCELLED"}


class AQS_OT_bake_floaters(bpy.types.Operator):
    bl_idname = "aquasuite.bake_floaters"
    bl_label = "Bake Floaters"
    bl_description = ("Float the Floating Objects in this tank on its baked "
                      "water and key their motion. With Pushes Water, the "
                      "water is baked again together with them")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    def invoke(self, context, event):
        entry = registry.get(context.scene, self.uuid)
        if entry is None or not pushes_water(entry, context.scene):
            return self.execute(context)
        minutes = estimate_minutes(entry)
        msg = ("The water is baked again with the floaters pushing it. "
               f"Blender is busy until it finishes (roughly {max(minutes, 1):.0f} min)")
        wm = context.window_manager
        try:
            return wm.invoke_confirm(self, event, title="Bake water and floaters?",
                                     message=msg, confirm_text="Bake", icon="INFO")
        except TypeError:  # older API without a custom message
            self.report({"INFO"}, msg)
            return wm.invoke_confirm(self, event)

    def execute(self, context):
        from . import bakes, errors
        entry = registry.get(context.scene, self.uuid)
        if entry is None or domain_of(entry) is None:
            self.report({"ERROR"}, "No liquid found for this setup")
            return {"CANCELLED"}
        if bakes.is_baking(entry):
            self.report({"WARNING"}, "Wait for the liquid bake to finish")
            return {"CANCELLED"}
        objs = floaters_of(entry, context.scene)
        good = [o for o in objs if eligible(o)[0]]
        if not good:
            self.report({"INFO"}, "No floating objects in this tank — add "
                                  "some with + under Floating Objects")
            return {"CANCELLED"}
        skipped = len(objs) - len(good)
        if pushes_water(entry, context.scene):
            if not bpy.data.filepath:
                return errors.fail(self, "AquaSuite couldn't start the bake",
                                   message="AQS-E020: " + C.MSG["E020"],
                                   mode=entry.mode, uuid=self.uuid)
            from ..level2 import still_water as sw
            dom = domain_of(entry)
            ds = next(m for m in dom.modifiers if m.type == "FLUID").domain_settings
            too_long = sw.cache_path_too_long(ds)
            if too_long:
                return errors.fail(self, "AquaSuite couldn't start the bake",
                                   message="AQS-E021: " + C.MSG["E021"].format(
                                       n=too_long, limit=sw.WINDOWS_PATH_LIMIT - 1),
                                   mode=entry.mode, uuid=self.uuid)
            n, secs = bake_coupled(context, entry, self.report)
            what = "Water and floaters baked"
        else:
            if not bakes.has_bake(entry):
                self.report({"WARNING"}, "Bake the liquid first")
                return {"CANCELLED"}
            n, secs = bake_one_way(context, entry)
            what = "Floaters baked"
        msg = f"{what}: {n} object(s) in {secs:.0f} s"
        if skipped:
            msg += f"; {skipped} skipped (see the warnings)"
        self.report({"WARNING"} if skipped else {"INFO"}, msg)
        return {"FINISHED"}


class AQS_OT_clear_floaters(bpy.types.Operator):
    bl_idname = "aquasuite.clear_floaters"
    bl_label = "Clear Floaters"
    bl_description = ("Remove the floater keys this tank's bake made and put "
                      "the objects back where they were")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        n = clear_water(self.uuid)
        self.report({"INFO"}, f"{n} floater(s) cleared")
        return {"FINISHED"} if n else {"CANCELLED"}


class AQS_OT_free_liquid(bpy.types.Operator):
    bl_idname = "aquasuite.free_liquid"
    bl_label = "Free Bake"
    bl_description = ("Delete this setup's baked frames. Floaters keyed on "
                      "this water lose their keys and go back where they were")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        clear_water(self.uuid)
        return bpy.ops.aquasuite.free_fluid(uuid=self.uuid)


CLASSES = (AQS_FloatSettings, AQS_OT_floating_add, AQS_OT_floating_remove,
           AQS_OT_bake_floaters, AQS_OT_clear_floaters, AQS_OT_free_liquid)


def register():
    bpy.types.Object.aqs_float = bpy.props.PointerProperty(type=AQS_FloatSettings)
    bpy.types.Scene.aqs_floating = bpy.props.PointerProperty(
        type=bpy.types.Collection, name="Floating Objects",
        description="Objects in this collection float on AquaSuite liquids")
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    _cache.clear()
    for owner, name in ((bpy.types.Object, "aqs_float"),
                        (bpy.types.Scene, "aqs_floating")):
        if hasattr(owner, name):
            try:
                delattr(owner, name)
            except Exception as exc:
                print(f"[AquaSuite] cleanup {owner.__name__}.{name}: {exc}")
