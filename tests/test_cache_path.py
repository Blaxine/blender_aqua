# SPDX-License-Identifier: GPL-3.0-or-later
"""Bakes whose cache files would pass Windows' 260-character path limit are
refused before Mantaflow runs (it would silently drop the liquid mesh)."""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from aquasuite.core import errors, presets  # noqa: E402
from aquasuite.level2 import still_water as sw  # noqa: E402


def _setup():
    """Still Water from the active mesh, in a saved file."""
    lib.save_blend("cache_path")
    bpy.ops.aquasuite.still_water_create()
    u = lib.last_uuid()
    _dom, ds = presets.domain(lib.entry(u))
    return u, ds


def _dir_for(ds, total):
    """An absolute cache folder whose longest cache file path is `total`
    characters long."""
    ds.cache_directory = lib.WORKDIR
    extra = total - len(sw.longest_cache_path(ds)) - 1
    ds.cache_directory = os.path.join(lib.WORKDIR, "d" * extra)
    return ds.cache_directory


def test_longest_cache_path():
    lib.make_active(bpy.data.objects["Cube"])
    u, ds = _setup()
    for flag in sw.SECONDARY_FLAGS:  # these toggle on every write
        sw.set_flag(ds, flag, False)
    ds.use_mesh = True
    mesh = sw.longest_cache_path(ds)
    sw.set_flag(ds, "use_foam_particles", True)
    particles = sw.longest_cache_path(ds)
    ds.cache_frame_end = 12345
    wide = sw.longest_cache_path(ds)
    lib.check("longest cache file follows what the bake writes",
              mesh.endswith(os.path.join("mesh", "fluid_mesh_0000.bobj.gz"))
              and particles.endswith(os.path.join("particles", "fluid_particles_0000.vdb"))
              and wide.endswith("fluid_particles_00000.vdb")
              and os.path.isabs(mesh), f"{mesh} | {particles} | {wide}")
    bpy.ops.aquasuite.assembly_delete(uuid=u)


def test_long_cache_path_refused():
    if sys.platform != "win32":
        lib.skip("Windows path limit", "only Windows limits paths to 260 characters")
        return
    lib.make_active(lib.add_cube())
    u, ds = _setup()
    _dir_for(ds, 259)
    lib.check("259 characters is allowed", sw.cache_path_too_long(ds) == 0,
              str(len(sw.longest_cache_path(ds))))
    _dir_for(ds, 260)
    lib.check("260 characters is refused", sw.cache_path_too_long(ds) == 260,
              str(sw.cache_path_too_long(ds)))
    _dir_for(ds, 300)
    errors.reset_session()
    result = None
    try:
        result = bpy.ops.aquasuite.bake_fluid(uuid=u)
    except RuntimeError:
        pass  # Blender promotes ERROR reports to RuntimeError for scripts.
    err = errors.last_error()
    from aquasuite.core import bakes
    entry = lib.entry(u)
    lib.check("a bake with a too-long cache path is refused with E021, not started",
              result != {'FINISHED'} and err is not None and 'AQS-E021' in err['message']
              and err['uuid'] == u and not bakes.is_baking(entry) and not bakes.has_bake(entry),
              str(err and err['message']))
    lib.check("the report says what to do", err is not None
              and 'shorter folder' in errors.build_report(err))
    bpy.ops.aquasuite.assembly_delete(uuid=u)


lib.main(globals())
