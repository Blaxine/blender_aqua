# SPDX-License-Identifier: GPL-3.0-or-later
"""AquaSuite — Layered Water Simulation Suite for Blender.

One-click, tiered water toolkit: surface & precipitation (Level 1),
volumetric liquid (Level 2), directed emission (Level 3).  See the
bundled README.md and docs/TROUBLESHOOTING.md.

Blender 4.2+ extension: name, version and requirements live in
blender_manifest.toml (the single source of the add-on version).
"""

import bpy
from bpy.props import CollectionProperty, EnumProperty

from . import constants as C
from .core import registry, handlers, quality, errors
from .level1 import ocean, rain, rain_reactive, snow
from .level2 import still_water, rain_sim
from .level3 import hose
from .ui import panel, beta


_MODULES = (errors, ocean, rain, rain_reactive, snow, still_water, rain_sim,
            hose, panel, beta)


def _all_classes():
    yield from registry.CLASSES
    for mod in _MODULES:
        yield from getattr(mod, "CLASSES", ())


def register():
    errors.register()
    for cls in _all_classes():
        if issubclass(cls, bpy.types.Operator):
            # No AquaSuite button may fail with a raw Python traceback.
            cls.execute = errors.guard_operator(cls.execute)
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
    errors.unregister()

    del bpy.types.Scene.aqs_quality
    del bpy.types.Scene.aqs_assemblies

    for cls in reversed(list(_all_classes())):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
