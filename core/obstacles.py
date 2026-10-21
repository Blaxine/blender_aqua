# SPDX-License-Identifier: GPL-3.0-or-later
"""Water Obstacles: one collection per scene; everything in it blocks and
deflects water in every simulation — Still Water, Rain Sim, the hose's
liquid simulation (Fluid effector) and the hose's real-time jets and mist
(Collision, which the hose particles are limited to).

Membership is the only rule.  What AquaSuite adds to an obstacle is
recorded on it, and removing the object from the collection — with the
panel's remove button or by hand in the Outliner — removes exactly that.
Modifiers the user had before are never touched.
"""

import json

import bpy
from bpy.app.handlers import persistent

from .. import constants as C

COLLECTION_NAME = "AQS Water Obstacles"
MARK_PROP = "aqs_obstacle"        # JSON {"collision": bool, "fluid": bool}
_cache = {}                       # scene name -> frozenset of member names


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collection(scene, create=False):
    col = getattr(scene, "aqs_obstacles", None)
    if col is None and create:
        col = bpy.data.collections.new(COLLECTION_NAME)
        col["aqs_obstacles"] = True
        scene.collection.children.link(col)
        scene.aqs_obstacles = col
    return col


def members(scene):
    col = collection(scene)
    return list(col.objects) if col is not None else []


def is_member(obj):
    for scene in bpy.data.scenes:
        col = getattr(scene, "aqs_obstacles", None)
        if col is not None and obj.name in col.objects:
            return True
    return False


def eligible(obj):
    """(ok, reason).  Meshes only; never AquaSuite domains/flows or liquid
    sources — water can't both come from an object and be blocked by it."""
    if obj.type != "MESH":
        return False, "not a mesh"
    if C.SRC_PROP in obj.keys():
        return False, "it is a water source"
    from . import floating
    if floating.is_member(obj):
        return False, "it is a Floating Object"
    fluid = next((m for m in obj.modifiers if m.type == "FLUID"), None)
    if fluid is not None and getattr(fluid, "fluid_type", "") != "EFFECTOR":
        return False, "it already has a Fluid setup"
    return True, ""


# ---------------------------------------------------------------------------
# Applying / removing what AquaSuite adds
# ---------------------------------------------------------------------------

def _apply(obj):
    mark = {"collision": False, "fluid": False}
    if not any(m.type == "COLLISION" for m in obj.modifiers):
        obj.modifiers.new("AQS Collision", "COLLISION")
        col = obj.collision
        if col is not None:
            # Water splats and slides; it doesn't bounce like rubber.
            col.damping_factor = 0.85
            col.damping_random = 0.1
            col.friction_factor = 0.4
            col.friction_random = 0.2
        mark["collision"] = True
    if not any(m.type == "FLUID" for m in obj.modifiers):
        add_fluid_effector(obj, "AQS Effector")
        mark["fluid"] = True
    obj[MARK_PROP] = json.dumps(mark)


def add_fluid_effector(obj, name):
    """A collision Fluid effector; floaters that push water use it too,
    with their own mark so sync() leaves them alone."""
    fluid = obj.modifiers.new(name, "FLUID")
    fluid.fluid_type = "EFFECTOR"
    es = fluid.effector_settings
    if hasattr(es, "effector_type"):
        es.effector_type = "COLLISION"
    return fluid


def _unapply(obj):
    try:
        mark = json.loads(obj.get(MARK_PROP, "{}"))
    except Exception:
        mark = {}
    # One Collision and one Fluid modifier per object: found by type, so a
    # renamed modifier is still removed.
    if mark.get("collision"):
        for m in list(obj.modifiers):
            if m.type == "COLLISION":
                obj.modifiers.remove(m)
                break
    if mark.get("fluid"):
        for m in list(obj.modifiers):
            if m.type == "FLUID" and getattr(m, "fluid_type", "") == "EFFECTOR":
                obj.modifiers.remove(m)
                break
    if MARK_PROP in obj.keys():
        del obj[MARK_PROP]


