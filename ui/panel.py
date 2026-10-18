# SPDX-License-Identifier: GPL-3.0-or-later
"""N-panel "Water" tab (TDD §9)."""

import bpy

from .. import constants as C
from ..core import registry, delete, errors, bakes
from ..core import presets, whitewater
from . import beta, control_spec
from ..level1 import ocean as ocean_mod


class AQS_OT_assembly_delete(bpy.types.Operator):
    bl_idname = "aquasuite.assembly_delete"
    bl_label = "Delete Assembly"
    bl_description = ("Remove everything this assembly created and restore "
                      "your objects' prior state")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()
    delete_cache: bpy.props.BoolProperty(
        name="Also delete bake files",
        default=False,
        description="Remove this assembly's bake cache folder "
                    "(//aquasuite_cache/<id>) from disk. Undo can't bring "
                    "these files back")

    def invoke(self, context, event):
        # Only ask when there is actually a cache on disk to decide about.
        if delete.cache_size_mb(self.uuid) <= 0.0:
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        col = self.layout.column()
        col.label(text=f"Bake files next to the .blend: "
                       f"{_fmt_size(delete.cache_size_mb(self.uuid))}",
                  icon="DISK_DRIVE")
        col.prop(self, "delete_cache", text="Also delete them (can't be undone)")

    def execute(self, context):
        delete.delete_assembly(context.scene, self.uuid,
                               delete_cache=self.delete_cache)
        msg = "AquaSuite assembly deleted; scene restored"
        if self.delete_cache:
            msg += "; bake files removed"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


def _fmt_size(mb):
    return f"{mb / 1024.0:.1f} GB" if mb >= 1024.0 else f"{mb:.0f} MB"


def _draw_ocean(box, context, entry):
    surf = entry.primary
    mod = ocean_mod.find_ocean_modifier(surf, entry.uuid)
    if mod is None:
        box.label(text="Surface missing", icon="ERROR")
        return
    colm = box.column(align=True)
    for name, *_rest in ocean_mod.INPUTS:
        ident = ocean_mod._socket_identifier(mod, name)
        if ident:
            colm.prop(mod, f'["{ident}"]', text=name)
    _draw_floaters(box, entry)


def _draw_floaters(box, entry):
    row = box.row()
    row.label(text=f"Buoys: {len(entry.buoys)}")
    op = row.operator("aquasuite.ocean_attach_buoy", text="", icon="ADD")
    op.uuid = entry.uuid
    for i, b in enumerate(entry.buoys):
        row = box.row(align=True)
        row.label(text=b.obj.name if b.obj else "<missing>", icon="MESH_UVSPHERE")
        row.prop(b, "offset", text="Offset")
        op = row.operator("aquasuite.ocean_detach_buoy", text="", icon="X")
        op.uuid = entry.uuid
        op.buoy_index = i


def _draw_particles(box, entry, fields=('count', 'lifetime', 'particle_size')):
    obj = entry.primary
    psys = obj.particle_systems[0] if obj and obj.particle_systems else None
    if psys is None:
        # Reactive rain binds to the floor; find the emitter in the collection.
        col = entry.root_collection
        if col:
            for o in col.all_objects:
                if o.particle_systems:
                    psys = o.particle_systems[0]
                    break
    if psys is None:
        return
    ps = psys.settings
    colm = box.column(align=True)
    for name in fields:
        colm.prop(ps, name, text={'count': 'Count', 'lifetime': 'Lifetime', 'particle_size': 'Size'}[name])


RES_PRESETS_UI = (
    ("Preview", 48, "Blocky but seconds-fast — layout and timing checks"),
    ("Medium", 96, "Balanced default — most iteration work"),
    ("High", 160, "Final quality for most shots (several GB RAM)"),
    ("Ultra", 256, "Hero close-ups only — very slow, very heavy"),
)


