# SPDX-License-Identifier: GPL-3.0-or-later
"""Reversible teardown (TDD §4.3 / core/delete).

Deletion trusts ONLY the ``aqs_owner`` UUID tag — never names.  Tracked
mutations of user data (buoy constraints, source visibility, refcounted
effector modifiers) are restored from their recorded pre-state first,
then every tagged ID is removed.
"""

import json

import bpy

from .. import constants as C
from . import registry


def _restore_buoys(entry):
    for b in entry.buoys:
        obj = b.obj
        if obj is None:
            continue
        names = [n for n in (b.added_constraints or "").split(";") if n]
        for n in names:
            con = obj.constraints.get(n)
            if con is not None:
                obj.constraints.remove(con)


def _restore_one_source(src, uuid):
    if src is None:
        return
    src.hide_render = False  # overwritten below by the recorded value
    for mod in list(src.modifiers):
        if mod.type == "FLUID" and mod.name.startswith("AQS"):
            src.modifiers.remove(mod)
    for prop in (C.SRC_PROP, C.OWNER_PROP):
        if str(src.get(prop, "")).endswith(uuid):
            del src[prop]


def _restore_source(entry):
    # Rain-Sim pool sources (each with its own recorded pre-state)
    for rec in getattr(entry, "pool_sources", []):
        src = rec.obj
        if src is None:
            continue
        _restore_one_source(src, entry.uuid)
        src.hide_render = rec.hide_render
        try:
            src.display_type = rec.display_type or "TEXTURED"
        except TypeError:
            src.display_type = "TEXTURED"

    src = entry.source
    if src is None:
        return
    src.hide_render = entry.src_hide_render
    try:
        src.display_type = entry.src_display_type or "TEXTURED"
    except TypeError:
        src.display_type = "TEXTURED"
    # Remove ONLY the Flow modifier AquaSuite added to the source (by our
    # modifier name — a user Fluid modifier can't exist here, since Create
    # refuses sources that already carry one, R1.4).
    for mod in list(src.modifiers):
        if mod.type == "FLUID" and mod.name.startswith("AQS"):
            src.modifiers.remove(mod)
    for prop in (C.SRC_PROP, C.OWNER_PROP):
        if str(src.get(prop, "")).endswith(entry.uuid):
            del src[prop]


def _release_effectors(assembly_uuid):
    """Decrement effector refcounts; remove modifiers whose owner list empties
    (R1.4 / §5.3b)."""
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
                    and getattr(mod, "fluid_type", "") == "EFFECTOR"
                    and mod.name.startswith("AQS")):
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


def delete_assembly(scene, assembly_uuid):
    entry = registry.get(scene, assembly_uuid)
    if entry is not None:
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

    registry.remove(scene, assembly_uuid)

    # Prune the root collection if it is now empty.
    root = d.collections.get(C.ROOT_COLLECTION)
    if root is not None and not root.children and not root.objects:
        d.collections.remove(root)
