# SPDX-License-Identifier: GPL-3.0-or-later
"""N-panel "Water" tab (TDD §9)."""

import bpy

from .. import constants as C
from ..core import registry, delete
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


def _draw_particles(box, entry, label="Particles"):
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
    colm.prop(ps, "count", text="Count")
    colm.prop(ps, "lifetime", text="Lifetime")
    colm.prop(ps, "particle_size", text="Size")


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


def _draw_fluid_settings(box, entry):
    """Resolution controllers + live cost readout + bake range."""
    from ..level2.still_water import find_domain_object
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
    longest = max(dom.dimensions) if dom else 0.0
    if eff > 0 and longest > 0.0:
        dx_cm = longest / eff * 100.0
        cost = (eff / 96.0) ** 3
        note = f"Effective {eff} · voxel {dx_cm:.1f} cm · ~{cost:.1f}× cost"
        if entry.mode in ("HOSE", "SIMRAIN") and entry.draft:
            note += "  (Draft ½)"
        sub = box.row()
        sub.enabled = False
        sub.label(text=note, icon="SORTTIME" if cost > 3 else "TIME")
        # Absolute memory estimate — the crash-prevention readout.
        from ..level2.rain_sim import memory_estimate
        mcells, gb = memory_estimate(dom, eff)
        sub = box.row()
        sub.alert = gb > 2.0
        sub.label(text=f"≈ {mcells:.1f} M cells · est. {gb:.1f} GB RAM",
                  icon="ERROR" if gb > 2.0 else "MEMORY")

    row = colm.row(align=True)
    row.prop(ds, "cache_frame_start", text="Bake Start")
    row.prop(ds, "cache_frame_end", text="End")


def _draw_bake(box, entry, op_bake, op_free=None, mandatory=True):
    row = box.row(align=True)
    row.alert = mandatory
    op = row.operator(op_bake, icon="RENDER_ANIMATION",
                      text="Bake (required)" if mandatory else "Bake")
    op.uuid = entry.uuid
    if op_free:
        op = row.operator(op_free, text="", icon="TRASH")
        op.uuid = entry.uuid


def _draw_rain_sim(box, entry):
    colm = box.column(align=True)
    colm.prop(entry, "rain_speed")
    colm.prop(entry, "rain_angle")
    colm.prop(entry, "rain_direction")
    colm.prop(entry, "rain_area")

    from ..level2.rain_sim import (find_emitter, _drops_modifier)
    from ..level1.ocean import _socket_identifier
    gnmod = _drops_modifier(find_emitter(entry), entry.uuid)
    if gnmod is not None:
        drops = box.column(align=True)
        drops.label(text="Drops", icon="MOD_FLUIDSIM")
        for sock_name, label in (("Density", "Drop Amount"),
                                 ("Drop Size", "Drop Size"),
                                 ("Seed", "Seed")):
            ident = _socket_identifier(gnmod, sock_name)
            if ident:
                drops.prop(gnmod, f'["{ident}"]', text=label)

    if gnmod is None:
        sub = box.row()
        sub.alert = True
        op = sub.operator("aquasuite.rain_sim_rebuild_emitter",
                          text="Emitter missing — Rebuild", icon="ERROR")
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

    row = box.row(align=True)
    row.prop(entry, "draft", toggle=True)
    op = row.operator("aquasuite.rain_sim_fit_domain", text="Fit Domain",
                      icon="SHADING_BBOX")
    op.uuid = entry.uuid
    _draw_fluid_settings(box, entry)
    _draw_bake(box, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")


def _draw_hose(box, entry):
    colm = box.column(align=True)
    colm.prop(entry, "pressure")
    colm.prop(entry, "hose_range")
    colm.prop(entry, "spread")
    colm.prop(entry, "nozzle_radius")
    row = box.row(align=True)
    for rid, label, _desc in C.REGIME_ITEMS:
        op = row.operator("aquasuite.hose_set_regime",
                          text=label.split()[0],
                          depress=(entry.regime == rid))
        op.uuid = entry.uuid
        op.regime = rid
    if entry.regime != C.REGIME_MIST:
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
        _draw_bake(box, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")


class AQS_PT_water(bpy.types.Panel):
    bl_label = "Water"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Water"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "aqs_quality", text="Quality")

        create = layout.box()
        create.label(text="Create", icon="ADD")
        row = create.row(align=True)
        row.operator("aquasuite.ocean_create", text="Ocean", icon=C.MODE_ICONS[C.MODE_OCEAN])
        row.operator("aquasuite.rain_create", text="Rain", icon=C.MODE_ICONS[C.MODE_RAIN])
        row = create.row(align=True)
        row.operator("aquasuite.rain_reactive_create", text="Reactive Rain")
        row.operator("aquasuite.snow_create", text="Snow")
        row = create.row(align=True)
        row.operator("aquasuite.still_water_create", text="Still Water (active mesh)")
        row = create.row(align=True)
        row.operator("aquasuite.hose_create", text="Water Hose")
        row.operator("aquasuite.rain_sim_create", text="Rain Sim",
                     icon=C.MODE_ICONS[C.MODE_SIMRAIN])

        entries = registry.entries(scene)
        if not entries:
            return
        layout.separator()
        layout.label(text="Assemblies", icon="OUTLINER_COLLECTION")

        for entry in entries:
            box = layout.box()
            header = box.row(align=True)
            header.label(text=C.MODE_LABELS.get(entry.mode, entry.mode),
                         icon=C.MODE_ICONS.get(entry.mode, "QUESTION"))
            header.label(text=f"AQS_A_{entry.uuid[:8]}")
            op = header.operator("aquasuite.assembly_delete", text="", icon="TRASH")
            op.uuid = entry.uuid

            try:
                self._draw_entry(box, context, entry)
            except Exception as exc:
                err = box.row()
                err.alert = True
                err.label(text=f"Panel error: {exc}", icon="ERROR")
                import traceback
                traceback.print_exc()

    def _draw_entry(self, box, context, entry):
        if entry.mode == C.MODE_OCEAN:
            _draw_ocean(box, context, entry)
        elif entry.mode in (C.MODE_RAIN, C.MODE_SNOW):
            _draw_particles(box, entry)
        elif entry.mode == C.MODE_RRAIN:
            _draw_particles(box, entry)
            _draw_bake(box, entry, "aquasuite.bake_ripples", mandatory=False)
        elif entry.mode == C.MODE_STILL:
            _draw_fluid_settings(box, entry)
            _draw_bake(box, entry, "aquasuite.bake_fluid", "aquasuite.free_fluid")
        elif entry.mode == C.MODE_HOSE:
            _draw_hose(box, entry)
        elif entry.mode == C.MODE_SIMRAIN:
            _draw_rain_sim(box, entry)


CLASSES = (AQS_OT_assembly_delete, AQS_OT_set_resolution,
           AQS_OT_set_resolution_custom, AQS_PT_water)
