# SPDX-License-Identifier: GPL-3.0-or-later
"""Ordered panel controls, shared by drawing and headless contract checks.

Groups are named UI actions; entry: and ocean: IDs bind actual properties.
Advanced lists the complete view, including Simple controls.
"""
from .. import constants as C

SIMPLE = {
    C.MODE_LIGHTING: ('entry:sun_strength', 'entry:sun_angle'),
    C.MODE_OCEAN: ('ocean:Amplitude', 'ocean:Wavelength', 'ocean:Speed', 'floaters'),
    C.MODE_RAIN: ('particles:count',),
    C.MODE_SNOW: ('particles:count',),
    C.MODE_RRAIN: ('particles:count', 'ripples'),
    C.MODE_STILL: ('preset', 'resolution_buttons', 'obstacles', 'bake'),
    C.MODE_SIMRAIN: ('preset', 'entry:rain_density', 'entry:rain_speed', 'entry:rain_angle', 'pools', 'obstacles', 'bake'),
    C.MODE_HOSE: ('regimes', 'entry:pressure', 'entry:spread', 'entry:hose_color', 'obstacles'),
    C.MODE_SIMOCEAN: ('preset', 'entry:wave_height', 'entry:wave_period', 'obstacles', 'bake'),
}
ADVANCED = {
    C.MODE_LIGHTING: ('entry:sun_strength', 'entry:sun_angle', 'lighting_details'),
    C.MODE_OCEAN: tuple('ocean:' + p for p in ('Size', 'Resolution', 'Amplitude', 'Wavelength', 'Choppiness', 'Direction', 'Spread', 'Speed')) + ('floaters',),
    C.MODE_RAIN: ('particles:count', 'particles:lifetime', 'particles:particle_size'),
    C.MODE_SNOW: ('particles:count', 'particles:lifetime', 'particles:particle_size'),
    C.MODE_RRAIN: ('particles:count', 'particles:lifetime', 'particles:particle_size', 'ripples'),
    C.MODE_STILL: ('preset', 'resolution_buttons', 'entry:draft', 'obstacles', 'fluid', 'whitewater', 'bake'),
    C.MODE_SIMRAIN: ('preset', 'entry:rain_density', 'entry:rain_speed', 'entry:rain_angle', 'entry:rain_direction', 'entry:rain_area',
                     'entry:drop_size', 'entry:splash_amount', 'entry:rain_seed', 'rain_tools', 'pools', 'obstacles', 'entry:draft', 'fluid', 'whitewater', 'bake'),
    C.MODE_HOSE: ('regimes', 'entry:pressure', 'entry:spread', 'entry:hose_color', 'entry:nozzle_radius', 'obstacles', 'hose_liquid_controls'),
    C.MODE_SIMOCEAN: ('preset', 'entry:wave_height', 'entry:wave_period',
                     'entry:tank_size', 'entry:draft', 'fluid', 'whitewater', 'obstacles', 'bake'),
}


def controls(mode, advanced=False):
    return (ADVANCED if advanced else SIMPLE).get(mode, ())


def advanced_visible(entries):
    return any(e.show_advanced for e in entries)
