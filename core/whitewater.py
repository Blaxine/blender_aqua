# SPDX-License-Identifier: GPL-3.0-or-later
"""Whitewater ownership, legacy adoption and renderer-ready particle instances."""
import bpy
import bmesh
from bpy.app.handlers import persistent

from .. import constants as C
from . import naming

ELEMENTS = ('spray', 'foam', 'bubbles')
NAMES = {'spray': 'Spray', 'foam': 'Foam', 'bubbles': 'Bubbles'}
FLAGS = {'spray': 'use_spray_particles', 'foam': 'use_foam_particles',
         'bubbles': 'use_bubble_particles'}
ROLE = 'aqs_whitewater_element'
SIZES = {'spray': 0.012, 'foam': 0.018, 'bubbles': 0.009}


def _systems(dom, entry, element):
    tagged = [p for p in dom.particle_systems if p.settings
              and naming.owned_by(p.settings, entry.uuid)
              and p.settings.get(ROLE) == element]
    if tagged:
        return tagged
    return [p for p in dom.particle_systems if p.name == NAMES[element]]


def initialize(entry):
    """Read legacy solver state into metadata only; never write the domain."""
    if entry.ww_initialized:
        return
    from .presets import domain
    dom, ds = domain(entry)
    if ds is None:
        return
    for element in ELEMENTS:
        entry['ww_' + element] = bool(getattr(ds, FLAGS[element]))
        entry['ww_' + element + '_amount'] = 0.5
        systems = _systems(dom, entry, element)
        size = systems[0].settings.particle_size if systems and systems[0].settings.render_type == 'OBJECT' else SIZES[element]
        entry['ww_' + element + '_size'] = max(size, 0.0001)
    if entry.mode == C.MODE_STILL:
        # Draft did not affect Still Water before these controls existed.
        entry['draft'] = False
    entry['ww_initialized'] = True


def seed_regime(entry):
    initialize(entry)
    enabled = entry.regime == C.REGIME_SPRAY
    for element in ELEMENTS:
        entry['ww_' + element] = enabled
    entry.ww_managed = True


def _instance(entry, element):
    from ..materials import mats
    col = entry.root_collection
    if col is None:
        raise RuntimeError('The assembly collection is missing.')
    obj = next((o for o in col.all_objects if naming.owned_by(o, entry.uuid)
                and o.get(ROLE) == element), None)
    if obj is None:
        mesh = bpy.data.meshes.new('AQS_' + NAMES[element] + '_Instance')
        bm = bmesh.new()
        try:
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
            bm.to_mesh(mesh)
        finally:
            bm.free()
        obj = naming.new_mesh_object(col, mesh.name, mesh, entry.mode, entry.uuid)
        obj[ROLE] = element
        obj.hide_render = True
        obj.hide_set(True)
        mats.assign(obj, mats.whitewater(entry.mode, entry.uuid, element))
    return obj


def _set(obj, name, value):
    if getattr(obj, name) != value:
        setattr(obj, name, value)


def apply_sizes(entry):
    from .presets import domain
    dom, ds = domain(entry)
    if ds is None:
        return
    for element in ELEMENTS:
        for system in _systems(dom, entry, element):
            _set(system.settings, 'particle_size', getattr(entry, 'ww_' + element + '_size'))


