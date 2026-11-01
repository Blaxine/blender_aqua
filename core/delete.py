# SPDX-License-Identifier: GPL-3.0-or-later
"""Reversible teardown (TDD §4.3 / core/delete).

Deletion trusts ONLY the ``aqs_owner`` UUID tag — never names.  Tracked
mutations of user data (buoy constraints, source visibility, refcounted
effector modifiers) are restored from their recorded pre-state first,
then every tagged ID is removed.
"""

import functools
import json
import os
import shutil

import bpy

from .. import constants as C
from . import registry

CACHE_ROOT = "aquasuite_cache"

# Datablock collections that can carry an ``aqs_owner`` tag.
_TAGGED_COLLECTIONS = ("objects", "meshes", "particles", "node_groups",
                       "materials", "collections", "actions", "worlds", "lights")


def restore_buoy(b):
    """Match the dedicated driver target, never a mutable constraint name."""
    if b.obj is None or b.empty is None:
        return
    for con in list(b.obj.constraints):
        if con.type in {"COPY_LOCATION", "COPY_ROTATION"} and con.target == b.empty:
            b.obj.constraints.remove(con)


def _restore_buoys(entry):
    for b in entry.buoys:
        restore_buoy(b)


def _restore_one_source(src, uuid, hide_render, display_type):
    """Undo what Still Water / Rain-Sim pools did to a user mesh.

    The Flow modifier is found by TYPE, not name, so a renamed modifier is
    still removed: Blender allows only one Fluid modifier per object and
    Create refuses sources that already carry one (R1.4), so any Fluid
    FLOW on a marked source is ours.
    """
    if src is None:
        return
    src.hide_render = hide_render
    try:
        src.display_type = display_type or "TEXTURED"
    except TypeError:
        src.display_type = "TEXTURED"
    if str(src.get(C.SRC_PROP, "")).endswith(uuid):
        for mod in list(src.modifiers):
            if mod.type == "FLUID" and getattr(mod, "fluid_type", "") == "FLOW":
                src.modifiers.remove(mod)
    for prop in (C.SRC_PROP, C.OWNER_PROP):
        if str(src.get(prop, "")).endswith(uuid):
            del src[prop]
    # Left only in this setup's pool/flow collections (the user unlinked it
    # from their own): those are about to go, so keep it in the scene.
    from . import naming
    cols = src.users_collection
    if cols and all(naming.owned_by(c, uuid) for c in cols):
        bpy.context.scene.collection.objects.link(src)


def _restore_source(entry):
    # Rain-Sim pool sources (each with its own recorded pre-state)
    for rec in getattr(entry, "pool_sources", []):
        _restore_one_source(rec.obj, entry.uuid, rec.hide_render,
                            rec.display_type)
    _restore_one_source(entry.source, entry.uuid, entry.src_hide_render,
                        entry.src_display_type)


def _release_effectors(assembly_uuid, objects=None):
    """Decrement effector refcounts; remove modifiers whose owner list empties
    (R1.4 / §5.3b).

    The owner list is only ever written on objects whose Effector AquaSuite
    created, so the modifier is identified by type — renaming it no longer
    strands it on the user's object.
    """
    for obj in (bpy.data.objects if objects is None else objects):
        raw = obj.get(C.EFFECTOR_OWNERS_PROP)
        if not raw:
            continue
        try:
            owners = json.loads(raw)
        except Exception:
            owners = []
        if assembly_uuid not in owners:
            continue
        owners.remove(assembly_uuid)
        if owners:
            obj[C.EFFECTOR_OWNERS_PROP] = json.dumps(owners)
            continue
        for mod in list(obj.modifiers):
            if (mod.type == "FLUID"
                    and getattr(mod, "fluid_type", "") == "EFFECTOR"):
                obj.modifiers.remove(mod)
        del obj[C.EFFECTOR_OWNERS_PROP]


def _used_elsewhere(id_block, scene):
    """True when anything besides ``scene`` still uses the datablock.

    Runs after the assembly's restore, so ``scene`` only references it
    through its own registry entry.  Another scene's world slot, another
    scene's registry, or a fake user means the user adopted it.
    """
    if id_block.use_fake_user:
        return True
    users = bpy.data.user_map(subset=[id_block]).get(id_block, set())
    return any(u != scene for u in users)


def _remove_or_release(id_block, scene, remover):
    """Remove an owned datablock, or — when the user adopted it elsewhere —
    keep it and drop the owner tag so it becomes ordinary user data that no
    later sweep can touch."""
    if _used_elsewhere(id_block, scene):
        del id_block[C.OWNER_PROP]
    else:
        remover(id_block)


def _remove_tagged(data_iterable, assembly_uuid, remover):
    for id_block in list(data_iterable):
        v = id_block.get(C.OWNER_PROP, "")
        if isinstance(v, str) and v.endswith(":" + assembly_uuid):
            try:
                remover(id_block)
            except Exception:
                pass


# --------------------------------------------------------------------------
# Bake cache on disk
# --------------------------------------------------------------------------

def cache_dir(assembly_uuid):
    """Absolute path of this assembly's default bake cache, or None when the
    .blend is unsaved (``//`` would not point next to a file)."""
    if not bpy.data.filepath or not assembly_uuid:
        return None
    return bpy.path.abspath(f"//{CACHE_ROOT}/{assembly_uuid}")


def cache_size_mb(assembly_uuid):
    path = cache_dir(assembly_uuid)
    if path is None or not os.path.isdir(path):
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 * 1024)


