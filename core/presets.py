# SPDX-License-Identifier: GPL-3.0-or-later
"""One-shot liquid presets. Saved setups retain values, never live recipes."""
import contextlib
import json
from functools import lru_cache

import bpy
from bpy.app.handlers import persistent

from .. import constants as C
from . import registry

LIQUID_MODES = (C.MODE_STILL, C.MODE_SIMRAIN, C.MODE_HOSE, C.MODE_SIMOCEAN)
_applying = set()


def _package(mode, label, resolution=96, draft=True, foam=0.0, spray=0.0,
             bubbles=0.0, viscosity=0.0, flip=0.97, tension=0.0, **values):
    props = dict(base_resolution=resolution, draft=draft, ww_budget=1.0,
                 ww_spray=spray > 0, ww_foam=foam > 0, ww_bubbles=bubbles > 0,
                 ww_spray_amount=spray or 0.5, ww_foam_amount=foam or 0.5,
                 ww_bubbles_amount=bubbles or 0.5,
                 ww_spray_size=0.012, ww_foam_size=0.018, ww_bubbles_size=0.009)
    props.update(values)
    return dict(mode=mode, label=label, entry=props, domain={
        'use_viscosity': viscosity > 0, 'viscosity_value': viscosity,
        'use_diffusion': False, 'surface_tension': tension,
        'use_flip_particles': True, 'flip_ratio': flip,
        'particle_radius': 1.0, 'particle_randomness': 0.1})


CATALOG = {
    'STILL_CALM': _package(C.MODE_STILL, 'Calm Pour', flip=0.8, draft=False),
    'STILL_SPLASHY': _package(C.MODE_STILL, 'Splashy', resolution=128, draft=False,
                              foam=0.65, spray=0.4, bubbles=0.25, flip=0.99),
    'STILL_THICK': _package(C.MODE_STILL, 'Thick', draft=False, viscosity=0.05, flip=0.65),
    'RAIN_DRIZZLE': _package(C.MODE_SIMRAIN, 'Drizzle', rain_density=2.0,
                            rain_speed=5.0, splash_amount=0.03),
    'RAIN_RAIN': _package(C.MODE_SIMRAIN, 'Rain', rain_density=6.0,
                         rain_speed=9.0, splash_amount=0.1),
    'RAIN_STORM': _package(C.MODE_SIMRAIN, 'Storm', resolution=128, draft=False,
                          foam=0.6, spray=0.5, bubbles=0.2, rain_density=18.0,
                          rain_speed=15.0, splash_amount=0.25),
    'HOSE_GARDEN': _package(C.MODE_HOSE, 'Garden', regime='NORMAL', pressure=0.7,
                           spread=6.0, nozzle_radius=0.03, hose_liquid=True),
    'HOSE_FIRE': _package(C.MODE_HOSE, 'Fire Hose', resolution=160, draft=False,
                         spray=0.8, foam=0.6, bubbles=0.3, regime='BLAST',
                         pressure=1.2, spread=3.0, nozzle_radius=0.05, hose_liquid=True),
    'HOSE_SPRINKLER': _package(C.MODE_HOSE, 'Sprinkler', draft=False, spray=0.55,
                              foam=0.25, regime='SPRAY', pressure=0.5,
                              spread=25.0, nozzle_radius=0.025, hose_liquid=True),
    # Calm and Rolling need ~12 cm cells: at Draft resolution 48 a cell is
    # 42 cm, larger than the waves (measured: both read as settling slosh).
    'OCEAN_CALM': _package(C.MODE_SIMOCEAN, 'Calm', resolution=160, draft=False,
                          wave_height=0.12,
                          wave_period=3.5, tank_size=(20.0, 8.0, 4.0)),
    'OCEAN_ROLLING': _package(C.MODE_SIMOCEAN, 'Rolling Waves', resolution=160,
                             draft=False, wave_height=0.45,
                             wave_period=2.4, tank_size=(20.0, 8.0, 4.0)),
    'OCEAN_STORM': _package(C.MODE_SIMOCEAN, 'Storm Surf', resolution=160, draft=False,
                           spray=0.8, foam=0.85, bubbles=0.4, wave_height=0.9,
                           wave_period=1.5, tank_size=(20.0, 8.0, 4.0)),
}
DEFAULTS = {C.MODE_STILL: 'STILL_CALM', C.MODE_SIMRAIN: 'RAIN_RAIN',
            C.MODE_HOSE: 'HOSE_GARDEN', C.MODE_SIMOCEAN: 'OCEAN_ROLLING'}
# Keep enum strings and lists alive for Blender's dynamic-enum API.
ITEMS = {mode: [(key, p['label'], 'Apply an editable starting point', i + 1)
                for i, (key, p) in enumerate(CATALOG.items()) if p['mode'] == mode]
         for mode in LIQUID_MODES}
CHOICES = {mode: [('CUSTOM', 'Custom', 'No preset selected', 0)] + items
           for mode, items in ITEMS.items()}
CUSTOM_ITEMS = [('CUSTOM', 'Custom', 'No preset selected', 0)]


def preset_items(self, _context):
    return CHOICES.get(self.mode, CUSTOM_ITEMS)


@contextlib.contextmanager
def applying(entry):
    nested = entry.uuid in _applying
    _applying.add(entry.uuid)
    try:
        yield
    finally:
        if not nested:
            _applying.discard(entry.uuid)


