# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent handlers (TDD §4.4, amended per R1.2).

This build ships exactly ONE per-frame handler: ``aqs_buoy_tick``.  It
is closed-form and stateless (R1.5): buoy transforms are a pure function
of (x, y, t), so isolated-frame (farm) evaluation matches sequential
playback.  It writes ONLY to AquaSuite-owned empties, never to user
objects.

Transform-aware: waves are defined in the ocean surface's LOCAL space,
so buoy world positions are mapped through the surface transform
(translation, Z-rotation, scale) before sampling, and heights mapped
back.  A playback-safety guard ensures a bad frame can never break the
animation loop (errors are logged once per assembly, not per frame).
"""

import math

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

from .. import constants as C
from .. import gerstner
from ..level1 import ocean as ocean_mod

_error_logged = set()


def _subframe_time(scene):
    frame = getattr(scene, "frame_current_final", None)
    if frame is None:
        frame = scene.frame_current + scene.frame_subframe
    fps = scene.render.fps / scene.render.fps_base
    return frame / max(fps, 1e-6)


def _tick_assembly(entry, t):
    surf = entry.primary
    if surf is None or not surf.users_scene:
        # Self-heal: the surface OBJECT is really gone -> detach orphan
        # buoys (AQS-W007).  Only then: a missing/replaced modifier is not
        # proof the ocean is gone, and detaching is destructive.
        for b in list(entry.buoys):
            if b.obj is not None:
                names = [n for n in (b.added_constraints or "").split(";") if n]
                for n in names:
                    con = b.obj.constraints.get(n)
                    if con:
                        b.obj.constraints.remove(con)
        entry.buoys.clear()
        print("[AquaSuite] W007:", C.MSG["W007"])
        return

    mod = ocean_mod.find_ocean_modifier(surf, entry.uuid)
    if mod is None:
        # Ocean modifier removed or disabled by the user: hold the buoys
        # where they are instead of tearing them off the floaters.
        key = ("nomod", entry.uuid)
        if key not in _error_logged:
            _error_logged.add(key)
            print(f"[AquaSuite] ocean {entry.uuid[:8]}: surface modifier "
                  "not found — buoys paused")
        return
    _error_logged.discard(("nomod", entry.uuid))

    params = ocean_mod.read_wave_params(mod)
    layers = gerstner.layer_params(**params)

    # Waves live in the surface's LOCAL space: decompose its transform
    # once per assembly per frame (supports translation, Z rotation, and
    # scale — the realistic ways an ocean plane gets placed).
    loc, rot, sca = surf.matrix_world.decompose()
    rot_inv = rot.inverted()
    s_xy = max((abs(sca.x) + abs(sca.y)) * 0.5, 1e-6)
    s_z = sca.z if abs(sca.z) > 1e-6 else 1.0

    def height_at(wx, wy, smoothing):
        """World-space water height at world (x, y)."""
        lp = rot_inv @ (Vector((wx, wy, 0.0)) - loc)
        h_local = gerstner.smoothed_height(
            layers, lp.x / s_xy, lp.y / s_xy, t, smoothing)
        return loc.z + h_local * s_z

    for b in entry.buoys:
        obj, empty = b.obj, b.empty
        if obj is None or empty is None:
            continue
        # Z-only constraint -> the object's world XY is user-authored
        # and safe to read here.
        wx, wy = obj.matrix_world.translation.x, obj.matrix_world.translation.y
        r = max(b.radius, 1e-3)
        sm = b.smoothing

        h_px = height_at(wx + r, wy, sm)
        h_mx = height_at(wx - r, wy, sm)
        h_py = height_at(wx, wy + r, sm)
        h_my = height_at(wx, wy - r, sm)
        h = 0.25 * (h_px + h_mx + h_py + h_my)

        empty.location = (wx, wy, h + b.offset)
        pitch = math.atan2(h_py - h_my, 2.0 * r) * b.tilt
        roll = math.atan2(h_px - h_mx, 2.0 * r) * b.tilt
        empty.rotation_euler = (pitch, -roll, 0.0)


@persistent
def aqs_buoy_tick(scene, _depsgraph=None):
    entries = getattr(scene, "aqs_assemblies", None)
    if not entries:
        return
    t = _subframe_time(scene)
    for entry in entries:
        if entry.mode != C.MODE_OCEAN or len(entry.buoys) == 0:
            continue
        try:
            _tick_assembly(entry, t)
        except Exception as exc:
            # NEVER break animation playback: record once per assembly; the
            # popup waits until playback/rendering stops.
            if entry.uuid not in _error_logged:
                _error_logged.add(entry.uuid)
                from . import errors
                errors.record("AquaSuite couldn't move the floating objects",
                              exc, mode=entry.mode, uuid=entry.uuid)
                errors.schedule()


def register():
    if aqs_buoy_tick not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(aqs_buoy_tick)


def unregister():
    if aqs_buoy_tick in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(aqs_buoy_tick)
