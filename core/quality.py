# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-wide Preview/Final quality tiers (TDD §5.1, editing contract R1.3).

Tier-managed fields in this build:
  * particle systems  -> ``display_percentage`` (25 in PREVIEW)
  * ocean surface     -> ``Resolution`` GN input (halved in PREVIEW)

Entering PREVIEW snapshots the live value into an ``aqs_authored``
ID-property on the owning datablock; returning to FINAL restores it and
clears the snapshot.  Authored values exist only while PREVIEW is
active (R1.3 rule 2).
"""

import bpy

from .. import constants as C
from ..level1 import ocean as ocean_mod


def _tagged_particles():
    for ps in bpy.data.particles:
        if C.OWNER_PROP in ps.keys():
            yield ps


def apply_tier(scene):
    preview = scene.aqs_quality == "PREVIEW"

    for ps in _tagged_particles():
        if preview:
            if C.AUTHORED_PROP not in ps.keys():
                ps[C.AUTHORED_PROP] = float(ps.display_percentage)
            ps.display_percentage = 25
        else:
            if C.AUTHORED_PROP in ps.keys():
                ps.display_percentage = int(ps[C.AUTHORED_PROP])
                del ps[C.AUTHORED_PROP]

    for entry in scene.aqs_assemblies:
        if entry.mode != C.MODE_OCEAN or entry.primary is None:
            continue
        obj = entry.primary
        mod = ocean_mod.find_ocean_modifier(obj, entry.uuid)
        if mod is None:
            continue
        res = ocean_mod.get_input(mod, "Resolution")
        if res is None:
            continue
        if preview:
            if C.AUTHORED_PROP not in obj.keys():
                obj[C.AUTHORED_PROP] = int(res)
            ocean_mod.set_input(mod, "Resolution", max(16, int(res) // 2))
        else:
            if C.AUTHORED_PROP in obj.keys():
                ocean_mod.set_input(mod, "Resolution", int(obj[C.AUTHORED_PROP]))
                del obj[C.AUTHORED_PROP]
        obj.update_tag()


def on_quality_update(self, context):
    try:
        apply_tier(context.scene)
    except Exception as exc:  # never break the UI on a tier flip
        print(f"[AquaSuite] tier switch error: {exc}")