def apply(entry, force=False):
    from . import presets
    if presets.busy(entry) and not force:
        return  # Preset application performs one final update after all writes.
    from ..level2.still_water import set_flag
    from ..materials import mats
    initialize(entry)
    if not entry.ww_managed:
        return  # Loading/editing an old scene must not add render geometry.
    dom, ds = presets.domain(entry)
    if ds is None:
        return
    active = {e: bool(getattr(entry, 'ww_' + e)) and not entry.draft and entry.ww_budget > 0
              and getattr(entry, 'ww_' + e + '_amount') > 0 for e in ELEMENTS}
    from . import render_layers
    render_layers.setup_materials(entry)
    if ds.sndparticle_combined_export != 'OFF':
        entry.ww_warning = 'Set secondary particle export to separate systems before using Whitewater controls.'
        return
    # Names are needed only for first discovery; our role tag survives renames.
    missing = []
    removed_settings = []
    for element in ELEMENTS:
        old = _systems(dom, entry, element)
        was_on = bool(getattr(ds, FLAGS[element]))
        if was_on and not old:
            missing.append(NAMES[element])
            continue  # Do not guess which renamed legacy system is ours.
        for system in old:
            naming.tag(system.settings, entry.mode, entry.uuid)
            if system.settings.get(ROLE) != element:
                system.settings[ROLE] = element
            if was_on and not active[element]:
                removed_settings.append(system.settings)
        set_flag(ds, FLAGS[element], active[element])
        systems = _systems(dom, entry, element)
        if active[element] and not systems:
            missing.append(NAMES[element])
            continue
        for system in systems:
            ps = system.settings
            naming.tag(ps, entry.mode, entry.uuid)
            if ps.get(ROLE) != element:
                ps[ROLE] = element
            obj = _instance(entry, element)
            _set(ps, 'render_type', 'OBJECT')
            _set(ps, 'instance_object', obj)
            _set(ps, 'particle_size', getattr(entry, 'ww_' + element + '_size'))
            _set(ps, 'size_random', 0.4)
            from . import quality
            quality.apply_particle_tier(presets.scene_for(entry), ps)
    # Remove only orphan settings we identified before the toggle.  Mantaflow
    # deletes the particle system without lowering the settings' user count
    # (it stays 1), so "unused" means no particle system references it.
    if removed_settings:
        referenced = {p.settings for o in bpy.data.objects for p in o.particle_systems
                      if p.settings is not None}
        for ps in removed_settings:
            if ps not in referenced and naming.owned_by(ps, entry.uuid)                     and ps.get(ROLE) in ELEMENTS:
                bpy.data.particles.remove(ps)
    amounts = {e: getattr(entry, 'ww_' + e + '_amount') if active[e] else 0.0 for e in ELEMENTS}
    maximum = max(amounts.values())
    amount = min(maximum, entry.ww_budget)
    if amount > 0:
        # Mantaflow has one spawn budget for all elements. Per-element
        # deterministic shader thinning below supplies independent Amount.
        values = dict(sndparticle_potential_min_wavecrest=2.5 * (1.0 - amount),
                      sndparticle_potential_max_wavecrest=8.0 - 5.0 * amount,
                      sndparticle_potential_min_trappedair=5.0 * (1.0 - amount),
                      sndparticle_potential_max_trappedair=20.0 - 12.0 * amount,
                      sndparticle_potential_min_energy=1.0 - 0.9 * amount,
                      sndparticle_potential_max_energy=5.0 - 3.0 * amount,
                      sndparticle_sampling_wavecrest=max(1, round(200 * amount)),
                      sndparticle_sampling_trappedair=max(1, round(40 * amount)))
        for name, value in values.items():
            _set(ds, name, value)
    for element in ELEMENTS:
        if active[element]:
            obj = _instance(entry, element)
            for mat in obj.data.materials:
                if mat and naming.owned_by(mat, entry.uuid):
                    mats.whitewater_amount(mat, amounts[element] / max(maximum, 1e-6))
    entry.ww_warning = ('Cannot identify ' + ', '.join(missing)
                        + '. Restore the original particle-system names, then edit Whitewater again.') if missing else ''


@persistent
def on_load(_dummy=None):
    from .presets import LIQUID_MODES
    for scene in bpy.data.scenes:
        for entry in getattr(scene, 'aqs_assemblies', []):
            if entry.mode in LIQUID_MODES:
                try:
                    initialize(entry)
                except Exception as exc:
                    from . import errors
                    errors.record("AquaSuite couldn't read the existing whitewater settings", exc,
                                  mode=entry.mode, uuid=entry.uuid)
                    errors.schedule()


def _initialize_after_register():
    # Add-on enable runs inside Blender's RestrictBlend context. Scene data
    # becomes available after register() returns to the event loop.
    if not hasattr(bpy.data, 'scenes'):
        return 0.1
    on_load()
    return None


def register():
    if on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load)
    if not bpy.app.timers.is_registered(_initialize_after_register):
        bpy.app.timers.register(_initialize_after_register, first_interval=0.0)


def unregister():
    if bpy.app.timers.is_registered(_initialize_after_register):
        bpy.app.timers.unregister(_initialize_after_register)
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
