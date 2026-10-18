# SPDX-License-Identifier: GPL-3.0-or-later
"""Ordered panel controls, shared by drawing and headless contract checks.

Groups are named UI actions; entry: and ocean: IDs bind actual properties.
Advanced lists the complete view, including Simple controls.
"""
from .. import constants as C

SIMPLE = {
    C.MODE_SIMOCEAN: ('preset', 'entry:wave_height', 'entry:wave_period', 'obstacles', 'bake'),
}
ADVANCED = {
    C.MODE_SIMOCEAN: ('preset', 'entry:wave_height', 'entry:wave_period',
                     'entry:tank_size', 'entry:draft', 'fluid', 'whitewater', 'obstacles', 'bake'),
}


def controls(mode, advanced=False):
    return (ADVANCED if advanced else SIMPLE).get(mode, ())


def advanced_visible(entries):
    return any(e.show_advanced for e in entries)
