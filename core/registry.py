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
from . import presets


class AQS_PoolSourceEntry(bpy.types.PropertyGroup):
    """Restore record for a user mesh serving as Rain-Sim pool water, or as
    one of a Still Water setup's extra water meshes."""
    obj: PointerProperty(type=bpy.types.Object)
    hide_render: BoolProperty(default=False)
    display_type: StringProperty(default="TEXTURED")


@errors.guard_update("AquaSuite couldn't set the floater's waterline")
def _buoy_material_update(self, context):
    """A material or density sets the Buoyancy Offset: the object's origin
    sits where a closed mesh that dense floats.  Sinking densities and open
    meshes leave the offset alone (the panel says why)."""
    from ..level2 import floaters
    if self.material == "MANUAL" or self.obj is None:
        return
    rho = floaters.DENSITY_PRESETS.get(self.material)
    if rho is not None and abs(self.density - rho) > 1e-6:
        self.density = rho  # this update runs again and sets the offset
        return
    if self.density >= floaters.RHO_WATER or not floaters.is_closed(self.obj):
        return
    self.offset = floaters.buoy_offset(self.obj, self.density)


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
    material: EnumProperty(
        name="Material", default="MANUAL", update=_buoy_material_update,
        items=[("MANUAL", "Manual Offset", "Set Buoyancy Offset by hand")]
        + C.float_material_items(floating_only=True),
        description="What the floater is made of: sets how deep it sits "
                    "(Buoyancy Offset)")
    density: FloatProperty(
        name="Density", default=600.0, min=1.0, soft_max=2000.0, precision=0,
        update=_buoy_material_update,
        description="kg/m³. Water is 1000: a Plane Ocean floater must be lighter")


