# SPDX-License-Identifier: GPL-3.0-or-later
"""AquaSuite constants: name prefixes, build tags, defaults, user-facing strings."""

import os as _os

ADDON_NAME = "aquasuite"
BUILD_TAG = "1.0.0"


def _manifest_version():
    """The add-on version: blender_manifest.toml is its single source."""
    try:
        import tomllib
        path = _os.path.join(_os.path.dirname(__file__), "blender_manifest.toml")
        with open(path, "rb") as fh:
            return str(tomllib.load(fh).get("version", "0.0.0"))
    except Exception:
        return "0.0.0"


ADDON_VERSION = _manifest_version()

# Saved-data layout version stamped on every assembly entry.  0 = made by a
# pre-release (pre-1.0) build.  Bump ONLY when a mode's saved layout
# changes; old setups are then offered an opt-in upgrade, never converted.
DATA_VERSION = 1

# --- Ownership / naming ------------------------------------------------------
OWNER_PROP = "aqs_owner"          # "<mode_id>:<assembly_uuid>" or "SHARED"
BUILD_PROP = "aqs_build"
EFFECTOR_OWNERS_PROP = "aqs_eff_owners"   # JSON list of assembly uuids
AUTHORED_PROP = "aqs_authored"            # tier snapshot storage (per-ID)
SRC_PROP = "aqs_source_of"                # marks a USER object as a Still-Water
                                          # source. NEVER the owner tag: user
                                          # objects must never match the
                                          # delete sweep, even with a lost
                                          # registry entry.

ROOT_COLLECTION = "AQS_Assemblies"

# Public issue tracker: bug reports, roadmap, support.
SUPPORT_URL = "https://github.com/Blaxine/aquasuite/issues"

MODE_OCEAN = "OCEAN"
MODE_RAIN = "RAIN"
MODE_RRAIN = "RRAIN"
MODE_SNOW = "SNOW"
MODE_STILL = "STILL"
MODE_SIMRAIN = "SIMRAIN"
MODE_HOSE = "HOSE"

MODE_LABELS = {
    MODE_OCEAN: "Plane Ocean",
    MODE_RAIN: "Plane Rain",
    MODE_RRAIN: "Reactive Rain",
    MODE_SNOW: "Snow Plane",
    MODE_STILL: "Still Water",
    MODE_SIMRAIN: "Rain Simulation",
    MODE_HOSE: "Water Hose",
}

MODE_ICONS = {
    MODE_OCEAN: "MOD_OCEAN",
    MODE_RAIN: "MOD_FLUIDSIM",
    MODE_RRAIN: "MOD_DYNAMICPAINT",
    MODE_SNOW: "FREEZE",
    MODE_STILL: "MATFLUID",
    MODE_SIMRAIN: "OUTLINER_DATA_VOLUME",
    MODE_HOSE: "FORCE_WIND",
}

# --- Hose regimes -------------------------------------------------------------
REGIME_NORMAL = "NORMAL"
REGIME_MIST = "MIST"
REGIME_SPRAY = "SPRAY"
REGIME_BLAST = "BLAST"

REGIME_ITEMS = [
    (REGIME_NORMAL, "Normal Flow", "Coherent laminar stream (Mantaflow, bake required)"),
    (REGIME_MIST, "Mist", "Fine hanging fog cone (particles, real-time)"),
    (REGIME_SPRAY, "Spray", "Broken-up shower with spray secondaries (Mantaflow, bake required)"),
    (REGIME_BLAST, "Water Blast", "High-velocity fire-hose jet (Mantaflow, bake required)"),
]

# Regime parameter packages (R1.9-corrected Blast defaults).
REGIME_PARAMS = {
    REGIME_NORMAL: dict(velocity=6.0, radius=0.03, resolution=96,
                        cfl=4.0, ts_min=1, ts_max=4, secondaries=False),
    REGIME_SPRAY: dict(velocity=9.0, radius=0.045, resolution=96,
                       cfl=4.0, ts_min=1, ts_max=4, secondaries=True),
    REGIME_BLAST: dict(velocity=20.0, radius=0.05, resolution=160,
                       cfl=2.0, ts_min=1, ts_max=12, secondaries=False),
}

# --- User-facing strings (single table, §15) ----------------------------------
MSG = {
    "E011": "That object already belongs to a AquaSuite assembly — detach or delete it first.",
    "E020": "Save the .blend first — caches are stored next to the file.",
    "W004": "Very fine ocean grid: consider Resolution ≤ 256.",
    "W007": "A floater lost its ocean and was detached automatically.",
    "W009": "Scene FPS below 12 — ripple simulation can become unstable at this timebase.",
    "W012": "Source mesh has open edges; the liquid volume may leak. Consider closing it.",
    "W015": "Secondary particles (foam/spray/bubbles) can multiply bake time several times.",
    "W018": ("Jet velocity was reduced to {v:.1f} m/s to stay stable at this resolution "
             "(full speed needs about {ts} solver substeps per frame). Lower Pressure, "
             "or lower Resolution / use Draft to raise the limit."),
    "W021": ("These objects were kept out of the liquid simulation because they already "
             "have a Fluid setup: {names}."),
    "W022": ("Estimated grid is {gb:.1f} GB — Blender can run out of memory. "
             "Reduce Area, Resolution, or fit the domain tighter."),
}
