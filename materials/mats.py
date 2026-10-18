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


AOV_NAMES = {'liquid': 'AQS_Liquid', 'spray': 'AQS_Spray',
             'foam': 'AQS_Foam', 'bubbles': 'AQS_Bubbles'}


def element_aov(mat, element, value_socket=None):
    """Idempotent scalar mask; separate materials supply Cryptomatte IDs."""
    if not mat.use_nodes:
        return
    nt = mat.node_tree
    node = next((n for n in nt.nodes if n.type == 'OUTPUT_AOV'
                 and n.get('aqs_aov_element') == element), None)
    if node is None:
        node = nt.nodes.new('ShaderNodeOutputAOV')
        node['aqs_aov_element'] = element
    if hasattr(node, 'aov_name'):
        node.aov_name = AOV_NAMES[element]
    else:
        node.name = AOV_NAMES[element]  # older 4.x API
    if node.inputs['Value'].default_value != 1.0:
        node.inputs['Value'].default_value = 1.0
    if value_socket is not None:
        nt.links.new(value_socket, node.inputs['Value'])


def whitewater(mode, uuid_, element):
    mat = _new_mat('AQS_' + element.title(), mode, uuid_)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    if element == 'foam':
        shader = nt.nodes.new('ShaderNodeBsdfDiffuse')
        shader.inputs['Color'].default_value = (0.93, 0.97, 1.0, 1.0)
        shader.inputs['Roughness'].default_value = 0.6
    else:
        shader = nt.nodes.new('ShaderNodeBsdfGlass')
        shader.inputs['IOR'].default_value = 1.33
        shader.inputs['Roughness'].default_value = 0.08
    info = nt.nodes.new('ShaderNodeObjectInfo')
    mask = nt.nodes.new('ShaderNodeMath')
    mask.operation = 'LESS_THAN'
    mask['aqs_amount'] = True
    mask.inputs[1].default_value = 1.0
    nt.links.new(info.outputs['Random'], mask.inputs[0])
    transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(mask.outputs[0], mix.inputs[0])
    nt.links.new(transparent.outputs[0], mix.inputs[1])
    nt.links.new(shader.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    element_aov(mat, element, mask.outputs[0])
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED'
    elif hasattr(mat, 'blend_method'):
        mat.blend_method = 'HASHED'
    return mat


def whitewater_amount(mat, fraction):
    nt = mat.node_tree
    for node in nt.nodes:
        if node.get('aqs_amount'):
            value = max(0.0, min(1.0, fraction))
            if node.inputs[1].default_value != value:
                node.inputs[1].default_value = value
            # Full-density elements need neither random thinning nor a
            # transparent closure. Keep the branch available for later edits.
            mix = next((l.to_node for l in node.outputs[0].links
                        if l.to_node.type == 'MIX_SHADER'), None)
            if mix and mix.inputs[2].links:
                shader = mix.inputs[2].links[0].from_node
                target = shader.outputs[0] if value >= 1.0 else mix.outputs[0]
                for out in nt.nodes:
                    if out.type == 'OUTPUT_MATERIAL':
                        socket = out.inputs['Surface']
                        if socket.links and socket.links[0].from_node in (mix, shader):
                            if socket.links[0].from_socket != target:
                                nt.links.new(target, socket)
            for out in nt.nodes:
                if out.type == 'OUTPUT_AOV' and out.get('aqs_aov_element'):
                    socket = out.inputs['Value']
                    if value >= 1.0:
                        for link in list(socket.links):
                            if link.from_node == node:
                                nt.links.remove(link)
                    elif not socket.links:
                        nt.links.new(node.outputs[0], socket)
