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


def _wrap(text, width):
    import textwrap
    return textwrap.wrap(text, width) or [text]


def _draw_wave_limit(box, entry):
    """Say so when the requested waves would break and were capped — and
    what to change to get taller ones.  Tanks from before 0.20 still have
    the paddle, whose waves barely travel: offer the upgrade."""
    from ..level2 import simulated_ocean
    height, _amplitude = simulated_ocean.wave_plan(entry)
    if height < entry.wave_height - 0.005:
        row = box.row()
        row.alert = True
        row.label(text=f"Waves this steep break — capped at {height:.2f} m. "
                       "Raise Period for taller waves", icon='INFO')
    warning = simulated_ocean.resolution_warning(
        entry, [(label, res) for label, res, _d in RES_PRESETS_UI])
    if warning:
        col = box.column(align=True)
        col.alert = True
        for i, line in enumerate(_wrap(warning, 60)):
            col.label(text=line, icon='ERROR' if i == 0 else 'BLANK1')
    if simulated_ocean.is_legacy(entry):
        box.label(text="This tank uses the old paddle; its waves barely travel", icon='INFO')
        box.operator('aquasuite.simulated_ocean_upgrade', icon='FILE_REFRESH').uuid = entry.uuid


def _draw_spec(box, context, entry):
    root = box
    baking = bakes.is_baking(entry)
    for control in control_spec.controls(entry.mode, entry.show_advanced):
        # Keep Cancel/Bake live, but do not alter a running simulation through
        # a preset button or one of the grouped advanced controls.
        box = root.column()
        box.enabled = not baking or control in ('bake', 'ripples', 'hose_liquid_controls')
        if control.startswith(('entry:', 'ocean:', 'particles:')):
            # Label on the left, value on the right: easier to scan.
            box.use_property_split = True
            box.use_property_decorate = False
        if control.startswith('entry:'):
            row = box.row()
            row.enabled = not baking
            name = control.split(':', 1)[1]
            labels = {'rain_density': 'Drop Amount', 'rain_speed': 'Speed', 'rain_angle': 'Angle', 'hose_color': 'Water Color'}
            row.prop(entry, name, **({'text': labels[name]} if name in labels else {}))
            if name == 'wave_period' and entry.mode == C.MODE_SIMOCEAN:
                _draw_wave_limit(box, entry)
        elif control.startswith('ocean:'):
            name = control.split(':', 1)[1]
            mod = ocean_mod.find_ocean_modifier(entry.primary, entry.uuid)
            owner, path = ocean_mod.input_prop(mod, name) if mod else (None, None)
            if owner is not None:
                box.prop(owner, path, text=name)
        elif control.startswith('particles:'):
            _draw_particles(box, entry, (control.split(':', 1)[1],))
        elif control == 'floaters':
            _draw_floaters(box, entry)
        elif control == 'resolution_buttons':
            if 'fluid' not in control_spec.controls(entry.mode, entry.show_advanced):
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
        elif control == 'lighting_details':
            import json
            from ..core import lighting
            sky = lighting.sky_node(entry)
            if sky:
                box.prop(sky, 'sky_type')
            changed = json.loads(entry.light_restore or '{}')
            box.label(text='Changed settings (restored on Delete):')
            for path in changed:
                box.label(text=path, icon='CHECKMARK')
            if not changed:
                box.label(text='Render settings were already suitable')
        elif control == 'fluid':
            _draw_fluid_settings(box, entry)
        elif control == 'whitewater':
            _draw_whitewater(box, entry)
        elif control == 'obstacles':
            _draw_obstacles(box, context)
        elif control == 'bake':
            _draw_bake(box, entry, 'aquasuite.bake_fluid', 'aquasuite.free_fluid')


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


def _draw_regimes(box, entry):
    row = box.row(align=True)
    for rid, label, _desc in C.REGIME_ITEMS:
        op = row.operator("aquasuite.hose_set_regime",
                          text=label.split()[0],
                          depress=(entry.regime == rid))
        op.uuid = entry.uuid
        op.regime = rid


