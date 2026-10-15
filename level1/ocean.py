# SPDX-License-Identifier: GPL-3.0-or-later
"""Plane Ocean (TDD §6.1, buoys per R1.5).

The surface is a procedurally generated grid displaced by a summed
Gerstner stack built programmatically as a Geometry Nodes tree.  Layer
constants are baked from :mod:`..gerstner` so the Python buoy handler
and the node tree agree exactly.

This build: wake solver not included (see README — roadmap); buoys are
closed-form deterministic (farm-safe with no bake) and remain wake
*injector-ready* for the wake build.
"""

import math

import bpy
import bmesh
from bpy.props import StringProperty

from .. import constants as C
from .. import gerstner
from ..core import delete, naming, registry
from ..materials import mats

MODIFIER_NAME = "AquaSuite Ocean"
NG_NAME = "AQS_GN_OceanSurface"

# UI-exposed inputs (name, socket_type, default, min, max, description)
INPUTS = (
    ("Size", "NodeSocketFloat", 30.0, 1.0, 2000.0, "Edge length of the surface (m)"),
    ("Resolution", "NodeSocketInt", 128, 16, 512, "Grid vertices per side (PREVIEW tier halves this)"),
    ("Amplitude", "NodeSocketFloat", 0.18, 0.0, 10.0, "Height of the primary swell (m)"),
    ("Wavelength", "NodeSocketFloat", 6.0, 0.1, 500.0, "Primary wavelength (m)"),
    ("Choppiness", "NodeSocketFloat", 0.4, 0.0, 1.0, "Gerstner horizontal pinch (clamped internally for stability)"),
    ("Direction", "NodeSocketFloat", 0.0, -360.0, 360.0, "Primary travel direction (degrees)"),
    ("Spread", "NodeSocketFloat", 0.35, 0.0, 1.5, "Directional spread between wave layers"),
    ("Speed", "NodeSocketFloat", 1.0, 0.0, 5.0, "Multiplier on the dispersion-derived wave speed"),
)


# --------------------------------------------------------------------------
# Node tree construction
# --------------------------------------------------------------------------

