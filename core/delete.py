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


def _restore_source(entry):
    # Rain-Sim pool sources (each with its own recorded pre-state)
    for rec in getattr(entry, "pool_sources", []):
        _restore_one_source(rec.obj, entry.uuid, rec.hide_render,
                            rec.display_type)
    _restore_one_source(entry.source, entry.uuid, entry.src_hide_render,
                        entry.src_display_type)


def _release_effectors(assembly_uuid):
    """Decrement effector refcounts; remove modifiers whose owner list empties
    (R1.4 / §5.3b).

    The owner list is only ever written on objects whose Effector AquaSuite
    created, so the modifier is identified by type — renaming it no longer
    strands it on the user's object.
    """
    for obj in bpy.data.objects:
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

def delete_assembly(scene, assembly_uuid, delete_cache=False):
    entry = registry.get(scene, assembly_uuid)
    if entry is not None:
        from . import lighting
        lighting.restore(scene, entry)
        _restore_buoys(entry)
        _restore_source(entry)
    _release_effectors(assembly_uuid)

    d = bpy.data
    _remove_tagged(d.objects, assembly_uuid, lambda o: d.objects.remove(o, do_unlink=True))
    _remove_tagged(d.meshes, assembly_uuid, lambda m: d.meshes.remove(m))
    _remove_tagged(d.particles, assembly_uuid, lambda p: d.particles.remove(p))
    _remove_tagged(d.node_groups, assembly_uuid, lambda n: d.node_groups.remove(n))
    _remove_tagged(d.materials, assembly_uuid, lambda m: d.materials.remove(m))
    _remove_tagged(d.collections, assembly_uuid, lambda c: d.collections.remove(c))
    _remove_tagged(d.actions, assembly_uuid, lambda a: d.actions.remove(a))
    _remove_tagged(d.worlds, assembly_uuid, lambda w: d.worlds.remove(w))
    _remove_tagged(d.lights, assembly_uuid, lambda l: d.lights.remove(l))

    registry.remove(scene, assembly_uuid)

    if delete_cache:
        remove_cache(assembly_uuid)

    # Prune the root collection if it is now empty.
    from . import naming
    for root in list(scene.collection.children):
        if root.get(naming.ROOT_PROP) and not root.children and not root.objects:
            d.collections.remove(root)


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
        from . import errors
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