def remove_cache(assembly_uuid):
    """Delete ``//aquasuite_cache/<uuid>`` — only that exact folder, and only
    when it really sits inside the cache root next to the .blend."""
    path = cache_dir(assembly_uuid)
    if path is None or not os.path.isdir(path):
        return False
    root = os.path.normcase(os.path.abspath(bpy.path.abspath(f"//{CACHE_ROOT}")))
    target = os.path.normcase(os.path.abspath(path))
    if os.path.dirname(target) != root:
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


# --------------------------------------------------------------------------
# Teardown
# --------------------------------------------------------------------------

def _copies(scene, assembly_uuid):
    """This setup in other scenes: copying a scene copies the uuid and tags too."""
    return [e for s in bpy.data.scenes if s != scene
            for e in s.aqs_assemblies if e.uuid == assembly_uuid]


def _setup_contents(entry):
    root = entry.root_collection if entry is not None else None
    if root is None:
        return set(), set()
    return set(root.all_objects), {root, *root.children_recursive}


def _delete_this_scene_only(scene, entry, assembly_uuid, copies):
    """Remove this scene's copy; what the other scenes' copies use stays."""
    from . import naming
    d = bpy.data
    keep_objects, keep_collections = set(), set()
    for other in copies:
        objects, collections = _setup_contents(other)
        keep_objects |= objects
        keep_collections |= collections
    objects, collections = _setup_contents(entry)
    for obj in objects - keep_objects:
        if naming.owned_by(obj, assembly_uuid):
            d.objects.remove(obj, do_unlink=True)
    for col in collections - keep_collections:
        d.collections.remove(col)
    registry.remove(scene, assembly_uuid)
    # Dependencies first release their users, so sweep until nothing changes.
    groups = ("meshes", "particles", "node_groups", "materials", "actions", "lights", "worlds")
    removed = True
    while removed:
        removed = False
        for group in groups:
            data = getattr(d, group)
            for id_block in list(data):
                if naming.owned_by(id_block, assembly_uuid) and id_block.users == 0:
                    data.remove(id_block)
                    removed = True


def delete_assembly(scene, assembly_uuid, delete_cache=False):
    entry = registry.get(scene, assembly_uuid)
    copies = _copies(scene, assembly_uuid)
    # Floaters keyed on this water go back where they were (they stay in
    # Floating Objects).
    from . import floating
    floating.clear_water(assembly_uuid, scene.objects if copies else None)
    if entry is not None:
        from . import lighting
        lighting.restore(scene, entry)
        _restore_buoys(entry)
        _restore_source(entry)
        if entry.mode == C.MODE_SIMOCEAN:
            from ..level2 import simulated_ocean
            simulated_ocean.restore_timeline(scene, entry)
    _release_effectors(assembly_uuid, scene.objects if copies else None)

    if copies:
        _delete_this_scene_only(scene, entry, assembly_uuid, copies)
        _prune_empty(scene)
        return

    d = bpy.data
    _remove_tagged(d.objects, assembly_uuid, lambda o: d.objects.remove(o, do_unlink=True))
    _remove_tagged(d.meshes, assembly_uuid, lambda m: d.meshes.remove(m))
    _remove_tagged(d.particles, assembly_uuid, lambda p: d.particles.remove(p))
    _remove_tagged(d.node_groups, assembly_uuid, lambda n: d.node_groups.remove(n))
    _remove_tagged(d.materials, assembly_uuid, lambda m: d.materials.remove(m))
    _remove_tagged(d.collections, assembly_uuid, lambda c: d.collections.remove(c))
    _remove_tagged(d.actions, assembly_uuid, lambda a: d.actions.remove(a))
    # A generated sky world may have been assigned to another scene;
    # removing it would leave that scene with no world (P2).
    _remove_tagged(d.worlds, assembly_uuid, lambda w: _remove_or_release(
        w, scene, d.worlds.remove))
    _remove_tagged(d.lights, assembly_uuid, lambda l: d.lights.remove(l))

    registry.remove(scene, assembly_uuid)

    if delete_cache:
        remove_cache(assembly_uuid)

    _prune_empty(scene)


def _prune_empty(scene):
    """Drop the root collection and an unused obstacles collection."""
    from . import naming, obstacles
    for root in list(scene.collection.children):
        if root.get(naming.ROOT_PROP) and not root.children and not root.objects:
            bpy.data.collections.remove(root)
    obstacles.prune(scene)


def _owner_uuids():
    found = set()
    for coll in _TAGGED_COLLECTIONS:
        for id_block in getattr(bpy.data, coll):
            v = id_block.get(C.OWNER_PROP, "")
            if isinstance(v, str) and ":" in v:
                found.add(v.rsplit(":", 1)[1])
    return found


def guarded_create(execute):
    """Decorator for Create operators.

    An operator that returns CANCELLED (or raises) does NOT roll back what
    it already built, and a half-built assembly has no registry entry — so
    no Delete button.  On failure, sweep every assembly uuid that appeared
    during this call through the normal teardown.
    """
    @functools.wraps(execute)
    def wrapper(self, context):
        before = _owner_uuids()
        from . import errors, handlers
        handlers.note_range(context.scene)  # a tank may extend the timeline
        count = len(context.scene.aqs_assemblies)
        try:
            result = execute(self, context)
        except Exception as exc:
            result = errors.fail(self, errors._operator_title(self), exc)
        if "CANCELLED" in result:
            for u in _owner_uuids() - before:
                delete_assembly(context.scene, u)
        elif len(context.scene.aqs_assemblies) > count:
            from . import quality
            quality.apply_tier(context.scene)
            from ..ui import beta
            beta.notify_created(context.scene.aqs_assemblies[-1].mode)
            from .presets import LIQUID_MODES
            if context.scene.aqs_assemblies[-1].mode in LIQUID_MODES:
                self.report({'INFO'}, 'Change the look in the setup box')
        return result
    return wrapper
