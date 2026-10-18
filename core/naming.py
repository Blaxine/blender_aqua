# SPDX-License-Identifier: GPL-3.0-or-later
"""Naming, ownership tagging, and managed-collection helpers (TDD §4.2)."""

import uuid as _uuid

import bpy

from .. import constants as C


def new_uuid():
    return _uuid.uuid4().hex


def short(u):
    return u[:8]


def owner_tag(mode, assembly_uuid):
    return f"{mode}:{assembly_uuid}"


def tag(id_block, mode, assembly_uuid):
    """Stamp any ID datablock as owned by an assembly."""
    value = owner_tag(mode, assembly_uuid)
    if id_block.get(C.OWNER_PROP) != value:
        id_block[C.OWNER_PROP] = value
    return id_block


def owned_by(id_block, assembly_uuid):
    v = id_block.get(C.OWNER_PROP, "")
    return isinstance(v, str) and v.endswith(":" + assembly_uuid)


ROOT_PROP = "aqs_assembly_root"


def ensure_root_collection(scene):
    # Reuse only this scene's managed root. Older roots can be recognized
    # by the registry's assembly collections without trusting their names.
    assemblies = {e.root_collection for e in scene.aqs_assemblies if e.root_collection}
    for root in scene.collection.children:
        managed = root.get(ROOT_PROP) or any(c in assemblies for c in root.children)
        shared = any(other != scene and root in tuple(other.collection.children_recursive)
                     for other in bpy.data.scenes)
        if managed and not shared:
            root[ROOT_PROP] = True
            return root
    root = bpy.data.collections.new(C.ROOT_COLLECTION)
    root[ROOT_PROP] = True
    scene.collection.children.link(root)
    return root


def new_assembly_collection(scene, mode, assembly_uuid):
    root = ensure_root_collection(scene)
    col = bpy.data.collections.new(f"AQS_A_{short(assembly_uuid)}")
    tag(col, mode, assembly_uuid)
    root.children.link(col)
    return col


def link_object(col, obj):
    if obj.name not in {o.name for o in col.objects}:
        col.objects.link(obj)
    # Keep assembly objects out of the scene root collection if they were
    # linked there by an operator.
    scene_col = bpy.context.scene.collection
    if obj.name in {o.name for o in scene_col.objects}:
        try:
            scene_col.objects.unlink(obj)
        except RuntimeError:
            pass
    return obj


def new_mesh_object(col, name, mesh, mode, assembly_uuid):
    obj = bpy.data.objects.new(name, mesh)
    tag(obj, mode, assembly_uuid)
    if mesh is not None:
        tag(mesh, mode, assembly_uuid)
    link_object(col, obj)
    return obj
