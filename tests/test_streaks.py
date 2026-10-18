# SPDX-License-Identifier: GPL-3.0-or-later
"""Rain streaks point along the direction of fall (straight and angled)."""

import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from aquasuite.level2 import rain_sim  # noqa: E402


def _particle_alignment(emitter, droplet):
    """Mean |cos| between each live particle's streak axis and velocity."""
    lib.scene().frame_set(30)
    dg = bpy.context.evaluated_depsgraph_get()
    ps = emitter.evaluated_get(dg).particle_systems[0]
    dims = droplet.data.vertices
    xs = [v.co.x for v in dims]
    zs = [v.co.z for v in dims]
    long_axis = Vector((1, 0, 0)) if (max(xs) - min(xs)) > (max(zs) - min(zs)) \
        else Vector((0, 0, 1))
    dots = []
    for p in ps.particles:
        if p.alive_state != "ALIVE" or p.velocity.length < 1e-3:
            continue
        dots.append(abs((p.rotation @ long_axis).dot(p.velocity.normalized())))
        if len(dots) >= 50:
            break
    return (sum(dots) / len(dots)) if dots else 0.0, len(dots)


def _droplet(entry):
    return next(o for o in entry.root_collection.all_objects
                if "Droplet" in o.data.name and o.type == "MESH")


def test_particle_rain_straight_and_angled():
    for op, label in (("rain_create", "Rain"), ("rain_reactive_create", "Reactive Rain")):
        getattr(bpy.ops.aquasuite, op)()
        e = lib.entry(lib.last_uuid())
        emitter = next(o for o in e.root_collection.all_objects if o.particle_systems)
        drop = _droplet(e)
        mean, n = _particle_alignment(emitter, drop)
        lib.check(f"{label}: streaks along velocity", n > 0 and mean > 0.98,
                  f"mean |cos| {mean:.3f} over {n} drops")
        emitter.particle_systems[0].settings.object_align_factor[0] = 6.0   # wind
        lib.scene().frame_set(1)
        mean, n = _particle_alignment(emitter, drop)
        lib.check(f"{label}: angled streaks along velocity", n > 0 and mean > 0.98,
                  f"mean |cos| {mean:.3f} over {n} drops")


def _instance_axes(obj):
    """Long (local Z, streak-scaled) axis of each instanced drop of obj."""
    dg = bpy.context.evaluated_depsgraph_get()
    axes = []
    for inst in dg.object_instances:
        if inst.is_instance and inst.parent is not None                 and inst.parent.original == obj:
            m = inst.matrix_world.to_3x3()
            z = m @ Vector((0, 0, 1))
            if z.length > 1e-9:
                axes.append(z.normalized())
    return axes


def _drop_axes(obj):
    """Long axis of each realized drop: one connected 12-vertex piece per
    drop (the loose 4-vertex plane outline is skipped)."""
    import bmesh
    dg = bpy.context.evaluated_depsgraph_get()
    mw = obj.matrix_world
    bm = bmesh.new()
    bm.from_mesh(obj.evaluated_get(dg).data)
    bm.verts.ensure_lookup_table()
    seen, axes = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, island = [v], []
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            island.append(mw @ cur.co)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        if len(island) != 12:
            continue
        a, b = max(((p, q) for p in island for q in island),
                   key=lambda pq: (pq[0] - pq[1]).length)
        axes.append((a - b).normalized())
    bm.free()
    return axes


def test_rain_sim_streaks():
    bpy.ops.aquasuite.rain_sim_create()
    u = lib.last_uuid()
    e = lib.entry(u)
    e.drop_size = 0.02                       # big enough to measure reliably
    lib.scene().frame_set(12)
    bpy.context.view_layer.update()
    drops = rain_sim.find_rain_drops(lib.entry(u))
    # Visible drops are instances; older trees realized them into mesh.
    axes = _instance_axes(drops) or _drop_axes(drops)
    vertical = sum(abs(a.z) for a in axes) / max(len(axes), 1)
    lib.check("Rain Sim straight rain: vertical streaks", axes and vertical > 0.99,
              f"mean |z| {vertical:.3f} over {len(axes)} drops")

    lib.entry(u).rain_angle = 45.0
    lib.scene().frame_set(13)
    bpy.context.view_layer.update()
    v, _g, t_fall, v_hit = rain_sim.rain_timing(lib.entry(u), lib.scene())
    rel, hit = v.normalized(), v_hit.normalized()
    span = math.degrees(rel.angle(hit)) + 5.0
    drops = rain_sim.find_rain_drops(lib.entry(u))
    axes = _instance_axes(drops) or _drop_axes(drops)
    ok = [a for a in axes
          if max(math.degrees(a.angle(rel)), math.degrees((-a).angle(rel))) >= 0
          and min(math.degrees(a.angle(rel)), math.degrees((-a).angle(rel))) <= span
          and min(math.degrees(a.angle(hit)), math.degrees((-a).angle(hit))) <= span]
    lib.check("Rain Sim 45° rain: streaks between release and impact direction",
              axes and len(ok) / len(axes) > 0.95,
              f"{len(ok)}/{len(axes)} within {span:.0f}° of the fall path")


lib.main(globals())
