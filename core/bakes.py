# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake state and cancelling.

Liquid bakes (Still Water, Hose, Rain Sim) and ripple bakes (Reactive
Rain) run as Blender background jobs: a progress bar in the status bar,
and Esc stops them.  Liquid bakes can also be stopped from the panel:
Blender's own Pause Bake stops the job and keeps the frames already
baked.  Ripple (point-cache) bakes have no stop operator — Esc only.

While anything AquaSuite started is baking, a timer redraws the 3D
Viewport sidebars so the panel shows the bake state live.
"""

import bpy

from .. import constants as C
from . import registry

_REDRAW_INTERVAL = 0.5


def fluid_settings(entry):
    from ..level2 import still_water as sw
    dom = sw.find_domain_object(entry)
    mod = next((m for m in dom.modifiers if m.type == "FLUID"), None) if dom else None
    return dom, getattr(mod, "domain_settings", None)


def ripple_cache(entry):
    floor = entry.primary
    if floor is None:
        return None
    mod = next((m for m in floor.modifiers if m.type == "DYNAMIC_PAINT"), None)
    canvas = getattr(mod, "canvas_settings", None)
    surfaces = canvas.canvas_surfaces if canvas else []
    return surfaces[0].point_cache if len(surfaces) else None


def is_baking(entry):
    if entry.mode == C.MODE_RRAIN:
        pc = ripple_cache(entry)
        return bool(pc and pc.is_baking)
    _dom, ds = fluid_settings(entry)
    return bool(ds and ds.is_cache_baking_any)


def any_baking():
    for scene in bpy.data.scenes:
        for entry in getattr(scene, "aqs_assemblies", []):
            try:
                if is_baking(entry):
                    return True
            except Exception:
                pass
    return False


def _redraw():
    for win in bpy.context.window_manager.windows:
        if win.screen is None:
            continue
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _timer():
    _redraw()
    return _REDRAW_INTERVAL if any_baking() else None


def watch():
    """Start the live panel refresh after a bake starts (UI only)."""
    if bpy.app.background:
        return
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=_REDRAW_INTERVAL)


def unwatch():
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)


class AQS_OT_cancel_bake(bpy.types.Operator):
    bl_idname = "aquasuite.cancel_bake"
    bl_label = "Cancel Bake"
    bl_description = ("Stop this liquid bake now. Frames already baked are "
                      "kept; Free Bake removes them")

    uuid: bpy.props.StringProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None or entry.mode == C.MODE_RRAIN:
            self.report({"INFO"}, "Press Esc to stop a ripple bake")
            return {"CANCELLED"}
        dom, ds = fluid_settings(entry)
        if ds is None or not ds.is_cache_baking_any:
            self.report({"INFO"}, "Nothing is baking for this setup")
            return {"CANCELLED"}
        from ..level2 import still_water as sw
        with sw._fluid_op_override(context, dom):
            bpy.ops.fluid.pause_bake()
        self.report({"INFO"}, "Bake stopped — frames baked so far are kept "
                              "(Free Bake removes them)")
        return {"FINISHED"}


CLASSES = (AQS_OT_cancel_bake,)


def unregister():
    unwatch()
