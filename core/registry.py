# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level assembly registry (TDD §4.3, pointer-based per R1.1)."""

import bpy
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
    BoolProperty,
)

from .. import constants as C
from . import errors


class AQS_PoolSourceEntry(bpy.types.PropertyGroup):
    """Restore record for a user mesh serving as Rain-Sim pool water."""
    obj: PointerProperty(type=bpy.types.Object)
    hide_render: BoolProperty(default=False)
    display_type: StringProperty(default="TEXTURED")


class AQS_BuoyEntry(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object, name="Floater")
    empty: PointerProperty(type=bpy.types.Object, name="Driver Empty")
    radius: FloatProperty(name="Sample Radius", default=0.5, min=0.01)
    offset: FloatProperty(
        name="Buoyancy Offset", default=0.0, soft_min=-2.0, soft_max=2.0,
        description="Vertical offset of the waterline on the floater")
    smoothing: FloatProperty(
        name="Bob Smoothing", default=0.35, min=0.0, soft_max=2.0,
        description="Seconds of stateless FIR smoothing (deterministic)")
    tilt: FloatProperty(
        name="Tilt Amount", default=1.0, min=0.0, soft_max=3.0,
        description="Pitch/roll response to the local wave gradient")
    added_constraints: StringProperty(default="")  # ';'-joined names, restore record


@errors.guard_update("AquaSuite couldn't apply that change")
def _resolution_update(self, context):
    """Single authoritative resolution per liquid assembly.

    HOSE: re-derive the full parameter package (draft halving, velocity
    clamp) so nothing clobbers the user's choice.  STILL: write straight
    to the domain settings.
    """
    if self.mode == "HOSE":
        from ..level3 import hose
        hose.apply_regime(context, self)
    elif self.mode == "SIMRAIN":
        from ..level2 import rain_sim
        rain_sim.apply_quality(context, self)
    elif self.mode == "STILL":
        from ..level2 import still_water as sw
        dom = sw.find_domain_object(self)
        dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
            if dom else None
        ds = getattr(dmod, "domain_settings", None)
        if ds is not None:
            ds.resolution_max = int(self.base_resolution)


