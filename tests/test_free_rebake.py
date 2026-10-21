# SPDX-License-Identifier: GPL-3.0-or-later
"""Free Bake, then bake again.  Blender's own Free All runs as a job, and on
4.5 a bake that starts before it ends crashes Mantaflow (always headless);
Bake All on a domain that was not reset bakes a different result.  Free
Bake therefore frees on the spot, and Bake Again frees first.  A crash
here shows as "test file crashed or never finished"."""

import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import bakes, delete  # noqa: E402
from aquasuite.level2 import still_water as sw  # noqa: E402

FRAMES = 6
U = {}


def _ds():
    return sw.find_domain_object(lib.entry(U["u"])).modifiers["AQS Fluid"].domain_settings


def _verts(frame):
    dom = sw.find_domain_object(lib.entry(U["u"]))
    lib.scene().frame_set(frame)
    return len(dom.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices)


def _bake():
    r = bpy.ops.aquasuite.bake_fluid(uuid=U["u"])
    return r, (_verts(1), _verts(FRAMES))


def _same_dir(a, b):
    """Blender normalises the slashes of a cache folder it is given."""
    return os.path.normpath(bpy.path.abspath(a)) == os.path.normpath(bpy.path.abspath(b))


def _cache_subdirs():
    path = delete.cache_dir(U["u"])
    return sorted(os.listdir(path)) if os.path.isdir(path) else []


def test_setup():
    lib.save_blend("free_rebake")
    lib.scene().frame_start, lib.scene().frame_end = 1, FRAMES
    lib.make_active(lib.add_cube(location=(0, 0, 1), name="WaterBlock"))
    bpy.ops.aquasuite.still_water_create()
    U["u"] = lib.last_uuid()
    lib.entry(U["u"]).base_resolution = 32
    ds = _ds()
    ds.cache_frame_start, ds.cache_frame_end = 1, FRAMES
    U["dir"] = ds.cache_directory
    lib.check("setup created", lib.entry(U["u"]) is not None)


def test_nothing_writes_use_fractions():
    """Writing use_fractions after a bake broke the next 4.5 bake when the
    bake was freed with Free All."""
    hits = []
    for root, dirs, files in os.walk(lib.REPO):
        dirs[:] = [d for d in dirs if d not in ("tests", "public_repo", "__pycache__")
                   and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    if "use_fractions" in fh.read():
                        hits.append(f)
    lib.check("the add-on never writes use_fractions", not hits, str(hits))


def test_free_without_bake_is_harmless():
    path = delete.cache_dir(U["u"])
    os.makedirs(path, exist_ok=True)
    keep = os.path.join(path, "keep.txt")
    with open(keep, "w") as fh:
        fh.write("not a cache file")
    r = bpy.ops.aquasuite.free_fluid(uuid=U["u"])
    lib.check("Free Bake with nothing baked: finishes, other files kept",
              r == {"FINISHED"} and os.path.isfile(keep), str(r))
    os.remove(keep)


def test_free_then_bake():
    if not lib.BAKE:
        lib.skip("free then bake", "run with --bake")
        return
    r, ref = _bake()
    U["ref"] = ref
    lib.check("first bake produces liquid", r == {"FINISHED"} and ref[1] > 8
              and bakes.has_bake(lib.entry(U["u"])), f"{r} verts f1/f{FRAMES} {ref}")

    r = bpy.ops.aquasuite.free_fluid(uuid=U["u"])
    ds = _ds()
    pauses = [getattr(ds, f"cache_frame_pause_{k}") for k in ("data", "mesh", "noise")]
    lib.check("Free Bake frees on the spot (button back to red Bake)",
              r == {"FINISHED"} and not bakes.has_bake(lib.entry(U["u"]))
              and not any(pauses), f"{r} pause {pauses}")
    lib.check("Free Bake deletes the cache folder, and the domain keeps it",
              not _cache_subdirs() and _same_dir(ds.cache_directory, U["dir"]),
              f"{_cache_subdirs()} {ds.cache_directory}")
    lib.check("after Free Bake the domain shows no liquid", _verts(3) <= 8, str(_verts(3)))

    r, got = _bake()
    lib.check("Free Bake then Bake: the same liquid as the first bake",
              r == {"FINISHED"} and got == U["ref"], f"{got} vs {U['ref']}")
    lib.check("the new bake is in the assembly's own cache folder",
              "data" in _cache_subdirs() and "mesh" in _cache_subdirs(), str(_cache_subdirs()))


def test_use_fractions_written_then_free_and_bake():
    if not lib.BAKE:
        lib.skip("use_fractions then free and bake", "run with --bake")
        return
    ds = _ds()
    ds.use_fractions = ds.use_fractions
    bpy.ops.aquasuite.free_fluid(uuid=U["u"])
    r, got = _bake()
    lib.check("use_fractions written, Free Bake, Bake: no crash, same liquid",
              r == {"FINISHED"} and got == U["ref"], f"{got} vs {U['ref']}")


def test_bake_again_is_a_clean_bake():
    if not lib.BAKE:
        lib.skip("bake again", "run with --bake")
        return
    for i in (1, 2):
        r, got = _bake()
        lib.check(f"Bake Again without Free ({i}): the same liquid as the first bake",
                  r == {"FINISHED"} and got == U["ref"], f"{got} vs {U['ref']}")


lib.main(globals())
