# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import aqs_testlib as lib
import bpy
from aquasuite.ui import control_spec
from aquasuite.level1 import ocean


def test_all_modes_and_one_click():
    lib.check('spec covers all modes', set(control_spec.SIMPLE) == set(lib.C.MODE_LABELS))
    for operator in ('still_water_create', 'rain_sim_create', 'hose_create'):
        if operator == 'still_water_create':
            lib.make_active(lib.add_cube())
        result = getattr(bpy.ops.aquasuite, operator)('INVOKE_DEFAULT')
        lib.check(operator + ' invokes immediately', result == {'FINISHED'})
    lib.check('all Simple hides advanced panel controls', not control_spec.advanced_visible(lib.scene().aqs_assemblies))
    lib.scene().aqs_assemblies[0].show_advanced = True
    lib.check('one Advanced enables panel controls', control_spec.advanced_visible(lib.scene().aqs_assemblies))


def test_spec_and_default():
    for mode, simple in control_spec.SIMPLE.items():
        lib.check(mode + ': Simple included in Advanced', set(simple) <= set(control_spec.ADVANCED[mode]))
        for token in control_spec.ADVANCED[mode]:
            if token.startswith('entry:'):
                assert token.split(':')[1] in lib.registry.AQS_AssemblyEntry.bl_rna.properties
            elif token.startswith('ocean:'):
                assert token.split(':')[1] in {s[0] for s in ocean.INPUTS}
            elif token.startswith('particles:'):
                assert token.split(':')[1] in bpy.types.ParticleSettings.bl_rna.properties
    result = bpy.ops.aquasuite.simulated_ocean_create('INVOKE_DEFAULT')
    entry = lib.entry(lib.last_uuid())
    lib.check('ocean invokes immediately with default preset', result == {'FINISHED'} and entry.preset_id == 'OCEAN_ROLLING')
    lib.check('new box defaults Simple', not entry.show_advanced)
    entry.show_advanced = True
    uid = entry.uuid
    path = lib.save_blend('simple_view')
    bpy.ops.wm.open_mainfile(filepath=bpy.data.filepath)
    lib.check('Advanced survives save/reload', lib.entry(uid).show_advanced)


lib.main(globals())