def _math(nt, op, a=None, b=None, value0=None, value1=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    if value0 is not None:
        n.inputs[0].default_value = value0
    if value1 is not None:
        n.inputs[1].default_value = value1
    if a is not None:
        nt.links.new(a, n.inputs[0])
    if b is not None:
        nt.links.new(b, n.inputs[1])
    return n


def build_ocean_tree(mode, uuid_):
    nt = bpy.data.node_groups.new(NG_NAME, "GeometryNodeTree")
    naming.tag(nt, mode, uuid_)
    nt[C.BUILD_PROP] = C.BUILD_TAG
    nt.is_modifier = True

    iface = nt.interface
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, stype, default, vmin, vmax, desc in INPUTS:
        s = iface.new_socket(name, in_out="INPUT", socket_type=stype)
        s.default_value = default
        try:
            s.min_value, s.max_value = vmin, vmax
        except AttributeError:
            pass
        s.description = desc

    gin = nt.nodes.new("NodeGroupInput")
    gout = nt.nodes.new("NodeGroupOutput")

    grid = nt.nodes.new("GeometryNodeMeshGrid")
    nt.links.new(gin.outputs["Size"], grid.inputs["Size X"])
    nt.links.new(gin.outputs["Size"], grid.inputs["Size Y"])
    nt.links.new(gin.outputs["Resolution"], grid.inputs["Vertices X"])
    nt.links.new(gin.outputs["Resolution"], grid.inputs["Vertices Y"])

    pos = nt.nodes.new("GeometryNodeInputPosition")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(pos.outputs["Position"], sep.inputs["Vector"])

    time = nt.nodes.new("GeometryNodeInputSceneTime")  # Seconds: FPS-independent (§6.1.4)

    dir_rad = _math(nt, "RADIANS", a=gin.outputs["Direction"])
    n_layers = gerstner.N_LAYERS
    accum = None

    for i in range(n_layers):
        amp_f = gerstner.AMP_DECAY ** i
        wl_f = gerstner.WL_FALLOFF ** i
        d_off = gerstner.DIR_OFFSETS[i]

        amp = _math(nt, "MULTIPLY", a=gin.outputs["Amplitude"], value1=amp_f)
        wl = _math(nt, "MULTIPLY", a=gin.outputs["Wavelength"], value1=wl_f)
        wl = _math(nt, "MAXIMUM", a=wl.outputs[0], value1=1e-4)
        k = _math(nt, "DIVIDE", b=wl.outputs[0], value0=gerstner.TWO_PI)

        # omega = sqrt(g*k) * Speed
        gk = _math(nt, "MULTIPLY", a=k.outputs[0], value1=gerstner.G)
        omega = _math(nt, "SQRT", a=gk.outputs[0])
        omega = _math(nt, "MULTIPLY", a=omega.outputs[0], b=gin.outputs["Speed"])

        # theta = dir_rad + DIR_OFFSETS[i] * Spread
        off = _math(nt, "MULTIPLY", a=gin.outputs["Spread"], value1=d_off)
        theta = _math(nt, "ADD", a=dir_rad.outputs[0], b=off.outputs[0])
        cth = _math(nt, "COSINE", a=theta.outputs[0])
        sth = _math(nt, "SINE", a=theta.outputs[0])

        # phase = k*(x*cos + y*sin) - omega*t
        xc = _math(nt, "MULTIPLY", a=sep.outputs["X"], b=cth.outputs[0])
        ys = _math(nt, "MULTIPLY", a=sep.outputs["Y"], b=sth.outputs[0])
        dot = _math(nt, "ADD", a=xc.outputs[0], b=ys.outputs[0])
        kdot = _math(nt, "MULTIPLY", a=k.outputs[0], b=dot.outputs[0])
        wt = _math(nt, "MULTIPLY", a=omega.outputs[0], b=time.outputs["Seconds"])
        phase = _math(nt, "SUBTRACT", a=kdot.outputs[0], b=wt.outputs[0])
        sinp = _math(nt, "SINE", a=phase.outputs[0])
        cosp = _math(nt, "COSINE", a=phase.outputs[0])

        # QA = min(Choppiness / (k*N), A)  — stability clamp §6.1.4
        kn = _math(nt, "MULTIPLY", a=k.outputs[0], value1=float(n_layers))
        qa = _math(nt, "DIVIDE", a=gin.outputs["Choppiness"], b=kn.outputs[0])
        qa = _math(nt, "MINIMUM", a=qa.outputs[0], b=amp.outputs[0])

        qac = _math(nt, "MULTIPLY", a=qa.outputs[0], b=cosp.outputs[0])
        ox = _math(nt, "MULTIPLY", a=qac.outputs[0], b=cth.outputs[0])
        oy = _math(nt, "MULTIPLY", a=qac.outputs[0], b=sth.outputs[0])
        oz = _math(nt, "MULTIPLY", a=amp.outputs[0], b=sinp.outputs[0])

        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(ox.outputs[0], comb.inputs["X"])
        nt.links.new(oy.outputs[0], comb.inputs["Y"])
        nt.links.new(oz.outputs[0], comb.inputs["Z"])

        if accum is None:
            accum = comb
        else:
            vadd = nt.nodes.new("ShaderNodeVectorMath")
            vadd.operation = "ADD"
            nt.links.new(accum.outputs[0], vadd.inputs[0])
            nt.links.new(comb.outputs[0], vadd.inputs[1])
            accum = vadd

    setpos = nt.nodes.new("GeometryNodeSetPosition")
    nt.links.new(grid.outputs["Mesh"], setpos.inputs["Geometry"])
    nt.links.new(accum.outputs[0], setpos.inputs["Offset"])

    smooth = nt.nodes.new("GeometryNodeSetShadeSmooth")
    nt.links.new(setpos.outputs["Geometry"], smooth.inputs["Geometry"])
    nt.links.new(smooth.outputs["Geometry"], gout.inputs["Geometry"])

    # Rough auto-layout so the tree is inspectable, not a node pile.
    for idx, node in enumerate(nt.nodes):
        node.location = ((idx % 14) * 190, -(idx // 14) * 220)
    gin.location = (-500, 300)
    gout.location = (14 * 190 + 300, 0)
    return nt


# --------------------------------------------------------------------------
# Modifier input IO (identifier-tolerant)
# --------------------------------------------------------------------------

def find_ocean_modifier(obj, assembly_uuid=None):
    """The GN modifier running an AquaSuite ocean tree.

    Identified by the node group's ``aqs_owner`` tag, never its name —
    users may rename the tree (README: "Names are yours").  With
    ``assembly_uuid`` only that assembly's tree matches.
    """
    if obj is None:
        return None
    for mod in obj.modifiers:
        if mod.type != "NODES" or mod.node_group is None:
            continue
        owner = mod.node_group.get(C.OWNER_PROP, "")
        if not isinstance(owner, str) \
                or not owner.startswith(C.MODE_OCEAN + ":"):
            continue
        if assembly_uuid is None or owner.endswith(":" + assembly_uuid):
            return mod
    return None


def _socket_identifier(mod, name):
    for item in mod.node_group.interface.items_tree:
        if getattr(item, "in_out", "") == "INPUT" and item.name == name:
            return item.identifier
    return None


def get_input(mod, name):
    ident = _socket_identifier(mod, name)
    if ident is None:
        return None
    try:
        return mod[ident]
    except KeyError:
        for item in mod.node_group.interface.items_tree:
            if item.identifier == ident:
                return item.default_value
    return None


def set_input(mod, name, value):
    ident = _socket_identifier(mod, name)
    if ident is not None:
        mod[ident] = value
        mod.id_data.update_tag()


def read_wave_params(mod):
    """Live parameters -> kwargs for gerstner.layer_params (handler use)."""
    g = lambda n, d: (get_input(mod, n) if get_input(mod, n) is not None else d)
    return dict(
        amplitude=float(g("Amplitude", 0.18)),
        wavelength=float(g("Wavelength", 6.0)),
        direction_deg=float(g("Direction", 0.0)),
        spread=float(g("Spread", 0.35)),
        speed_mult=float(g("Speed", 1.0)),
        choppiness=float(g("Choppiness", 0.4)),
    )


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class AQS_OT_ocean_create(bpy.types.Operator):
    bl_idname = "aquasuite.ocean_create"
    bl_label = "Create Plane Ocean"
    bl_description = "One-click Gerstner ocean surface with buoy support"
    bl_options = {"REGISTER", "UNDO"}

    @delete.guarded_create
    def execute(self, context):
        scene = context.scene
        uid = naming.new_uuid()
        col = naming.new_assembly_collection(scene, C.MODE_OCEAN, uid)

        mesh = bpy.data.meshes.new("AQS_Ocean_Surface")
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bm.to_mesh(mesh)
        bm.free()

        surf = naming.new_mesh_object(col, "AQS_Ocean_Surface", mesh,
                                      C.MODE_OCEAN, uid)
        nt = build_ocean_tree(C.MODE_OCEAN, uid)
        mod = surf.modifiers.new(MODIFIER_NAME, "NODES")
        mod.node_group = nt

        # volume=False: a volume shader on an OPEN plane renders black in
        # Cycles (rays enter, never exit). Volume is for closed domains only.
        mats.assign(surf, mats.water_surface(C.MODE_OCEAN, uid, volume=False))
        registry.add(scene, C.MODE_OCEAN, uid, primary=surf, root_collection=col)

        context.view_layer.objects.active = surf
        self.report({"INFO"}, "AquaSuite: Plane Ocean created")
        return {"FINISHED"}


class AQS_OT_ocean_attach_buoy(bpy.types.Operator):
    bl_idname = "aquasuite.ocean_attach_buoy"
    bl_label = "Attach Floater"
    bl_description = ("Make the active object bob on this ocean "
                      "(deterministic, farm-safe — no keyframes on your object)")
    bl_options = {"REGISTER", "UNDO"}

    uuid: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        scene = context.scene
        entry = registry.get(scene, self.uuid)
        obj = context.active_object
        if entry is None or entry.primary is None:
            self.report({"ERROR"}, "Ocean assembly not found")
            return {"CANCELLED"}
        if C.OWNER_PROP in obj.keys() or C.SRC_PROP in obj.keys():
            self.report({"ERROR"}, "AQS-E011: " + C.MSG["E011"])
            return {"CANCELLED"}
        for b in entry.buoys:
            if b.obj == obj:
                self.report({"WARNING"}, "Already a floater on this ocean")
                return {"CANCELLED"}

        empty = bpy.data.objects.new(f"AQS_Ocean_Buoy_{len(entry.buoys)}", None)
        empty.empty_display_type = "SPHERE"
        empty.empty_display_size = 0.15
        naming.tag(empty, C.MODE_OCEAN, self.uuid)
        naming.link_object(entry.root_collection, empty)
        empty.location = obj.matrix_world.translation

        added = []
        cz = obj.constraints.new("COPY_LOCATION")
        cz.name = "AQS Buoy Z"
        cz.target = empty
        cz.use_x = cz.use_y = False
        cz.use_z = True
        added.append(cz.name)
        cr = obj.constraints.new("COPY_ROTATION")
        cr.name = "AQS Buoy Tilt"
        cr.target = empty
        cr.mix_mode = "ADD"
        added.append(cr.name)

        b = entry.buoys.add()
        b.obj = obj
        b.empty = empty
        b.radius = max(max(obj.dimensions.x, obj.dimensions.y) * 0.5, 0.05)
        # XY only: a tall mast must not inflate the wave-sample radius
        b.added_constraints = ";".join(added)

        self.report({"INFO"}, f"Floater attached: {obj.name}")
        return {"FINISHED"}


class AQS_OT_ocean_detach_buoy(bpy.types.Operator):
    bl_idname = "aquasuite.ocean_detach_buoy"
    bl_label = "Detach Floater"
    bl_options = {"REGISTER", "UNDO"}

    uuid: StringProperty()
    buoy_index: bpy.props.IntProperty()

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None or self.buoy_index >= len(entry.buoys):
            return {"CANCELLED"}
        b = entry.buoys[self.buoy_index]
        if b.obj is not None:
            for n in [n for n in (b.added_constraints or "").split(";") if n]:
                con = b.obj.constraints.get(n)
                if con:
                    b.obj.constraints.remove(con)
        if b.empty is not None:
            bpy.data.objects.remove(b.empty, do_unlink=True)
        entry.buoys.remove(self.buoy_index)
        return {"FINISHED"}


CLASSES = (AQS_OT_ocean_create, AQS_OT_ocean_attach_buoy,
           AQS_OT_ocean_detach_buoy)
