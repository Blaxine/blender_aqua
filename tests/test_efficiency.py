# SPDX-License-Identifier: GPL-3.0-or-later
"""No-bake checks for efficiency changes, in an isolated Blender process."""
import os
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib
import bpy
from aquasuite.core import whitewater, presets, memory
from aquasuite.level1 import ocean
from aquasuite.level2 import rain_sim, simulated_ocean


def test_rain_instances_and_preview():
    assert bpy.ops.aquasuite.rain_sim_create() == {'FINISHED'}
    entry = lib.entry(lib.last_uuid())
    visible = rain_sim.find_rain_drops(entry)
    emitter = rain_sim.find_emitter(entry)
    vm = rain_sim._drops_modifier(visible, entry.uuid)
    em = rain_sim._drops_modifier(emitter, entry.uuid)
    bpy.context.scene.aqs_quality = 'PREVIEW'
    lib.check('Preview changes visible fraction only',
              ocean.get_input(vm, 'Viewport Fraction') == .25 and
              ocean.get_input(em, 'Viewport Fraction') == 1)
    tree = vm.node_group
    switch = next(n for n in tree.nodes if n.type == 'SWITCH' and n.input_type == 'GEOMETRY')
    lib.check('visible output stays instanced',
              switch.inputs['False'].links[0].from_node.type == 'SCALE_INSTANCES' and
              switch.inputs['True'].links[0].from_node.type == 'REALIZE_INSTANCES')
    bpy.context.scene.aqs_quality = 'FINAL'
    lib.check('Final restores visible fraction', ocean.get_input(vm, 'Viewport Fraction') == 1)
    # Emulate the old socket interface on a separate visible tree. The upgrade
    # must keep the source tree, visible input values, and material ownership.
    previous_source = em.node_group
    old = vm.node_group.copy()
    vm.node_group = old
    socket = next(s for s in old.interface.items_tree if s.name == 'Viewport Fraction')
    old.interface.remove(socket)
    ocean.set_input(vm, 'Density', 13.0)
    result = bpy.ops.aquasuite.rain_sim_optimize(uuid=entry.uuid)
    lib.check('existing visible rain upgrade preserves input and emitter',
              result == {'FINISHED'} and ocean.get_input(vm, 'Density') == 13.0 and
              em.node_group == previous_source and ocean.get_input(vm, 'Viewport Fraction') == 1)
    upgraded = vm.node_group
    bpy.ops.aquasuite.rain_sim_optimize(uuid=entry.uuid)
    lib.check('rain optimization is idempotent', vm.node_group == upgraded)
    bpy.ops.aquasuite.assembly_delete(uuid=entry.uuid)


def test_narrow_updates_and_budget():
    assert bpy.ops.aquasuite.simulated_ocean_create(preset='OCEAN_STORM') == {'FINISHED'}
    entry = lib.entry(lib.last_uuid())
    dom, ds = presets.domain(entry)
    original = whitewater.apply
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    whitewater.apply = counted
    try:
        entry.base_resolution = 96
        lib.check('one whitewater application per resolution edit', len(calls) == 1, str(len(calls)))
        calls.clear()
        before = (tuple(dom.scale), ds.resolution_max, ds.sndparticle_sampling_wavecrest)
        entry.ww_foam_size = .027
        entry.wave_period = 3.1
        after = (tuple(dom.scale), ds.resolution_max, ds.sndparticle_sampling_wavecrest)
        lib.check('Size and Period skip full whitewater and domain writes', not calls and before == after)
    finally:
        whitewater.apply = original
    entry.ww_budget = 0
    lib.check('zero budget suspends systems without losing choices',
              entry.ww_foam and entry.ww_spray and not ds.use_foam_particles and not ds.use_spray_particles)
    bpy.context.scene.aqs_quality = 'PREVIEW'
    entry.ww_budget = .2
    lib.check('recreated whitewater inherits Preview',
              all(p.settings.display_percentage <= 25 for p in dom.particle_systems
                  if p.settings.get(whitewater.ROLE)))
    # 200 x 0.2 = 40, and ocean tanks sample a quarter of that (whitewater.apply).
    lib.check('budget reduces shared generation', ds.sndparticle_sampling_wavecrest == 10,
              str(ds.sndparticle_sampling_wavecrest))
    foam = whitewater._instance(entry, 'foam').data.materials[0]
    out = next(n for n in foam.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
    lib.check('full-density whitewater bypasses transparency mix',
              out.inputs['Surface'].links[0].from_node.type == 'BSDF_DIFFUSE')
    entry.ww_foam_amount = .1
    lib.check('relative density restores thinning branch',
              out.inputs['Surface'].links[0].from_node.type == 'MIX_SHADER')
    allowance = memory.assembly(entry)
    lib.check('memory allowance includes mesh and secondaries',
              allowance['mesh'] > 0 and allowance['secondary'] > 0 and allowance['high'] > allowance['grid'])
    bpy.ops.aquasuite.assembly_delete(uuid=entry.uuid)
    bpy.context.scene.aqs_quality = 'FINAL'


def test_preset_native_edits():
    assert bpy.ops.aquasuite.simulated_ocean_create() == {'FINISHED'}
    entry = lib.entry(lib.last_uuid())
    _dom, ds = presets.domain(entry)
    ds.flip_ratio = .72
    bpy.context.view_layer.update()
    lib.check('native Physics edit marks preset modified', entry.preset_modified)
    bpy.ops.aquasuite.assembly_delete(uuid=entry.uuid)


def test_registration_restricted():
    try:
        from _bpy_restrict_state import RestrictBlend
    except ImportError:
        lib.skip('restricted registration', 'this Blender has no _bpy_restrict_state')
        return
    lib.aq.unregister()
    with RestrictBlend():
        lib.aq.register()
    lib.check('restricted registration succeeds', hasattr(bpy.types.Scene, 'aqs_assemblies'))
    lib.aq.unregister()


lib.main(globals())
