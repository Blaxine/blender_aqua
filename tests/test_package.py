# SPDX-License-Identifier: GPL-3.0-or-later
"""The extension zip: validates, builds, ships only add-on files, and the
add-on inside it loads and runs.  Needs Blender 4.2+ (`--command extension`)."""

import os
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402

FORBIDDEN = ("requirements/", "tests/", ".git", "__pycache__", "aquasuite_cache",
             "public_repo/", "docs/TESTING.md", "docs/THESAURUS.md",
             "docs/RELEASE_CHECKLIST.md", "docs/REQ003_REVIEW.md")
REQUIRED = ("__init__.py", "README.md", "docs/TROUBLESHOOTING.md", "blender_manifest.toml", "constants.py", "core/errors.py",
            "core/registry.py", "core/lighting.py", "core/demo.py", "ui/control_spec.py",
            "level2/rain_sim.py", "ui/panel.py", "ui/beta.py")

LOAD_SCRIPT = r'''
import importlib.util, os, sys
sys.dont_write_bytecode = True
pkg = sys.argv[sys.argv.index("--") + 1]
spec = importlib.util.spec_from_file_location("aquasuite", os.path.join(pkg, "__init__.py"),
                                              submodule_search_locations=[pkg])
mod = importlib.util.module_from_spec(spec); sys.modules["aquasuite"] = mod
spec.loader.exec_module(mod); mod.register()
import bpy
bpy.context.view_layer.objects.active = bpy.data.objects['Cube']
bpy.ops.aquasuite.still_water_create()
for op in ("ocean_create", "rain_create", "rain_reactive_create", "snow_create",
           "hose_create", "rain_sim_create", "simulated_ocean_create", "water_lighting"):
    getattr(bpy.ops.aquasuite, op)()
n = len(bpy.context.scene.aqs_assemblies)
for u in [e.uuid for e in bpy.context.scene.aqs_assemblies]:
    bpy.ops.aquasuite.assembly_delete(uuid=u)
mod.unregister()
print("ZIPLOAD", n)
'''


def _blender(*args):
    proc = subprocess.run([bpy.app.binary_path, "--factory-startup", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    return proc.returncode, proc.stdout + proc.stderr


def test_package():
    if bpy.app.version < (4, 2, 0):
        lib.skip("extension package", "needs Blender 4.2+")
        return
    code, out = _blender("--command", "extension", "validate", lib.REPO)
    lib.check("manifest validates", code == 0 and "Success" in out, out.strip()[-200:])

    out_dir = os.path.join(lib.WORKDIR, "dist")
    os.makedirs(out_dir, exist_ok=True)
    code, out = _blender("--command", "extension", "build",
                         "--source-dir", lib.REPO, "--output-dir", out_dir)
    zips = [f for f in os.listdir(out_dir) if f.endswith(".zip")]
    lib.check("extension zip builds", code == 0 and len(zips) == 1, out.strip()[-200:])
    if not zips:
        return
    path = os.path.join(out_dir, zips[0])
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        bad = [n for n in names if any(n.startswith(f) or f"/{f}" in f"/{n}"
                                       for f in FORBIDDEN) or n.endswith(".zip")]
        lib.check("zip ships no plans, tests, git or cache files", not bad, str(bad[:10]))
        missing = [r for r in REQUIRED if r not in names]
        lib.check("zip contains the add-on", not missing, f"missing {missing}")
        pkg = os.path.join(lib.WORKDIR, "unzipped", "aquasuite")
        zf.extractall(pkg)

    code, out = _blender("-b", "--python-expr", LOAD_SCRIPT, "--", pkg)
    loaded = [ln for ln in out.splitlines() if ln.startswith("ZIPLOAD")]
    lib.check("add-on from the zip registers and runs every mode",
              code == 0 and loaded == ["ZIPLOAD 9"],
              f"exit {code}: " + (loaded or [out.strip()[-300:]])[0])


lib.main(globals())