class AQS_OT_set_resolution_custom(bpy.types.Operator):
    bl_idname = "aquasuite.set_resolution_custom"
    bl_label = "Custom Resolution"
    bl_description = ("Freely set any resolution (16–512). Values below 32 "
                      "are great for near-instant viewport iteration — "
                      "chunky water, but immediate feedback")
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()
    resolution: bpy.props.IntProperty(name="Resolution", default=64,
                                      min=16, max=512)

    def invoke(self, context, event):
        entry = registry.get(context.scene, self.uuid)
        if entry is not None:
            self.resolution = entry.base_resolution
        return context.window_manager.invoke_props_dialog(self, width=240)

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        entry.base_resolution = self.resolution
        return {"FINISHED"}


class AQS_OT_set_resolution(bpy.types.Operator):
    bl_idname = "aquasuite.set_resolution"
    bl_label = "Set Simulation Resolution"
    bl_description = "Apply a resolution preset to this liquid assembly"
    bl_options = {"REGISTER", "UNDO"}

    uuid: bpy.props.StringProperty()
    resolution: bpy.props.IntProperty()

    @classmethod
    def description(cls, context, properties):
        for label, res, desc in RES_PRESETS_UI:
            if res == properties.resolution:
                return f"{label} ({res} divisions): {desc}"
        return f"Set resolution to {properties.resolution}"

    def execute(self, context):
        entry = registry.get(context.scene, self.uuid)
        if entry is None:
            return {"CANCELLED"}
        entry.base_resolution = self.resolution  # update callback applies it
        return {"FINISHED"}


def _draw_resolution_buttons(box, entry):
    row = box.row(align=True)
    for label, res, _desc in RES_PRESETS_UI:
        op = row.operator('aquasuite.set_resolution', text=label, depress=entry.base_resolution == res)
        op.uuid, op.resolution = entry.uuid, res


def _draw_fluid_settings(box, entry):
    """Resolution controllers + live cost readout + bake range."""
    from ..level2.still_water import find_domain_object, object_dims
    dom = find_domain_object(entry)
    dmod = next((m for m in dom.modifiers if m.type == "FLUID"), None) \
        if dom else None
    ds = getattr(dmod, "domain_settings", None)
    if ds is None:
        return

    # Preset buttons (highlight the active one) + free Custom entry.
    row = box.row(align=True)
    preset_values = {res for _l, res, _d in RES_PRESETS_UI}
    for label, res, _desc in RES_PRESETS_UI:
        op = row.operator("aquasuite.set_resolution", text=label,
                          depress=(entry.base_resolution == res))
        op.uuid = entry.uuid
        op.resolution = res
    op = row.operator("aquasuite.set_resolution_custom", text="Custom",
                      depress=(entry.base_resolution not in preset_values))
    op.uuid = entry.uuid

    colm = box.column(align=True)
    colm.prop(entry, "base_resolution")

    # Live readout: effective resolution (after Draft halving), voxel
    # size, and rough bake cost relative to Medium(96).
    eff = ds.resolution_max
    longest = max(object_dims(dom)) if dom else 0.0
    if eff > 0 and longest > 0.0:
        dx_cm = longest / eff * 100.0
        cost = (eff / 96.0) ** 3
        note = f"Effective {eff} · voxel {dx_cm:.1f} cm · ~{cost:.1f}× cost"
        if entry.mode in ("HOSE", "SIMRAIN", C.MODE_SIMOCEAN, C.MODE_STILL) and entry.draft and entry.ww_managed:
            note += "  (Draft ½)"
        sub = box.row()
        sub.enabled = False
        sub.label(text=note, icon="SORTTIME" if cost > 3 else "TIME")
        # Absolute memory estimate — the crash-prevention readout.
        from ..level2.rain_sim import memory_estimate
        mcells, gb = memory_estimate(dom, eff)
        sub = box.row()
        sub.alert = gb > 2.0
        sub.label(text=f"≈ {mcells:.1f} M cells · grid only {gb:.2f} GB",
                  icon="ERROR" if gb > 2.0 else "MEMORY")
        from ..core import memory
        allowance = memory.assembly(entry)
        sub = box.row()
        sub.alert = allowance['high'] > 2.0
        sub.label(text=f"Liquid allowance {allowance['low']:.2f}–{allowance['high']:.2f} GB (uncalibrated)")

    row = colm.row(align=True)
    row.prop(ds, "cache_frame_start", text="Bake Start")
    row.prop(ds, "cache_frame_end", text="End")


