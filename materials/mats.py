# SPDX-License-Identifier: GPL-3.0-or-later
"""Auto-generated materials (TDD §13, mist per R1.12).

Principled socket names moved around in 4.x, so all sets go through a
name-tolerant helper.  Materials are tagged per assembly and appended to
a free slot only (never overwrite user slots).
"""

import bpy

from .. import constants as C
from ..core import naming


def _pset(node, names, value):
    for n in names:
        sock = node.inputs.get(n)
        if sock is not None:
            try:
                sock.default_value = value
                return True
            except Exception:
                pass
    return False


def _new_mat(name, mode, uuid_):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    naming.tag(mat, mode, uuid_)
    return mat


def assign(obj, mat):
    """Append to a free slot; never overwrite occupied user slots (§13)."""
    if obj.data is None or not hasattr(obj.data, "materials"):
        return
    mats = obj.data.materials
    for i, m in enumerate(mats):
        if m is None:
            mats[i] = mat
            return
    mats.append(mat)


def water_surface(mode, uuid_, name="AQS_MAT_OceanSurface", volume=True):
    mat = _new_mat(name, mode, uuid_)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    _pset(glass, ("IOR",), 1.33)
    _pset(glass, ("Roughness",), 0.02)
    _pset(glass, ("Color", "Base Color"), (0.9, 0.97, 1.0, 1.0))
    nt.links.new(glass.outputs[0], out.inputs["Surface"])
    if volume:
        absorb = nt.nodes.new("ShaderNodeVolumeAbsorption")
        _pset(absorb, ("Color",), (0.45, 0.72, 0.78, 1.0))
        _pset(absorb, ("Density",), 0.35)
        nt.links.new(absorb.outputs[0], out.inputs["Volume"])
    try:
        mat.use_screen_refraction = True  # EEVEE hint (§13.1)
    except AttributeError:
        pass
    return mat


def droplet(mode, uuid_):
    mat = _new_mat("AQS_MAT_Droplet", mode, uuid_)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    _pset(glass, ("IOR",), 1.33)
    emit = nt.nodes.new("ShaderNodeEmission")
    _pset(emit, ("Strength",), 0.02)
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(glass.outputs[0], add.inputs[0])
    nt.links.new(emit.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return mat


def ripple_floor(mode, uuid_):
    mat = _new_mat("AQS_MAT_RippleFloor", mode, uuid_)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        _pset(bsdf, ("Base Color",), (0.035, 0.04, 0.045, 1.0))
        _pset(bsdf, ("Roughness",), 0.12)
        _pset(bsdf, ("Specular IOR Level", "Specular"), 0.6)
    return mat


def snow(mode, uuid_):
    mat = _new_mat("AQS_MAT_Snow", mode, uuid_)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        _pset(bsdf, ("Base Color",), (0.92, 0.94, 0.97, 1.0))
        _pset(bsdf, ("Subsurface Weight", "Subsurface"), 0.3)
        _pset(bsdf, ("Roughness",), 0.6)
    return mat


def flake(mode, uuid_):
    mat = _new_mat("AQS_MAT_Flake", mode, uuid_)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        _pset(bsdf, ("Base Color",), (0.9, 0.95, 1.0, 1.0))
        _pset(bsdf, ("Sheen Weight", "Sheen"), 0.6)
        _pset(bsdf, ("Transmission Weight", "Transmission"), 0.15)
        _pset(bsdf, ("Roughness",), 0.35)
    return mat


def mist(mode, uuid_):
    """R1.12: view-independent spherical puff — no billboard dependency."""
    mat = _new_mat("AQS_MAT_Mist", mode, uuid_)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    _pset(lw, ("Blend",), 0.35)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.15
    ramp.color_ramp.elements[1].position = 0.9
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    transl = nt.nodes.new("ShaderNodeBsdfTranslucent")
    _pset(transl, ("Color",), (0.85, 0.9, 0.95, 1.0))
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lw.outputs["Facing"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["Fac"])
    nt.links.new(transp.outputs[0], mix.inputs[1])
    nt.links.new(transl.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    # 4.1 EEVEE legacy uses blend/shadow_method; 4.2 EEVEE Next replaced
    # them with surface_render_method. Set whichever exists.
    for attr, val in (("blend_method", "HASHED"), ("shadow_method", "NONE"),
                      ("surface_render_method", "DITHERED")):
        try:
            setattr(mat, attr, val)
        except (AttributeError, TypeError):
            pass
    return mat