def _draw_hose_liquid(box, entry, context):
    root = box
    box = root.column()
    box.enabled = not bakes.is_baking(entry)
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
    _draw_bake(root, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")


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


# Create buttons, grouped by what the user must do after clicking.
_REALTIME = (
    ("aquasuite.ocean_create", "Ocean", C.MODE_OCEAN),
    ("aquasuite.rain_create", "Rain", C.MODE_RAIN),
    ("aquasuite.rain_reactive_create", "Reactive Rain", C.MODE_RRAIN),
    ("aquasuite.snow_create", "Snow", C.MODE_SNOW),
    ("aquasuite.hose_create", "Water Hose", C.MODE_HOSE),
)
_LIQUID = (
    ("aquasuite.still_water_create", "Still Water", C.MODE_STILL),
    ("aquasuite.rain_sim_create", "Rain Sim", C.MODE_SIMRAIN),
    ("aquasuite.simulated_ocean_create", "Ocean (Simulated)", C.MODE_SIMOCEAN),
)


def _is_liquid(entry):
    return entry.mode in presets.LIQUID_MODES and (
        entry.mode != C.MODE_HOSE or entry.hose_liquid)


def _next_step(context, entry):
    """One plain-language hint for what to do next: (text, icon, alert)
    or None when there is nothing to say."""
    if entry.mode == C.MODE_LIGHTING or bakes.is_baking(entry):
        return None
    if _is_liquid(entry):
        if not bpy.data.is_saved:
            return "Save the file before baking", "ERROR", True
        if not bakes.has_bake(entry):
            return None     # the red Bake (required) button says it already
    elif entry.mode == C.MODE_RRAIN and not bakes.has_bake(entry):
        return "Bake Ripples before scrubbing", "INFO", False
    screen = context.screen
    if screen is not None and screen.is_animation_playing:
        return None
    return "Press Play (Space) to see it move", "PLAY", False


def _draw_entry_box(layout, context, entry):
    box = layout.box()
    header = box.row(align=True)
    header.prop(entry, "show_expanded", text="", emboss=False,
                icon="DISCLOSURE_TRI_DOWN" if entry.show_expanded
                else "DISCLOSURE_TRI_RIGHT")
    header.label(text=C.MODE_LABELS.get(entry.mode, entry.mode),
                 icon=C.MODE_ICONS.get(entry.mode, "QUESTION"))
    if beta.is_beta(entry.mode) or (entry.mode == C.MODE_HOSE
                                    and entry.hose_liquid):
        header.label(text="", icon="EXPERIMENTAL")     # Beta, as in Create
    op = header.operator("aquasuite.assembly_delete", text="", icon="TRASH")
    op.uuid = entry.uuid
    if not entry.show_expanded:
        return

    try:
        if entry.show_advanced and registry.is_pre_release(entry):
            _draw_pre_release(box, entry)
        hint = _next_step(context, entry)
        if hint is not None:
            text, icon, alert = hint
            row = box.row()
            row.alert = alert
            row.label(text=text, icon=icon)
        _draw_spec(box, context, entry)
    except Exception as exc:
        err = box.row()
        err.alert = True
        err.label(text="This setup can't be displayed", icon="ERROR")
        errors.record("AquaSuite couldn't draw a setup", exc,
                      mode=entry.mode, uuid=entry.uuid)
        errors.schedule()

    # The Simple/Advanced switch, in words, at the foot of the box.
    row = box.row()
    row.prop(entry, "show_advanced", emboss=False,
             text="Fewer Settings" if entry.show_advanced else "More Settings",
             icon="TRIA_UP" if entry.show_advanced else "TRIA_DOWN")


class AQS_OT_setups_expand(bpy.types.Operator):
    bl_idname = "aquasuite.setups_expand"
    bl_label = "Collapse or Expand All"
    bl_description = ("Collapse every setup box, or expand them all when "
                      "they are all collapsed")
    bl_options = {"INTERNAL"}

    def execute(self, context):
        entries = registry.entries(context.scene)
        expand = not any(e.show_expanded for e in entries)
        for e in entries:
            e.show_expanded = expand
        return {"FINISHED"}


class AQS_PT_water(bpy.types.Panel):
    bl_label = "AquaSuite"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Water"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(scene, "aqs_quality", expand=True)
        from ..core import lighting
        if lighting.suggested(scene):
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Water may look invisible", icon="INFO")
            col.label(text="without lighting.", icon="BLANK1")
            box.operator("aquasuite.water_lighting", icon="LIGHT_SUN")
        entries = registry.entries(scene)
        from ..core import memory
        low, high = (memory.scene_allowance(scene)
                     if control_spec.advanced_visible(entries) else (0, 0))
        if high:
            col = layout.column(align=True)
            col.label(text=f"Liquid total: {low:.2f}–{high:.2f} GB", icon="MEMORY")
            col.label(text="Planning allowance; excludes rendering", icon="BLANK1")


class AQS_PT_water_create(bpy.types.Panel):
    bl_label = "Create"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Water"
    bl_parent_id = "AQS_PT_water"

    def draw(self, context):
        layout = self.layout
        from ..core import lighting

        col = layout.column(align=True)
        col.label(text="Real-time · plays instantly", icon="PLAY")
        grid = col.grid_flow(row_major=True, columns=0, even_columns=True,
                             align=True)
        for op_id, text, mode in _REALTIME:
            grid.operator(op_id, text=text, icon=C.MODE_ICONS[mode])

        col = layout.column(align=True)
        col.label(text="Liquid · needs a bake · Beta", icon="EXPERIMENTAL")
        grid = col.grid_flow(row_major=True, columns=0, even_columns=True,
                             align=True)
        for op_id, text, mode in _LIQUID:
            grid.operator(op_id, text=text, icon=C.MODE_ICONS[mode])
        if not bpy.ops.aquasuite.still_water_create.poll():
            row = col.row()
            row.enabled = False
            row.label(text="Still Water: select a mesh first", icon="INFO")

        col = layout.column(align=True)
        col.label(text="Scene", icon="SCENE_DATA")
        row = col.row(align=True)
        sub = row.row(align=True)
        sub.enabled = lighting.existing(context.scene) is None
        sub.operator("aquasuite.water_lighting", text="Water Lighting",
                     icon="LIGHT_SUN")
        row.operator("aquasuite.load_demo", icon="FILE_BLEND")


class AQS_PT_water_setups(bpy.types.Panel):
    bl_label = "Your Setups"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Water"
    bl_parent_id = "AQS_PT_water"

    def draw_header_preset(self, context):
        entries = registry.entries(context.scene)
        row = self.layout.row(align=True)
        if len(entries):
            row.label(text=str(len(entries)))
        if len(entries) > 1:
            any_open = any(e.show_expanded for e in entries)
            row.operator("aquasuite.setups_expand", text="", emboss=False,
                         icon="FULLSCREEN_EXIT" if any_open else "FULLSCREEN_ENTER")

    def draw(self, context):
        layout = self.layout
        entries = registry.entries(context.scene)
        if not entries:
            col = layout.column(align=True)
            col.enabled = False
            col.label(text="Nothing here yet.", icon="INFO")
            col.label(text="Click a Create button above,", icon="BLANK1")
            col.label(text="or explore the demo scene:", icon="BLANK1")
            layout.operator("aquasuite.load_demo", icon="FILE_BLEND")
            return

        for entry in entries:
            _draw_entry_box(layout, context, entry)

        if control_spec.advanced_visible(entries) and any(
                _is_liquid(e) for e in entries):
            layout.operator("aquasuite.setup_render_layers", icon="RENDERLAYERS")


CLASSES = (AQS_OT_assembly_delete, AQS_OT_set_resolution,
           AQS_OT_set_resolution_custom, AQS_OT_setups_expand,
           AQS_PT_water, AQS_PT_water_create, AQS_PT_water_setups)
