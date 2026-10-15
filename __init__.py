# SPDX-License-Identifier: GPL-3.0-or-later
"""AquaSuite — Layered Water Simulation Suite for Blender.

One-click, tiered water toolkit: surface & precipitation (Level 1),
volumetric liquid (Level 2), directed emission (Level 3).  See the
bundled README.md and docs/TROUBLESHOOTING.md.
"""

bl_info = {
    "name": "AquaSuite — Water FX",
    "author": "AquaSuite",
    "version": (0, 13, 3),
    "blender": (4, 1, 0),
    "location": "3D Viewport > N-panel > Water",
    "description": "One-click layered water: ocean, rain, reactive rain, "
                   "snow, still water (FLIP), water hose",
    "category": "Physics",
    "doc_url": "",
}

import bpy
from bpy.props import CollectionProperty, EnumProperty

from . import constants as C
from .core import registry, handlers, quality
from .level1 import ocean, rain, rain_reactive, snow
from .level2 import still_water, rain_sim
from .level3 import hose
from .ui import panel


_MODULES = (ocean, rain, rain_reactive, snow, still_water, rain_sim,
            hose, panel)


def _all_classes():
    yield from registry.CLASSES
    for mod in _MODULES:
        yield from getattr(mod, "CLASSES", ())


def register():
    for cls in _all_classes():
        bpy.utils.register_class(cls)

    bpy.types.Scene.aqs_assemblies = CollectionProperty(
        type=registry.AQS_AssemblyEntry)
    bpy.types.Scene.aqs_quality = EnumProperty(
        name="Quality",
        items=[
            ("PREVIEW", "Preview", "Animator playback: reduced counts and "
                                   "resolutions (non-destructive)"),
            ("FINAL", "Final", "Everything at authored values"),
        ],
        default="FINAL",
        update=quality.on_quality_update,
        description="Scene-wide AquaSuite quality tier (TDD §5.1)")

    handlers.register()


def unregister():
    handlers.unregister()

    del bpy.types.Scene.aqs_quality
    del bpy.types.Scene.aqs_assemblies

    for cls in reversed(list(_all_classes())):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