def busy(entry):
    return entry.uuid in _applying


def scene_for(entry):
    return entry.id_data if isinstance(entry.id_data, bpy.types.Scene) else bpy.context.scene


def domain(entry):
    from ..level2 import still_water as sw
    obj = sw.find_domain_object(entry)
    mod = next((m for m in obj.modifiers if m.type == 'FLUID' and m.fluid_type == 'DOMAIN'), None) if obj else None
    return obj, mod.domain_settings if mod else None


def _value(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (str, bool, int)):
        return value
    return [_value(v) for v in value]


def snapshot(entry, fields):
    _obj, ds = domain(entry)
    return {kind: {name: _value(getattr(entry if kind == 'entry' else ds, name))
                   for name in names if hasattr(entry if kind == 'entry' else ds, name)}
            for kind, names in fields.items()}


@lru_cache(maxsize=256)
def _decoded_snapshot(encoded):
    return json.loads(encoded)


def is_modified(entry):
    if entry.preset_modified:
        return True
    if not entry.preset_id or not entry.preset_snapshot:
        return False
    try:
        saved = _decoded_snapshot(entry.preset_snapshot)
        return snapshot(entry, saved) != saved
    except (ValueError, TypeError):
        return True


def note_edit(entry):
    if not entry.preset_modified and not busy(entry) and entry.preset_id and is_modified(entry):
        entry['preset_modified'] = True


@persistent
def on_depsgraph(scene, _depsgraph=None):
    # Catch edits made in Blender's Physics panel as well as our callbacks.
    # Compare with saved values, not the current catalogue definitions.
    changed = ({u.id.original.as_pointer() for u in _depsgraph.updates}
               if _depsgraph is not None else None)
    for entry in getattr(scene, 'aqs_assemblies', []):
        if entry.preset_id and not entry.preset_modified:
            obj, _ds = domain(entry)
            if changed is not None and scene.as_pointer() not in changed and (
                    obj is None or obj.as_pointer() not in changed):
                continue
            note_edit(entry)


@persistent
def reset_cache(_dummy=None):
    _decoded_snapshot.cache_clear()


def register():
    if on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if reset_cache not in handlers:
            handlers.append(reset_cache)


def unregister():
    if on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph)
    _applying.clear()
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if reset_cache in handlers:
            handlers.remove(reset_cache)
    reset_cache()


def apply(context, entry, preset_id):
    from . import bakes, whitewater
    from ..level2 import rain_sim, simulated_ocean
    from ..level2.still_water import set_flag
    from ..level3 import hose
    package = CATALOG.get(preset_id)
    if package is None or package['mode'] != entry.mode:
        raise RuntimeError('Choose a preset for this liquid mode.')
    if bakes.is_baking(entry):
        raise RuntimeError('Stop the current bake before applying a preset.')
    _obj, ds = domain(entry)
    if ds is None:
        raise RuntimeError('This setup has no liquid domain.')
    missing = [name for name in package['domain'] if not hasattr(ds, name)]
    if missing:
        raise RuntimeError('This Blender cannot apply the preset fields: ' + ', '.join(missing))
    with applying(entry):
        whitewater.initialize(entry)
        entry.ww_managed = True
        for name, value in package['entry'].items():
            setattr(entry, name, value)
        if entry.mode == C.MODE_HOSE:
            hose.fit_domain(context, entry)
            hose.apply_regime(context, entry)
        elif entry.mode == C.MODE_SIMRAIN:
            rain_sim.fit_domain(context, entry)
            rain_sim.apply_rain_params(context, entry)
            rain_sim.apply_quality(context, entry)
        elif entry.mode == C.MODE_SIMOCEAN:
            simulated_ocean.apply_settings(context, entry)
        else:
            ds.resolution_max = max(16, entry.base_resolution // 2) if entry.draft else entry.base_resolution
        for name, value in package['domain'].items():
            if isinstance(value, bool):
                set_flag(ds, name, value)
            else:
                setattr(ds, name, value)
        whitewater.apply(entry, force=True)
        fields = {'entry': list(package['entry']), 'domain': list(package['domain']) + [
            'resolution_max', 'mesh_scale', 'use_spray_particles', 'use_foam_particles',
            'use_bubble_particles', 'sndparticle_sampling_wavecrest',
            'sndparticle_sampling_trappedair', 'sndparticle_potential_min_wavecrest',
            'sndparticle_potential_max_wavecrest', 'sndparticle_potential_min_trappedair',
            'sndparticle_potential_max_trappedair', 'sndparticle_potential_min_energy',
            'sndparticle_potential_max_energy']}
        entry.preset_snapshot = json.dumps(snapshot(entry, fields), sort_keys=True)
        entry.preset_id = preset_id
        entry.preset_label = package['label']
        entry.preset_choice = preset_id
        entry.preset_modified = False


class AQS_OT_apply_preset(bpy.types.Operator):
    bl_idname = 'aquasuite.apply_preset'
    bl_label = 'Apply Preset'
    bl_description = 'Replace the preset settings; existing bake files are kept. Bake Again to update'
    bl_options = {'REGISTER', 'UNDO'}
    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {'CANCELLED'}
        apply(context, entry, entry.preset_choice)
        self.report({'INFO'}, f'{entry.preset_label} applied — Bake Again to see the result')
        return {'FINISHED'}


CLASSES = (AQS_OT_apply_preset,)