@errors.guard_update("AquaSuite couldn't apply that change")
def _resolution_update(self, context):
    """Single authoritative resolution per liquid assembly.

    HOSE: re-derive the full parameter package (draft halving, velocity
    clamp) so nothing clobbers the user's choice.  STILL: write straight
    to the domain settings.
    """
    if presets.busy(self):
        return
    if self.mode == "HOSE":
        from ..level3 import hose
        hose.apply_regime(context, self)
    elif self.mode == "SIMRAIN":
        from ..level2 import rain_sim
        rain_sim.apply_quality(context, self)
    elif self.mode == C.MODE_SIMOCEAN:
        from ..level2 import simulated_ocean
        simulated_ocean.apply_settings(context, self)
    elif self.mode == "STILL":
        from ..level2 import still_water as sw
        dom = sw.find_domain_object(self)
        dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
            if dom else None
        ds = getattr(dmod, "domain_settings", None)
        if ds is not None:
            ds.resolution_max = (max(16, self.base_resolution // 2)
                                 if self.ww_managed and self.draft else self.base_resolution)
        from . import whitewater
        whitewater.apply(self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _rain_params_update(self, context):
    if presets.busy(self):
        return
    if self.mode != "SIMRAIN":
        return
    from ..level2 import rain_sim
    rain_sim.apply_rain_params(context, self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _rain_domain_update(self, context):
    if presets.busy(self):
        return
    if self.mode != "SIMRAIN":
        return
    from ..level2 import rain_sim
    rain_sim.fit_domain(context, self)
    rain_sim.apply_rain_params(context, self)
    rain_sim.apply_quality(context, self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _rain_area_update(self, context):
    """Rain Area resizes the emitter plane itself, then refits the domain
    around it — the slider changes where rain falls, not just the box."""
    if presets.busy(self) or self.mode != "SIMRAIN":
        return
    from ..level2 import rain_sim
    rain_sim.apply_area(self)
    _rain_domain_update(self, context)


@errors.guard_update("AquaSuite couldn't apply that change")
def _hose_params_update(self, context):
    if presets.busy(self):
        return
    if self.mode != "HOSE":
        return
    from ..level3 import hose
    hose.apply_regime(context, self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't change the water color")
def _hose_color_update(self, context):
    if self.mode != "HOSE":
        return
    from ..level3 import hose
    hose.apply_color(self)


@errors.guard_update("AquaSuite couldn't apply that change")
def _hose_domain_update(self, context):
    if presets.busy(self):
        return
    if self.mode != "HOSE":
        return
    from ..level3 import hose
    hose.fit_domain(context, self)
    hose.apply_regime(context, self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't update whitewater")
def _whitewater_update(self, context):
    if presets.busy(self):
        return
    from . import whitewater
    # Legacy metadata is hydrated on enable/load, before users edit it.
    self.ww_initialized = True
    self.ww_managed = True
    whitewater.apply(self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't update the wave tank")
def _tank_update(self, context):
    if presets.busy(self) or self.mode != C.MODE_SIMOCEAN:
        return
    from ..level2 import simulated_ocean
    simulated_ocean.apply_settings(context, self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't resize whitewater")
def _whitewater_size_update(self, context):
    if presets.busy(self):
        return
    from . import whitewater
    if not self.ww_managed:
        _whitewater_update(self, context)
    else:
        whitewater.apply_sizes(self)
        presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't update the wave period")
def _period_update(self, context):
    if presets.busy(self) or self.mode != C.MODE_SIMOCEAN:
        return
    from ..level2 import simulated_ocean
    simulated_ocean.apply_period(self)
    presets.note_edit(self)


@errors.guard_update("AquaSuite couldn't adjust the lighting")
def _lighting_update(self, context):
    from . import lighting
    lighting.update(self, context)


class AQS_AssemblyEntry(bpy.types.PropertyGroup):
    light_previous_world: PointerProperty(type=bpy.types.World)
    light_world: PointerProperty(type=bpy.types.World)
    light_restore: StringProperty(default='')
    sun_strength: FloatProperty(name='Sun Strength', default=2.0, min=0, soft_max=10, update=_lighting_update)
    sun_angle: FloatProperty(name='Sun Angle', default=0.610865, min=0.01, max=1.570796,
        subtype='ANGLE', update=_lighting_update, description='Sun elevation above the horizon')
    show_advanced: BoolProperty(name='Advanced', default=False,
        description='Show all controls for this setup')
    show_expanded: BoolProperty(name='Expanded', default=True,
        description="Show or hide this setup's controls")
    uuid: StringProperty()
    mode: StringProperty()
    created: StringProperty()
    # Stamp: saved-layout version (0 = pre-release build) and the add-on
    # version that created this assembly.
    data_version: IntProperty(default=0)
    addon_version: StringProperty()
    primary: PointerProperty(type=bpy.types.Object)
    root_collection: PointerProperty(type=bpy.types.Collection)
    preset_id: StringProperty(default="")
    preset_label: StringProperty(default="")
    preset_choice: EnumProperty(name="Preset", items=presets.preset_items)
    preset_modified: BoolProperty(default=False)
    preset_snapshot: StringProperty(default="")
    ww_initialized: BoolProperty(default=False)
    ww_managed: BoolProperty(default=False)
    ww_warning: StringProperty(default="")
    ww_budget: FloatProperty(name="Generation Budget", default=1.0, min=0.0, max=1.0,
        update=_whitewater_update, description="Cap shared whitewater generation. Lower to reduce simulation work; re-bake. Zero disables all secondaries without clearing choices")
    ww_spray: BoolProperty(name="Spray", update=_whitewater_update)
    ww_foam: BoolProperty(name="Foam", update=_whitewater_update)
    ww_bubbles: BoolProperty(name="Bubbles", update=_whitewater_update)
    ww_spray_amount: FloatProperty(name="Amount", default=0.5, min=0, max=1,
        update=_whitewater_update, description="Spray amount; re-bake to update. Zero suspends this element")
    ww_foam_amount: FloatProperty(name="Amount", default=0.5, min=0, max=1,
        update=_whitewater_update, description="Foam amount; re-bake to update. Zero suspends this element")
    ww_bubbles_amount: FloatProperty(name="Amount", default=0.5, min=0, max=1,
        update=_whitewater_update, description="Bubble amount; re-bake to update. Zero suspends this element")
    ww_spray_size: FloatProperty(name="Size", default=0.012, min=0.0001, soft_max=0.1,
        subtype='DISTANCE', update=_whitewater_size_update, description="Spray render radius in metres")
    ww_foam_size: FloatProperty(name="Size", default=0.018, min=0.0001, soft_max=0.1,
        subtype='DISTANCE', update=_whitewater_size_update, description="Foam render radius in metres")
    ww_bubbles_size: FloatProperty(name="Size", default=0.009, min=0.0001, soft_max=0.1,
        subtype='DISTANCE', update=_whitewater_size_update, description="Bubble render radius in metres")
    wave_height: FloatProperty(name="Wave Height", default=0.45, min=0.01, max=2.0,
        subtype='DISTANCE', update=_tank_update, description="Target wave height. The wave maker's push is derived from it, the period and the depth; "
                    "heights that would break are capped (raise Period for taller waves)")
    wave_period: FloatProperty(name="Wave Period", default=2.4, min=0.5, max=12.0,
        update=_period_update, description="Seconds per wave")
    tank_size: FloatVectorProperty(name="Tank Size", size=3, default=(20, 8, 4),
        min=2.0, max=100.0, subtype='XYZ', update=_tank_update)
    # Still Water restore records (source visibility policy §7.1.2/7.1.3)
    source: PointerProperty(type=bpy.types.Object)
    src_hide_render: BoolProperty(default=False)
    src_display_type: StringProperty(default="TEXTURED")
    # Water meshes added or removed since the last bake (Still Water's
    # extra meshes live in pool_sources).
    sources_changed: BoolProperty(default=False)
    # The domain's Flow collection: only these objects pour liquid into it.
    flow_collection: PointerProperty(type=bpy.types.Collection)
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
