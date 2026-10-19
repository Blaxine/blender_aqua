# SPDX-License-Identifier: GPL-3.0-or-later
"""AquaSuite — Layered Water Simulation Suite for Blender.

One-click, tiered water toolkit: surface & precipitation (Level 1),
volumetric liquid (Level 2), directed emission (Level 3).  See the
bundled README.md and docs/TROUBLESHOOTING.md.

Blender 4.2+ extension: name, version and requirements live in
blender_manifest.toml (the single source of the add-on version).
"""

import bpy
from bpy.props import CollectionProperty, EnumProperty, PointerProperty

from . import constants as C
from .core import registry, handlers, quality, errors, bakes, obstacles
from .core import presets, whitewater, render_layers
from .core import lighting
from .core import demo
from .level1 import ocean, rain, rain_reactive, snow
from .level2 import still_water, rain_sim
from .level2 import simulated_ocean
from .level3 import hose
from .ui import panel, beta


_MODULES = (errors, bakes, obstacles, ocean, rain, rain_reactive, snow, still_water, rain_sim,
            hose, simulated_ocean, presets, render_layers, lighting, demo, panel, beta)


def _all_classes():
    yield from registry.CLASSES
    for mod in _MODULES:
        yield from getattr(mod, "CLASSES", ())


def register():
    # A previous failed enable can leave these exact Python classes registered.
    # Remove their handlers/properties before retrying; never skip individual
    # classes and leave a mixture of old and new registration state.
    if any(cls.is_registered for cls in _all_classes()):
        unregister()
    try:
        _register()
    except Exception:
        unregister()
        raise


def _register():
    errors.register()
    for cls in _all_classes():
        if issubclass(cls, bpy.types.Operator):
            # No AquaSuite button may fail with a raw Python traceback.
            if not getattr(cls.execute, '_aqs_guarded', False):
                cls.execute = errors.guard_operator(cls.execute)
                cls.execute._aqs_guarded = True
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

    bpy.types.Scene.aqs_obstacles = PointerProperty(
        type=bpy.types.Collection, name="Water Obstacles",
        description="Objects in this collection block water in every AquaSuite simulation")

    handlers.register()
    obstacles.register()
    whitewater.register()
    presets.register()


def unregister():
    # Also valid after partial registration. Continue cleanup if one resource
    # fails so it does not strand every subsequently registered resource.
    for module in (presets, whitewater, obstacles, handlers, errors, bakes):
        try:
            module.unregister()
        except Exception as exc:
            print(f'[AquaSuite] cleanup {module.__name__}: {exc}')

    for name in ('aqs_obstacles', 'aqs_quality', 'aqs_assemblies'):
        if hasattr(bpy.types.Scene, name):
            try:
                delattr(bpy.types.Scene, name)
            except Exception as exc:
                print(f'[AquaSuite] cleanup Scene.{name}: {exc}')

    for cls in reversed(list(_all_classes())):
        if cls.is_registered:
            try:
                bpy.utils.unregister_class(cls)
            except Exception as exc:
                print(f'[AquaSuite] cleanup {cls.__name__}: {exc}')


if __name__ == "__main__":
    register()