def _draw_bake(box, entry, op_bake, op_free=None, mandatory=True):
    if bakes.is_baking(entry):
        row = box.row(align=True)
        if entry.mode == C.MODE_RRAIN:
            row.label(text="Baking ripples — press Esc to stop", icon="TIME")
        else:
            row.label(text="Baking…", icon="TIME")
            op = row.operator("aquasuite.cancel_bake", icon="CANCEL")
            op.uuid = entry.uuid
        return
    # Not baked: red Bake.  Baked: blue (pressed-style) Bake Again.
    # Free Bake: red, greyed out while there is nothing to free.
    baked = bakes.has_bake(entry)
    row = box.row(align=True)
    sub = row.row(align=True)
    sub.alert = not baked
    if baked:
        text = "Bake Again"
    else:
        text = "Bake (required)" if mandatory else "Bake"
    op = sub.operator(op_bake, icon="RENDER_ANIMATION", text=text,
                      depress=baked)
    op.uuid = entry.uuid
    if op_free:
        sub = row.row(align=True)
        sub.alert = True
        sub.enabled = baked
        op = sub.operator(op_free, text="", icon="TRASH")
        op.uuid = entry.uuid


def _draw_preset(box, entry):
    col = box.column(align=True)
    col.enabled = not bakes.is_baking(entry)
    label = entry.preset_label or 'Custom'
    if entry.preset_modified:
        label += ' (modified)'
    col.label(text=label, icon='PRESET')
    row = col.row(align=True)
    row.prop(entry, 'preset_choice', text='Preset')
    sub = row.row(align=True)
    sub.enabled = entry.preset_choice != 'CUSTOM'
    op = sub.operator('aquasuite.apply_preset', text='Apply')
    op.uuid = entry.uuid


def _draw_whitewater(box, entry):
    col = box.column(align=True)
    col.enabled = not bakes.is_baking(entry)
    col.label(text='Whitewater')
    col.prop(entry, 'ww_budget')
    col.label(text='Amount: relative density; Budget: shared generation')
    if entry.draft and entry.ww_managed:
        col.label(text='Off while Draft is on', icon='INFO')
    if not entry.ww_managed:
        col.label(text='Existing solver settings; edit to enable controls', icon='INFO')
    for element in whitewater.ELEMENTS:
        row = col.row(align=True)
        row.prop(entry, 'ww_' + element, text=whitewater.NAMES[element])
        sliders = row.row(align=True)
        sliders.enabled = getattr(entry, 'ww_' + element) and not (entry.draft and entry.ww_managed)
        sliders.prop(entry, 'ww_' + element + '_amount', text='Amount')
        sliders.prop(entry, 'ww_' + element + '_size', text='Size')
    if entry.ww_warning:
        warn = col.column()
        warn.alert = True
        warn.label(text=entry.ww_warning, icon='ERROR')


def _draw_simulated_ocean(box, entry, context):
    _draw_spec(box, context, entry)


