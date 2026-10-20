# SPDX-License-Identifier: GPL-3.0-or-later
"""Material Cryptomatte and four scalar AOVs on the active view layer."""
import bpy

from . import naming, presets
from ..materials import mats


def setup_materials(entry):
    dom, _ds = presets.domain(entry)
    if dom is None:
        return
    for slot in dom.material_slots:
        mat = slot.material
        if mat is not None and naming.owned_by(mat, entry.uuid):
            mats.element_aov(mat, 'liquid')


class AQS_OT_render_layers(bpy.types.Operator):
    bl_idname = 'aquasuite.setup_render_layers'
    bl_label = 'Set Up Render Layers'
    bl_description = 'Enable Material Cryptomatte and Liquid, Spray, Foam, Bubbles AOV masks on the active view layer'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        layer = context.view_layer
        names = tuple(mats.AOV_NAMES.values())
        conflicts = [a.name for a in layer.aovs if a.name in names and a.type != 'VALUE']
        if conflicts:
            raise RuntimeError('Rename existing Color AOVs before setup: ' + ', '.join(conflicts))
        changed = []
        if not layer.use_pass_cryptomatte_material:
            layer.use_pass_cryptomatte_material = True
            changed.append('Material Cryptomatte')
        for name in names:
            if not any(a.name == name for a in layer.aovs):
                aov = layer.aovs.add()
                aov.name = name
                aov.type = 'VALUE'
                changed.append(name)
        for entry in context.scene.aqs_assemblies:
            if entry.mode in presets.LIQUID_MODES:
                setup_materials(entry)
        self.report({'INFO'}, ('Enabled ' + ', '.join(changed) if changed
                              else 'Render layers already configured')
                    + ' on ' + layer.name)
        return {'FINISHED'}


CLASSES = (AQS_OT_render_layers,)
