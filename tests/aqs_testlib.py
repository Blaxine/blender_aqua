# SPDX-License-Identifier: GPL-3.0-or-later
"""In-Blender helper shared by every AquaSuite test file.

Importing this module loads the add-on from the repo as the package
``aquasuite`` (whatever the folder is called) and registers it.  A test
file defines ``test_*`` functions and ends with ``lib.main(globals())``;
they run in definition order in one fresh Blender process.

Rules learned the hard way:
  * Hold assembly uuids, never entry objects, across deletions: RNA
    references into ``scene.aqs_assemblies`` silently point at another
    entry after any removal.
  * Call ``bpy.context.view_layer.update()`` before measuring
    ``matrix_world`` / ``dimensions`` / bounding boxes of objects just
    moved or resized.
"""

import importlib.util
import os
import sys
import tempfile
import traceback

sys.dont_write_bytecode = True

import bpy  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        if i + 1 < len(ARGS):
            return ARGS[i + 1]
    return default


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = _arg("--repo", os.path.dirname(HERE))
WORKDIR = _arg("--workdir") or tempfile.mkdtemp(prefix="aqs_test_")
BAKE = "--bake" in ARGS
TAG = "AQS_TEST|"


def _load_addon():
    spec = importlib.util.spec_from_file_location(
        "aquasuite", os.path.join(REPO, "__init__.py"),
        submodule_search_locations=[REPO])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aquasuite"] = mod
    spec.loader.exec_module(mod)
    # What enabling the add-on does, so AddonPreferences are available.
    bpy.context.preferences.addons.new().module = "aquasuite"
    mod.register()
    return mod


aq = _load_addon()

from aquasuite import constants as C  # noqa: E402
from aquasuite.core import registry  # noqa: E402


def _clean(text):
    return str(text).replace("|", "/").replace("\n", " ")


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"{TAG} {status} | {_clean(name)} | {_clean(detail)}", flush=True)
    return ok


def skip(name, why):
    print(f"{TAG} SKIP | {_clean(name)} | {_clean(why)}", flush=True)


def main(namespace):
    """Run every ``test_*`` function of the calling module, in order."""
    for name, fn in list(namespace.items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:
                last = traceback.format_exc().strip().splitlines()[-3:]
                check(name, False, f"{type(exc).__name__}: {exc} @ {' / '.join(last)}")
    print(f"{TAG} DONE", flush=True)


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def scene():
    return bpy.context.scene


def save_blend(name):
    """Save into the run's temp folder (bakes and caches need a saved file)."""
    path = os.path.join(WORKDIR, f"{name}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path


def last_uuid():
    return scene().aqs_assemblies[-1].uuid


def entry(uuid):
    return registry.get(scene(), uuid)


def tagged_left():
    out = []
    for coll in ("objects", "meshes", "particles", "node_groups",
                 "materials", "collections"):
        for idb in getattr(bpy.data, coll):
            if C.OWNER_PROP in idb.keys():
                out.append((coll, idb.name))
    return out


def add_cube(location=(0.0, 0.0, 0.0), size=1.0, name=None):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    obj = bpy.context.active_object
    if name:
        obj.name = name
    return obj


def make_active(obj):
    bpy.context.view_layer.objects.active = obj