@errors.guard_update("AquaSuite couldn't apply that change")
def _rain_params_update(self, context):
    if self.mode != "SIMRAIN":
        return
    from ..level2 import rain_sim
    rain_sim.apply_rain_params(context, self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _rain_domain_update(self, context):
    if self.mode != "SIMRAIN":
        return
    from ..level2 import rain_sim
    rain_sim.fit_domain(context, self)
    rain_sim.apply_rain_params(context, self)
    rain_sim.apply_quality(context, self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _rain_area_update(self, context):
    """Rain Area resizes the emitter plane itself, then refits the domain
    around it — the slider changes where rain falls, not just the box."""
    if self.mode != "SIMRAIN":
        return
    from ..level2 import rain_sim
    rain_sim.apply_area(self)
    _rain_domain_update(self, context)


@errors.guard_update("AquaSuite couldn't apply that change")
def _hose_params_update(self, context):
    if self.mode != "HOSE":
        return
    from ..level3 import hose
    hose.apply_regime(context, self)


@errors.guard_update("AquaSuite couldn't change the water color")
def _hose_color_update(self, context):
    if self.mode != "HOSE":
        return
    from ..level3 import hose
    hose.apply_color(self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _hose_domain_update(self, context):
    if self.mode != "HOSE":
        return
    from ..level3 import hose
    hose.fit_domain(context, self)
    hose.apply_regime(context, self)


class AQS_AssemblyEntry(bpy.types.PropertyGroup):
    uuid: StringProperty()
    mode: StringProperty()
    created: StringProperty()
    # Stamp: saved-layout version (0 = pre-release build) and the add-on
    # version that created this assembly.
    data_version: IntProperty(default=0)
    addon_version: StringProperty()
    primary: PointerProperty(type=bpy.types.Object)
    root_collection: PointerProperty(type=bpy.types.Collection)
    # Still Water restore records (source visibility policy §7.1.2/7.1.3)
    source: PointerProperty(type=bpy.types.Object)
    src_hide_render: BoolProperty(default=False)
    src_display_type: StringProperty(default="TEXTURED")
    # Hose
    regime: EnumProperty(items=C.REGIME_ITEMS, default=C.REGIME_NORMAL)
    pressure: FloatProperty(
        name="Pressure", default=1.0, min=0.05, max=1.5, subtype="FACTOR",
        update=_hose_params_update,
        description="Scales jet velocity. Automatically clamped to what the "
                    "solver can integrate stably at the current resolution")
    hose_range: FloatProperty(
        name="Range", default=6.0, min=0.5, max=50.0, subtype="DISTANCE",
        update=_hose_domain_update,
        description="How far the jet must reach; drives the fitted domain size")
    spread: FloatProperty(
        name="Spread Angle", default=6.0, min=0.0, max=45.0,
        update=_hose_domain_update,
        description="Cone half-angle in degrees (widens mist and breaks up "
                    "liquid regimes)")
    nozzle_radius: FloatProperty(
        name="Nozzle Radius", default=0.03, min=0.005, max=0.2,
        subtype="DISTANCE", update=_hose_params_update,
        description="Physical emitter radius")
    hose_liquid: BoolProperty(
        name="Simulate Liquid", default=False, update=_hose_params_update,
        description="Beta: replace the real-time jet with a Mantaflow "
                    "liquid simulation (pools and splashes, but must be "
                    "baked and is much thicker than a real jet)")
    hose_color: FloatVectorProperty(
        name="Water Color", size=3, subtype="COLOR", min=0.0, max=1.0,
        default=(0.85, 0.92, 1.0), update=_hose_color_update,
        description="Tint of the hose water: jet droplets, mist and "
                    "simulated liquid")
    draft: BoolProperty(
        name="Draft Quality", default=True,
        update=_resolution_update,
        description="Half resolution, 1x mesh, no secondary particles — "
                    "roughly 8-15x faster bakes for iteration. Turn off "
                    "for the final bake")
    # Rain Simulation
    pool_collection: PointerProperty(type=bpy.types.Collection)
    pool_sources: CollectionProperty(type=AQS_PoolSourceEntry)
    rain_area: FloatProperty(
        name="Rain Area", default=4.0, min=1.0, max=30.0, subtype="DISTANCE",
        update=_rain_area_update,
        description="Edge of the rained-on square — resizes the emitter "
                    "plane and the fitted domain (memory scales with area)")
    rain_speed: FloatProperty(
        name="Speed", default=9.0, min=1.0, max=20.0,
        update=_rain_params_update, description="Drop speed in m/s")
    rain_angle: FloatProperty(
        name="Angle", default=0.0, min=0.0, max=60.0,
        update=_rain_domain_update,
        description="Tilt from vertical (degrees) — wind-blown rain. Also "
                    "widens the fitted domain to cover the drift")
    rain_direction: FloatProperty(
        name="Direction", default=0.0, min=0.0, max=360.0,
        update=_rain_domain_update,
        description="Compass heading of the tilt (degrees)")
    rain_density: FloatProperty(
        name="Drop Amount", default=6.0, min=0.05, soft_max=100.0,
        update=_rain_params_update,
        description="Drops per square metre of the emitter (stays the same "
                    "when Rain Area changes)")
    drop_size: FloatProperty(
        name="Drop Size", default=0.0025, min=0.0005, soft_max=0.05,
        subtype="DISTANCE", update=_rain_params_update,
        description="Radius of the rendered raindrops (real rain: 1-3 mm). "
                    "The splash liquid injected at impact is never smaller "
                    "than ~1 voxel, or the solver can't see it")
    splash_amount: FloatProperty(
        name="Splash Amount", default=0.1, min=0.0, max=1.0,
        subtype="FACTOR", update=_rain_params_update,
        description="Share of raindrops that splash into the simulated "
                    "water. Every drop still renders; each splash is a "
                    "grid-sized blob carrying far more water than a real "
                    "drop, so higher values fill the domain faster")
    rain_seed: IntProperty(
        name="Seed", default=0, min=0, update=_rain_params_update,
        description="Random layout of the drops")
    base_resolution: IntProperty(
        name="Resolution", default=96, min=16, max=512,
        update=_resolution_update,
        description="Voxel grid divisions on the domain's longest side (16 = chunky but instant viewport). "
                    "Bake time and RAM scale roughly with the CUBE of this "
                    "value: 96→160 is ~5x slower, 160→256 another ~4x")
    buoys: CollectionProperty(type=AQS_BuoyEntry)


def entries(scene):
    return scene.aqs_assemblies


def get(scene, assembly_uuid):
    for e in scene.aqs_assemblies:
        if e.uuid == assembly_uuid:
            return e
    return None


def add(scene, mode, assembly_uuid, primary=None, root_collection=None):
    import datetime
    e = scene.aqs_assemblies.add()
    e.uuid = assembly_uuid
    e.mode = mode
    e.created = datetime.date.today().isoformat()
    e.data_version = C.DATA_VERSION
    e.addon_version = C.ADDON_VERSION
    if primary is not None:
        e.primary = primary
    if root_collection is not None:
        e.root_collection = root_collection
    return e


def is_pre_release(entry):
    """Made by a pre-1.0 build: no compatibility promise, offer a rebuild."""
    return entry.data_version < 1


def remove(scene, assembly_uuid):
    for i, e in enumerate(scene.aqs_assemblies):
        if e.uuid == assembly_uuid:
            scene.aqs_assemblies.remove(i)
            return True
    return False


CLASSES = (AQS_PoolSourceEntry, AQS_BuoyEntry, AQS_AssemblyEntry)
