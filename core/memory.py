# SPDX-License-Identifier: GPL-3.0-or-later
"""Uncalibrated planning allowances, not a prediction of Blender peak RAM."""


def liquid_allowance(cells, mesh_scale=1, elements=0):
    # Keep components explicit. Meshing allowance scales with the upsampled
    # grid; secondary allowance is intentionally broad (population is unknown).
    base = cells * 120e-9
    mesh = cells * 16e-9 * max(1, mesh_scale) ** 3
    secondary = base * 0.5 * elements
    return {'grid': base, 'mesh': mesh, 'secondary': secondary,
            'low': base + mesh, 'high': 2 * (base + mesh + secondary)}


def assembly(entry):
    from .presets import domain
    from ..level2.rain_sim import memory_estimate
    obj, ds = domain(entry)
    if ds is None:
        return liquid_allowance(0)
    cells, _base = memory_estimate(obj, ds.resolution_max)
    elements = sum(bool(getattr(ds, name)) for name in (
        'use_spray_particles', 'use_foam_particles', 'use_bubble_particles'))
    return liquid_allowance(cells * 1e6, ds.mesh_scale, elements)


def scene_allowance(scene):
    from .presets import LIQUID_MODES
    estimates = [assembly(e) for e in scene.aqs_assemblies
                 if e.mode in LIQUID_MODES and (e.mode != 'HOSE' or e.hose_liquid)]
    return sum(e['low'] for e in estimates), sum(e['high'] for e in estimates)
