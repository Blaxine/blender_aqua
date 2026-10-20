# SPDX-License-Identifier: GPL-3.0-or-later
"""Water Hose: real-time jets per regime, Mist, the liquid toggle, Water
Color, and that the particles can render."""

import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib  # noqa: E402

import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402
from aquasuite.level2 import still_water as sw  # noqa: E402
from aquasuite.level3 import hose  # noqa: E402

C = lib.C
U = {}


def _parts(entry):
    em = hose._find_emitter(entry)
    jet, jet_mod = hose._psys(em, "jet")
    mist, mist_mod = hose._psys(em, "mist")
    flow = next((m for m in em.modifiers if m.type == "FLUID"), None)
    dom = hose._find_domain(entry)
    dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None)
    return em, jet_mod, mist_mod, flow, dmod


def _visible(mod):
    return bool(mod and mod.show_viewport and mod.show_render)


def _alive(entry, role, frames=24):
    for f in range(1, frames + 1):
        lib.scene().frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    em = hose._find_emitter(entry).evaluated_get(dg)
    psys, _ = hose._psys(em, role)
    return [p for p in psys.particles if p.alive_state == "ALIVE"]


def test_setup():
    lib.scene().frame_start, lib.scene().frame_end = 1, 48
    bpy.ops.aquasuite.hose_create()
    U["h"] = lib.last_uuid()
    noz = lib.entry(U["h"]).primary
    noz.location = (0, 0, 3)
    # cone tipped down, then swung 60 degrees toward +X: aim +X and down
    noz.rotation_euler = (Matrix.Rotation(math.radians(-60), 3, 'Y')
                          @ Matrix.Rotation(-math.pi / 2, 3, 'X')).to_euler()
    bpy.context.view_layer.update()
    lib.check("hose created", lib.entry(U["h"]) is not None)


def test_jet_by_default_no_bake():
    e = lib.entry(U["h"])
    em, jet_mod, mist_mod, flow, dmod = _parts(e)
    lib.check("Normal: jet on, mist and liquid off",
              _visible(jet_mod) and not _visible(mist_mod)
              and not _visible(flow) and not _visible(dmod) and not e.hose_liquid)
    lib.check("particles can render (emitter renders, disc itself hidden)",
              not em.hide_render and not em.show_instancer_for_render)


def _direction_stats(entry):
    alive = _alive(entry, "jet")
    aim = hose._aim_direction(entry.primary)
    now = lib.scene().frame_current
    young = [p for p in alive if now - p.birth_time < 3] or alive
    dots = [p.velocity.normalized().dot(aim) for p in young if p.velocity.length > 1e-3]
    speed = sum(p.velocity.length for p in young) / max(len(young), 1)
    return len(alive), (sum(dots) / max(len(dots), 1)), speed


def test_regimes():
    u = U["h"]
    n, along, v_normal = _direction_stats(lib.entry(u))
    lib.check("Normal: a coherent jet along the aim", n > 1000 and along > 0.97,
              f"{n} droplets, mean cos to aim {along:.3f}")
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="SPRAY")
    n, along_spray, _ = _direction_stats(lib.entry(u))
    lib.check("Spray: wider than Normal", n > 1000 and along_spray < along,
              f"cos {along_spray:.3f} vs Normal {along:.3f}")
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="BLAST")
    n, _along, v_blast = _direction_stats(lib.entry(u))
    lib.check("Blast: much faster than Normal", v_blast > 1.8 * v_normal,
              f"{v_blast:.1f} vs {v_normal:.1f} m/s")
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="MIST")
    em, jet_mod, mist_mod, flow, dmod = _parts(lib.entry(u))
    lib.check("Mist: mist on, jet and liquid off",
              _visible(mist_mod) and not _visible(jet_mod) and not _visible(flow))
    lib.check("Mist emits", len(_alive(lib.entry(u), "mist")) > 100)
    bpy.ops.aquasuite.hose_set_regime(uuid=u, regime="NORMAL")


def test_liquid_toggle():
    u = U["h"]
    lib.entry(u).hose_liquid = True
    em, jet_mod, mist_mod, flow, dmod = _parts(lib.entry(u))
    lib.check("Simulate Liquid: liquid on, jet off",
              _visible(flow) and _visible(dmod) and not _visible(jet_mod))
    lib.entry(u).hose_liquid = False
    em, jet_mod, mist_mod, flow, dmod = _parts(lib.entry(u))
    lib.check("liquid off again: jet back, liquid off",
              _visible(jet_mod) and not _visible(flow) and not _visible(dmod))


def test_water_color():
    u = U["h"]
    lib.entry(u).hose_color = (0.2, 0.6, 0.3)
    e = lib.entry(u)
    colors = []
    for obj in e.root_collection.all_objects:
        for slot in obj.material_slots:
            if slot.material and slot.material.use_nodes:
                for node in slot.material.node_tree.nodes:
                    if node.type in ("BSDF_GLASS", "BSDF_TRANSLUCENT"):
                        colors.append(tuple(round(c, 3) for c in node.inputs["Color"].default_value[:3]))
    lib.check("Water Color tints jet, mist and liquid materials",
              len(colors) >= 3 and all(c == (0.2, 0.6, 0.3) for c in colors), str(colors))



def _cone_axis(nozzle):
    """Where the Cone empty points: its local +Y."""
    return (sw.world_matrix(nozzle).to_3x3() @ Vector((0, 1, 0))).normalized()


def _disc_normal(emitter):
    return (sw.world_matrix(emitter).to_3x3()
            @ emitter.data.polygons[0].normal).normalized()


def test_cone_shows_aim():
    bpy.ops.aquasuite.hose_create()
    e = lib.entry(lib.last_uuid())
    noz, em = e.primary, hose._find_emitter(e)
    aim = hose._aim_direction(noz)
    lib.check("new hose: the cone points where the jet fires (straight down)",
              aim.dot(_cone_axis(noz)) > 0.999 and aim.z < -0.999
              and aim.dot(_disc_normal(em)) > 0.999,
              f"aim {tuple(round(c, 3) for c in aim)}")

    noz.rotation_euler = Euler((math.radians(-30), 0, math.radians(50)))
    hose.fit_domain(bpy.context, e)
    bpy.context.view_layer.update()
    aim = hose._aim_direction(noz)
    end = sw.world_matrix(noz).translation + aim * e.hose_range
    dmin, dmax = sw.world_bbox(hose._find_domain(e))
    lib.check("re-aimed hose: jet, emitter disc and fitted domain follow the cone",
              aim.dot(_cone_axis(noz)) > 0.999 and aim.dot(_disc_normal(em)) > 0.999
              and all(dmin[i] < end[i] < dmax[i] for i in range(3)),
              f"aim {tuple(round(c, 3) for c in aim)}, cone "
              f"{tuple(round(c, 3) for c in _cone_axis(noz))}")

    # A rig saved before 0.20: untilted disc, jet along the nozzle's -Z.
    noz.rotation_euler = (0.0, 0.0, 0.0)
    em.rotation_euler = (0.0, 0.0, 0.0)
    aim = hose._aim_direction(noz)
    lib.check("older hose rigs keep spraying where they did (nozzle -Z)",
              aim.z < -0.999 and aim.dot(_disc_normal(em)) > 0.999,
              f"aim {tuple(round(c, 3) for c in aim)}")


lib.main(globals())
