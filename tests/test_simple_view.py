# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import aqs_testlib as lib
import bpy
from aquasuite.ui import control_spec


def test_spec_and_default():
    for mode, simple in control_spec.SIMPLE.items():
        lib.check(mode + ': Simple included in Advanced', set(simple) <= set(control_spec.ADVANCED[mode]))
        for token in control_spec.ADVANCED[mode]:
            if token.startswith('entry:'):
                assert token.split(':')[1] in lib.registry.AQS_AssemblyEntry.bl_rna.properties
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
