# SPDX-License-Identifier: GPL-3.0-or-later
"""Beta modes: which modes are Beta, the one-time note flags in the
add-on preferences, and resetting them.  (The popup itself and the panel
labels are covered by the release checklist.)"""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.ui import beta  # noqa: E402

C = lib.C


def _flags():
    p = beta.prefs()
    return {m: getattr(p, beta._FLAG[m]) for m in beta.BETA_MODES}


def test_beta_modes():
    lib.check("exactly the three liquid modes are Beta",
              set(beta.BETA_MODES) == {C.MODE_STILL, C.MODE_HOSE, C.MODE_SIMRAIN}
              and not beta.is_beta(C.MODE_OCEAN) and not beta.is_beta(C.MODE_RAIN))


def test_preferences_available():
    lib.check("add-on preferences registered under the package name",
              beta.prefs() is not None and beta.ADDON_ID == "aquasuite", beta.ADDON_ID)
    lib.check("no Beta note seen on a fresh install", not any(_flags().values()), str(_flags()))


def test_note_once_per_mode():
    bpy.ops.aquasuite.ocean_create()
    lib.check("non-Beta create sets no flag", not any(_flags().values()), str(_flags()))
    lib.make_active(lib.add_cube(location=(30, 0, 1)))
    bpy.ops.aquasuite.still_water_create()
    f1 = _flags()
    lib.check("first Still Water create marks its note seen",
              f1[C.MODE_STILL] and not f1[C.MODE_HOSE] and not f1[C.MODE_SIMRAIN], str(f1))
    lib.check("second create: note not due again", not beta.note_due(C.MODE_STILL))
    bpy.ops.aquasuite.hose_create()
    bpy.ops.aquasuite.rain_sim_create()
    lib.check("Hose and Rain Sim notes marked on first create", all(_flags().values()),
              str(_flags()))


def test_reset():
    bpy.ops.aquasuite.reset_beta_notes()
    lib.check("Show Beta Notes Again clears every flag", not any(_flags().values()),
              str(_flags()))
    lib.check("notes are due again", all(beta.note_due(m) for m in beta.BETA_MODES))


lib.main(globals())
