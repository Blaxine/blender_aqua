# SPDX-License-Identifier: GPL-3.0-or-later
"""Beta modes: labels, the one-time explanatory note, and the minimal
add-on preferences that remember which notes were seen."""

import bpy
from bpy.props import BoolProperty

from .. import constants as C

# The add-on's package: "aquasuite" from the repo, "bl_ext.<repo>.aquasuite"
# when installed as an extension.  AddonPreferences must use exactly this.
ADDON_ID = __package__.rpartition(".")[0]

BETA_MODES = (C.MODE_STILL, C.MODE_HOSE, C.MODE_SIMRAIN)
_FLAG = {C.MODE_STILL: "beta_seen_still",
         C.MODE_HOSE: "beta_seen_hose",
         C.MODE_SIMRAIN: "beta_seen_simrain"}

NOTE_LINES = (
    "Liquid modes must be baked before they play or render.",
    "Bakes get slow and RAM-heavy at high Resolution.",
    "Draft is fast but coarse: turn it off for final quality.",
    "Found a problem? Report it at:",
    C.SUPPORT_URL,
)

_session_seen = set()   # used only when preferences are unavailable


def is_beta(mode):
    return mode in BETA_MODES


def prefs():
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon is not None else None


def note_due(mode):
    if not is_beta(mode):
        return False
    p = prefs()
    if p is not None:
        return not getattr(p, _FLAG[mode])
    return mode not in _session_seen


def mark_seen(mode):
    p = prefs()
    if p is not None:
        setattr(p, _FLAG[mode], True)
        bpy.context.preferences.is_dirty = True    # saved with user prefs
    _session_seen.add(mode)


def reset_notes():
    p = prefs()
    if p is not None:
        for flag in _FLAG.values():
            setattr(p, flag, False)
        bpy.context.preferences.is_dirty = True
    _session_seen.clear()


def _show_note(mode):
    if bpy.app.background:
        return
    label = C.MODE_LABELS.get(mode, mode)

    def draw(menu, _context):
        for line in NOTE_LINES:
            menu.layout.label(text=line)

    try:
        bpy.context.window_manager.popup_menu(
            draw, title=f"{label} is in Beta", icon="EXPERIMENTAL")
    except Exception as exc:
        print(f"[AquaSuite] could not show the Beta note: {exc}")


def notify_created(mode):
    """After a successful Create: show the Beta note once per mode per
    Blender install.  Returns True when the note was due."""
    if not note_due(mode):
        return False
    _show_note(mode)
    mark_seen(mode)
    return True


class AQS_OT_reset_beta_notes(bpy.types.Operator):
    bl_idname = "aquasuite.reset_beta_notes"
    bl_label = "Show Beta Notes Again"
    bl_description = ("Show the explanation of Beta modes again the next "
                      "time each one is created")

    def execute(self, context):
        reset_notes()
        self.report({"INFO"}, "Beta notes will show again")
        return {"FINISHED"}


class AQS_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    beta_seen_still: BoolProperty(default=False)
    beta_seen_hose: BoolProperty(default=False)
    beta_seen_simrain: BoolProperty(default=False)

    def draw(self, _context):
        col = self.layout.column()
        col.label(text="Still Water, Water Hose and Rain Simulation are Beta: "
                       "a note explains what that means the first time each "
                       "is created.")
        col.operator("aquasuite.reset_beta_notes", icon="LOOP_BACK")


CLASSES = (AQS_OT_reset_beta_notes, AQS_Preferences)
