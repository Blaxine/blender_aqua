# SPDX-License-Identifier: GPL-3.0-or-later
"""Liquid presets: all twelve apply, the "(modified)" marker, Set Up Render
Layers."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import errors, presets  # noqa: E402

C = lib.C


def _create(mode, key):
    if mode == C.MODE_STILL:
        lib.make_active(lib.add_cube(location=(len(lib.scene().aqs_assemblies) * 6, 0, 1)))
        bpy.ops.aquasuite.still_water_create(preset=key)
    elif mode == C.MODE_SIMRAIN:
        bpy.ops.aquasuite.rain_sim_create(preset=key)
    elif mode == C.MODE_HOSE:
        bpy.ops.aquasuite.hose_create(simulate_liquid=True, preset=key)
    else:
        bpy.ops.aquasuite.simulated_ocean_create(preset=key)
    return lib.last_uuid()


def test_catalogue():
    per_mode = {m: [k for k, p in presets.CATALOG.items() if p["mode"] == m]
                for m in presets.LIQUID_MODES}
    lib.check("three presets per liquid mode", all(len(v) == 3 for v in per_mode.values()),
              str({m: len(v) for m, v in per_mode.items()}))
    lib.check("every mode has a default preset",
              all(presets.DEFAULTS[m] in per_mode[m] for m in presets.LIQUID_MODES))


def test_all_presets_apply():
    errors.reset_session()
    bad = []
    for key, pkg in presets.CATALOG.items():
        try:
            u = _create(pkg["mode"], key)
            e = lib.entry(u)
            _dom, ds = presets.domain(e)
            if e.preset_id != key or presets.is_modified(e) or ds is None:
                bad.append(f"{key}: id={e.preset_id} modified={presets.is_modified(e)}")
            for name, value in pkg["domain"].items():
                got = getattr(ds, name)
                if (abs(got - value) > 1e-4) if isinstance(value, float) else got != value:
                    bad.append(f"{key}: {name}={got} expected {value}")
            ww = pkg["entry"]
            flags = (ds.use_spray_particles, ds.use_foam_particles, ds.use_bubble_particles)
            wanted = tuple(ww[f"ww_{x}"] and not ww["draft"] for x in ("spray", "foam", "bubbles"))
            if flags != wanted:
                bad.append(f"{key}: whitewater {flags} expected {wanted}")
        except Exception as exc:
            bad.append(f"{key}: {type(exc).__name__}: {exc}")
    lib.check("all twelve presets apply their package", not bad, "; ".join(bad))
    lib.check("no errors recorded while applying presets", not errors.pending(),
              str([e["title"] for e in errors.pending()]))


def test_thick_uses_viscosity():
    u = next(e.uuid for e in lib.scene().aqs_assemblies if e.preset_id == "STILL_THICK")
    _dom, ds = presets.domain(lib.entry(u))
    lib.check("Thick turns viscosity on", ds.use_viscosity and ds.viscosity_value > 0)


def test_modified_marker():
    u = _create(C.MODE_STILL, "STILL_CALM")
    lib.entry(u).base_resolution = 64
    bpy.context.view_layer.update()
    edited = presets.is_modified(lib.entry(u))
    lib.entry(u).preset_choice = "STILL_CALM"
    bpy.ops.aquasuite.apply_preset(uuid=u)
    lib.check("editing marks the preset modified; Apply clears it",
              edited and not presets.is_modified(lib.entry(u))
              and lib.entry(u).preset_label == "Calm Pour")


def test_wrong_mode_preset_refused():
    u = _create(C.MODE_STILL, "STILL_CALM")
    try:
        presets.apply(bpy.context, lib.entry(u), "RAIN_STORM")
        refused = False
    except RuntimeError:
        refused = True
    lib.check("a preset from another mode is refused", refused
              and lib.entry(u).preset_id == "STILL_CALM")


def test_render_layers():
    r1 = bpy.ops.aquasuite.setup_render_layers()
    vl = bpy.context.view_layer
    aovs = sorted((a.name, a.type) for a in vl.aovs)
    r2 = bpy.ops.aquasuite.setup_render_layers()
    lib.check("Set Up Render Layers: Material Cryptomatte + four value AOVs",
              r1 == {"FINISHED"} and vl.use_pass_cryptomatte_material
              and aovs == sorted((n, "VALUE") for n in ("AQS_Liquid", "AQS_Spray",
                                                         "AQS_Foam", "AQS_Bubbles")), str(aovs))
    lib.check("running it again changes nothing",
              r2 == {"FINISHED"} and sorted((a.name, a.type) for a in vl.aovs) == aovs)


def test_delete_all():
    for u in [e.uuid for e in lib.scene().aqs_assemblies]:
        bpy.ops.aquasuite.assembly_delete(uuid=u)
    lib.check("deleting every preset setup leaves nothing tagged", lib.tagged_left() == [],
              str(lib.tagged_left()))


lib.main(globals())
