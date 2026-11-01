# SPDX-License-Identifier: GPL-3.0-or-later
"""Upgrading in one Blender session: when Blender re-runs __init__.py over a
version that was turned off, the add-on must use the new files throughout."""

import importlib
import os
import shutil
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402

NAME = "aqs_upgrade_copy"
PARTS = ("core", "level1", "level2", "level3", "materials", "ui")


def test_new_files_replace_the_old_modules():
    # Only one copy of the add-on's classes can be registered at a time.
    lib.aq.unregister()
    pkg = os.path.join(lib.WORKDIR, NAME)
    os.makedirs(pkg)
    for part in PARTS:
        shutil.copytree(os.path.join(lib.REPO, part), os.path.join(pkg, part),
                        ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("__init__.py", "constants.py", "gerstner.py", "blender_manifest.toml"):
        shutil.copy(os.path.join(lib.REPO, name), pkg)
    sys.path.insert(0, lib.WORKDIR)
    mod = importlib.import_module(NAME)
    bpy.context.preferences.addons.new().module = NAME
    mod.register()
    mod.unregister()
    lib.check("the old version's modules are still loaded after turning it off",
              NAME + ".constants" in sys.modules
              and not hasattr(sys.modules[NAME + ".constants"], "NEW_IN_THIS_VERSION"))

    with open(os.path.join(pkg, "constants.py"), "a", encoding="utf-8") as fh:
        fh.write("\nNEW_IN_THIS_VERSION = True\n")
    with open(os.path.join(pkg, "core", "floating.py"), "a", encoding="utf-8") as fh:
        fh.write("\nfrom .. import constants as _C\nSEEN_NEW = _C.NEW_IN_THIS_VERSION\n")
    importlib.invalidate_caches()
    importlib.reload(mod)  # what addon_utils.enable does when the file changed
    lib.check("the package attribute is the new constants",
              getattr(mod.C, "NEW_IN_THIS_VERSION", False))
    lib.check("submodules read the new constants too",
              getattr(sys.modules.get(NAME + ".core.floating"), "SEEN_NEW", False))
    mod.register()
    lib.check("the new version registers and runs",
              bpy.ops.aquasuite.ocean_create() == {"FINISHED"})
    mod.unregister()


lib.main(globals())