def _draw_spec(box, context, entry):
    for control in control_spec.controls(entry.mode, entry.show_advanced):
        if control.startswith('entry:'):
            row = box.row()
            row.enabled = not bakes.is_baking(entry)
            name = control.split(':', 1)[1]
            labels = {'rain_density': 'Drop Amount', 'rain_speed': 'Speed', 'rain_angle': 'Angle', 'hose_color': 'Water Color'}
            row.prop(entry, name, **({'text': labels[name]} if name in labels else {}))
        elif control.startswith('ocean:'):
            name = control.split(':', 1)[1]
            mod = ocean_mod.find_ocean_modifier(entry.primary, entry.uuid)
            ident = ocean_mod._socket_identifier(mod, name) if mod else None
            if ident:
                box.prop(mod, f'["{ident}"]', text=name)
        elif control.startswith('particles:'):
            _draw_particles(box, entry, (control.split(':', 1)[1],))
        elif control == 'floaters':
            _draw_floaters(box, entry)
        elif control == 'resolution_buttons':
            _draw_resolution_buttons(box, entry)
        elif control == 'ripples':
            _draw_bake(box, entry, 'aquasuite.bake_ripples', mandatory=False)
        elif control == 'regimes':
            _draw_regimes(box, entry)
        elif control == 'hose_liquid_controls':
            _draw_hose_liquid(box, entry, context)
        elif control == 'pools':
            row = box.row(align=True)
            row.label(text=f'Pool meshes: {len(entry.pool_sources)}')
            row.operator('aquasuite.rain_sim_add_pool', text='', icon='ADD').uuid = entry.uuid
            if entry.show_advanced:
                for rec in entry.pool_sources:
                    box.label(text=rec.obj.name if rec.obj else '<missing>')
        elif control == 'rain_tools':
            for op_id, label in (('rain_sim_rebuild_emitter', 'Rebuild Emitter'), ('rain_sim_optimize', 'Optimize Visible Rain'), ('rain_sim_check', 'Check Pool Link'), ('rain_sim_fit_domain', 'Fit Domain')):
                box.operator('aquasuite.' + op_id, text=label).uuid = entry.uuid
        elif control == 'preset':
            _draw_preset(box, entry)
        elif control == 'fluid':
            _draw_fluid_settings(box, entry)
        elif control == 'whitewater':
            _draw_whitewater(box, entry)
        elif control == 'obstacles':
            _draw_obstacles(box, context)
        elif control == 'bake':
            _draw_bake(box, entry, 'aquasuite.bake_fluid', 'aquasuite.free_fluid')