def _effector_thickness(scene):
    """~1 voxel of the coarsest liquid domain, so thin walls don't leak."""
    from ..level2 import still_water as sw
    dx = 0.0
    for entry in getattr(scene, "aqs_assemblies", []):
        dom = sw.find_domain_object(entry)
        mod = next((m for m in dom.modifiers if m.type == "FLUID"), None) if dom else None
        ds = getattr(mod, "domain_settings", None)
        if ds is not None and ds.resolution_max > 0:
            dx = max(dx, max(sw.object_dims(dom)) / ds.resolution_max)
    return min(max(dx, 0.02), 0.3) if dx > 0 else None


def sync(scene):
    """Make the scene's obstacles match its collection.  Returns the number
    of obstacles."""
    objs = members(scene)
    for obj in objs:
        if MARK_PROP not in obj.keys() and eligible(obj)[0]:
            _apply(obj)
    for obj in bpy.data.objects:
        if MARK_PROP in obj.keys() and not is_member(obj):
            _unapply(obj)
    thickness = _effector_thickness(scene)
    for obj in objs:
        for m in obj.modifiers:
            if m.type == "FLUID" and getattr(m, "fluid_type", "") == "EFFECTOR":
                es = m.effector_settings
                if hasattr(es, "use_effector"):
                    es.use_effector = True
                if thickness is not None and hasattr(es, "surface_distance") \
                        and MARK_PROP in obj.keys():
                    es.surface_distance = thickness
    col = collection(scene)
    _cache[scene.name] = frozenset(o.name for o in col.objects) if col else frozenset()
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
# Keeping in sync when the collection is edited by hand
# ---------------------------------------------------------------------------

@persistent
def _on_depsgraph(scene, _depsgraph=None):
    col = getattr(scene, "aqs_obstacles", None)
    names = frozenset(o.name for o in col.objects) if col is not None else frozenset()
    if _cache.get(scene.name) != names:
        try:
            sync(scene)
        except Exception as exc:
            from . import errors
            errors.record("AquaSuite couldn't update the water obstacles", exc)
            errors.schedule()


@persistent
def _on_load(_dummy=None):
    _cache.clear()
    for scene in bpy.data.scenes:
        try:
            sync(scene)
        except Exception as exc:
            print(f"[AquaSuite] obstacle sync on load failed: {exc}")


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class AQS_OT_obstacles_add(bpy.types.Operator):
    bl_idname = "aquasuite.obstacles_add"
    bl_label = "Add to Water Obstacles"
    bl_description = ("Selected meshes block and deflect water in every "
                      "simulation (Still Water, Water Hose, Rain Sim)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objs = list(context.selected_objects) or (
            [context.active_object] if context.active_object else [])
        if not objs:
            self.report({"INFO"}, "Select the objects water should hit first")
            return {"CANCELLED"}
        added, skipped = add(context.scene, objs)
        msg = f"{len(added)} object(s) added to Water Obstacles"
        if skipped:
            msg += "; skipped " + ", ".join(f"{n} ({why})" for n, why in skipped)
        self.report({"WARNING"} if skipped else {"INFO"}, msg)
        return {"FINISHED"} if added else {"CANCELLED"}


class AQS_OT_obstacles_remove(bpy.types.Operator):
    bl_idname = "aquasuite.obstacles_remove"
    bl_label = "Remove from Water Obstacles"
    bl_description = ("Selected objects stop blocking water; what AquaSuite "
                      "added to them is removed")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = remove(context.scene, list(context.selected_objects))
        self.report({"INFO"}, f"{len(removed)} object(s) removed from Water Obstacles")
        return {"FINISHED"} if removed else {"CANCELLED"}


CLASSES = (AQS_OT_obstacles_add, AQS_OT_obstacles_remove)


def register():
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