def _draw_rain_sim(box, entry, context):
    _draw_preset(box, entry)
    colm = box.column(align=True)
    colm.prop(entry, "rain_speed")
    colm.prop(entry, "rain_angle")
    colm.prop(entry, "rain_direction")
    colm.prop(entry, "rain_area")

    from ..level2.rain_sim import (find_emitter, _drops_modifier,
                                   is_legacy_tree)
    gnmod = _drops_modifier(find_emitter(entry), entry.uuid)
    legacy = gnmod is not None and is_legacy_tree(gnmod)
    if gnmod is not None:
        drops = box.column(align=True)
        drops.label(text="Drops", icon="MOD_FLUIDSIM")
        from ..level2.rain_sim import find_rain_drops
        visible = find_rain_drops(entry)
        visible_mod = _drops_modifier(visible, entry.uuid) if visible else None
        if visible_mod and not legacy and ocean_mod.get_input(visible_mod, 'Viewport Fraction') is None:
            upgrade = drops.row()
            upgrade.enabled = not bakes.is_baking(entry)
            op = upgrade.operator('aquasuite.rain_sim_optimize', icon='MOD_PARTICLES')
            op.uuid = entry.uuid
        drops.prop(entry, "rain_density")
        drops.prop(entry, "drop_size")
        drops.prop(entry, "splash_amount")
        drops.prop(entry, "rain_seed")

    if gnmod is None or legacy:
        sub = box.row()
        sub.alert = True
        text = "Emitter missing — Rebuild" if gnmod is None \
            else "Old rain emitter — Rebuild"
        op = sub.operator("aquasuite.rain_sim_rebuild_emitter",
                          text=text, icon="ERROR")
        op.uuid = entry.uuid
    else:
        sub = box.row(align=True)
        op = sub.operator("aquasuite.rain_sim_rebuild_emitter",
                          text="Rebuild Emitter", icon="FILE_REFRESH")
        op.uuid = entry.uuid
        op = sub.operator("aquasuite.rain_sim_check",
                          text="Check Pool Link", icon="VIEWZOOM")
        op.uuid = entry.uuid

    row = box.row(align=True)
    row.label(text=f"Pool meshes: {len(entry.pool_sources)}",
              icon="OUTLINER_COLLECTION")
    op = row.operator("aquasuite.rain_sim_add_pool", text="", icon="ADD")
    op.uuid = entry.uuid
    for rec in entry.pool_sources:
        sub = box.row()
        sub.enabled = False
        sub.label(text=rec.obj.name if rec.obj else "<missing>",
                  icon="MATFLUID")

    _draw_obstacles(box, context)
    row = box.row(align=True)
    row.prop(entry, "draft", toggle=True)
    op = row.operator("aquasuite.rain_sim_fit_domain", text="Fit Domain",
                      icon="SHADING_BBOX")
    op.uuid = entry.uuid
    _draw_fluid_settings(box, entry)
    _draw_whitewater(box, entry)
    _draw_bake(box, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")


def _draw_obstacles(box, context):
    """Shared by every liquid setup: the scene's Water Obstacles."""
    from ..core import obstacles
    n = len(obstacles.members(context.scene))
    row = box.row(align=True)
    row.label(text=f"Water obstacles: {n}", icon="MOD_PHYSICS")
    row.operator("aquasuite.obstacles_add", text="", icon="ADD")
    sub = row.row(align=True)
    sub.enabled = n > 0
    sub.operator("aquasuite.obstacles_remove", text="", icon="REMOVE")


def _draw_hose(box, entry, context):
    _draw_regimes(box, entry)
    colm = box.column(align=True)
    for name in ('pressure', 'spread', 'nozzle_radius', 'hose_color'):
        colm.prop(entry, name)
    _draw_obstacles(box, context)
    _draw_hose_liquid(box, entry, context)


def _draw_regimes(box, entry):
    row = box.row(align=True)
    for rid, label, _desc in C.REGIME_ITEMS:
        op = row.operator("aquasuite.hose_set_regime",
                          text=label.split()[0],
                          depress=(entry.regime == rid))
        op.uuid = entry.uuid
        op.regime = rid


def _draw_hose_liquid(box, entry, context):
    if entry.regime == C.REGIME_MIST:
        return
    row = box.row(align=True)
    row.prop(entry, "hose_liquid", toggle=True,
             text="Simulate Liquid (Beta)",
             icon="CHECKBOX_HLT" if entry.hose_liquid else "CHECKBOX_DEHLT")
    if not entry.hose_liquid:
        return
    _draw_preset(box, entry)
    box.prop(entry, "hose_range")
    from ..level3.hose import clamp_state
    clamp = clamp_state(entry)
    if clamp is not None:
        warn = box.column(align=True)
        warn.alert = True
        warn.label(text=f"Jet slowed to {clamp[0]:.1f} m/s for stability",
                   icon="ERROR")
        warn.label(text="Lower Pressure or Resolution (or use Draft) "
                        "for full speed")
    row = box.row(align=True)
    row.prop(entry, "draft", toggle=True,
             icon="CHECKBOX_HLT" if entry.draft else "CHECKBOX_DEHLT")
    op = row.operator("aquasuite.hose_fit_domain", text="Fit Domain",
                      icon="SHADING_BBOX")
    op.uuid = entry.uuid
    _draw_fluid_settings(box, entry)
    _draw_whitewater(box, entry)
    _draw_bake(box, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")


def _draw_pre_release(box, entry):
    """Setups made before 1.0 keep working as they are; nothing changes
    unless the user rebuilds/recreates them."""
    row = box.row(align=True)
    row.label(text="Made with a pre-release version", icon="INFO")
    if entry.mode == C.MODE_SIMRAIN:
        op = row.operator("aquasuite.rain_sim_rebuild_emitter",
                          text="Rebuild", icon="FILE_REFRESH")
        op.uuid = entry.uuid
    else:
        sub = row.row()
        sub.enabled = False
        sub.label(text="Recreate to update")


class AQS_PT_water(bpy.types.Panel):
    bl_label = "Water"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Water"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "aqs_quality", text="Quality")
        entries = registry.entries(scene)
        advanced = control_spec.advanced_visible(entries)
        from ..core import memory
        low, high = memory.scene_allowance(scene) if advanced else (0, 0)
        if high:
            layout.label(text=f'Liquid total: {low:.2f}–{high:.2f} GB planning allowance')
            layout.label(text='Excludes other geometry, rendering and Blender overhead')

        create = layout.box()
        create.label(text="Create", icon="ADD")
        row = create.row(align=True)
        row.operator("aquasuite.ocean_create", text="Ocean", icon=C.MODE_ICONS[C.MODE_OCEAN])
        row.operator("aquasuite.rain_create", text="Rain", icon=C.MODE_ICONS[C.MODE_RAIN])
        row = create.row(align=True)
        row.operator("aquasuite.rain_reactive_create", text="Reactive Rain")
        row.operator("aquasuite.snow_create", text="Snow")
        row = create.row(align=True)
        row.operator("aquasuite.still_water_create",
                     text="Still Water (active mesh) · Beta")
        row = create.row(align=True)
        row.operator("aquasuite.hose_create", text="Water Hose")
        row.operator("aquasuite.rain_sim_create", text="Rain Sim · Beta",
                     icon=C.MODE_ICONS[C.MODE_SIMRAIN])
        create.operator('aquasuite.simulated_ocean_create',
                        text='Ocean (Simulated) · Beta', icon='MOD_OCEAN')

        entries = registry.entries(scene)
        if not entries:
            return
        if advanced and any(e.mode in presets.LIQUID_MODES and
               (e.mode != C.MODE_HOSE or e.hose_liquid) for e in entries):
            layout.operator('aquasuite.setup_render_layers', icon='RENDERLAYERS')
        layout.separator()
        layout.label(text="Assemblies", icon="OUTLINER_COLLECTION")

        for entry in entries:
            box = layout.box()
            header = box.row(align=True)
            header.label(text=C.MODE_LABELS.get(entry.mode, entry.mode),
                         icon=C.MODE_ICONS.get(entry.mode, "QUESTION"))
            if beta.is_beta(entry.mode) or (entry.mode == C.MODE_HOSE
                                            and entry.hose_liquid):
                header.label(text="Beta", icon="EXPERIMENTAL")
            header.prop(entry, 'show_advanced', text='', icon='PREFERENCES', toggle=True)
            op = header.operator("aquasuite.assembly_delete", text="", icon="TRASH")
            op.uuid = entry.uuid
            if entry.show_advanced and registry.is_pre_release(entry):
                _draw_pre_release(box, entry)

            try:
                self._draw_entry(box, context, entry)
            except Exception as exc:
                err = box.row()
                err.alert = True
                err.label(text="This setup can't be displayed", icon="ERROR")
                errors.record("AquaSuite couldn't draw a setup", exc,
                              mode=entry.mode, uuid=entry.uuid)
                errors.schedule()

    def _draw_entry(self, box, context, entry):
        if entry.mode in control_spec.SIMPLE:
            _draw_spec(box, context, entry)
            return
        if entry.mode == C.MODE_OCEAN:
            _draw_ocean(box, context, entry)
        elif entry.mode in (C.MODE_RAIN, C.MODE_SNOW):
            _draw_particles(box, entry)
        elif entry.mode == C.MODE_RRAIN:
            _draw_particles(box, entry)
            _draw_bake(box, entry, "aquasuite.bake_ripples", mandatory=False)
        elif entry.mode == C.MODE_STILL:
            _draw_preset(box, entry)
            if entry.ww_managed:
                box.prop(entry, 'draft', toggle=True)
            _draw_obstacles(box, context)
            _draw_fluid_settings(box, entry)
            _draw_whitewater(box, entry)
            _draw_bake(box, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")
        elif entry.mode == C.MODE_HOSE:
            _draw_hose(box, entry, context)
        elif entry.mode == C.MODE_SIMRAIN:
            _draw_rain_sim(box, entry, context)
        elif entry.mode == C.MODE_SIMOCEAN:
            _draw_simulated_ocean(box, entry, context)


CLASSES = (AQS_OT_assembly_delete, AQS_OT_set_resolution,
           AQS_OT_set_resolution_custom, AQS_PT_water)
