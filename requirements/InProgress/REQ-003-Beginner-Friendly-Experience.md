# REQ-003 — Beginner-Friendly Experience

| Field | Value |
| ----- | ----- |
| ID | REQ-003 |
| Title | Beginner-Friendly Experience |
| Status | In progress — implementation preview; visual tuning and beginner sessions pending |
| Phase | Pre-launch |
| Tier | Release-blocking for the beginner market |
| Area | Water panel, Create operators, scene lighting/render setup, demo scene, preset tuning |
| Author | Blaxine |
| Created | 2026-10-18 |
| Last Updated | 2026-10-18 |

> Builds on REQ-001 (launch readiness) and REQ-002 (presets, whitewater, Ocean (Simulated)); takes over REQ-002's open tuning items S015, S027, Q5 and Q7.

## Implementation checkpoint — 2026-10-18

Slices 1–4 are implemented and checked headlessly. Slice 5 adds twelve preset
bake smoke checks (passed on Blender 5.1.2) and the late-quarter ocean gate;
S019–S021 and running/accepting S023 remain pending visual review. The user
confirmed no visual observations/renders yet. Slice 6 provides documentation
and the beginner-session protocol; S028 requires real participants and is pending.
UI smoke tests and EEVEE/Cycles visual acceptance remain manual gates.

## Short Description

Makes AquaSuite usable by Blender beginners without help. Every setup box opens in a **Simple** view — the preset (liquids), the two or three controls that change the look most, Water obstacles, and the Bake/Play action — with an **Advanced** toggle per box for everything else. **Create buttons are one click again** (the default preset; options stay in Blender's redo panel). A one-click, fully removable **Water Lighting** gives scenes a sky, sun and water-friendly render settings so clear water reads as water. **Load Demo** builds a real-time showcase in its own new scene. The presets are **tuned from an in-app visual review** and guarded by bake tests, and a session with beginners is the exit gate.

## Constraints

- **Headless Blender cannot draw panels.** What Simple and Advanced show must be defined as data the panel reads, so tests can check it.
- **Sky texture types differ:** Blender 4.1 offers `NISHITA`, `PREETHAM`, `HOSEK_WILKIE`; 5.1 offers `SINGLE_SCATTERING`, `MULTIPLE_SCATTERING`, `PREETHAM`, `HOSEK_WILKIE` (no `NISHITA`).
- **EEVEE refraction settings differ:** 4.1 — `scene.eevee.use_ssr`, `use_ssr_refraction`, material `use_screen_refraction`; 5.1 — `scene.eevee.use_raytracing`, material `use_raytrace_refraction` (the 4.1 scene settings are gone).
- **Cycles settings exist only when the Cycles add-on is enabled** (`scene.cycles`); a headless factory start lists only `BLENDER_EEVEE` as an engine.
- **Blender's redo panel shows an operator's options only with `REGISTER` + `UNDO`** — all Create operators already have both; four currently open a dialog first (`invoke_props_dialog`): Still Water, Rain Sim, Water Hose, Ocean (Simulated).
- **Switching the window to a new scene needs a window** (`context.window.scene`); headless runs have none usable.
- **Measured (REQ-002 review):** Calm stays within 0.07 m and Rolling Waves builds to ~0.4 m crest-to-trough at resolution 160; Storm Surf peaks ~1.2 m around frame 48 and falls to ~0.2 m by frame 96 while the paddle keeps moving.
- **The panel's top currently shows the Quality tier, a liquid memory allowance (two lines) and Set Up Render Layers** before the Create box.

## Architectural decisions

- **Simple/Advanced is per setup box**, stored on each assembly entry, default Simple; old setups open in Simple. UI state only — the data version stays 1.
- **A per-mode control specification** (data) lists the Simple controls and the Advanced controls; the panel draws from it, tests read it.
- **Simple per mode:** Plane Ocean — Amplitude, Wavelength, Speed, floaters row. Plane Rain / Snow — Count. Reactive Rain — Count, Bake Ripples. Still Water — Preset, resolution preset buttons, Water obstacles, Bake. Rain Simulation — Preset, Drop Amount, Speed, Angle, Pool meshes row, Water obstacles, Bake. Water Hose — regime buttons, Pressure, Spread, Water Color, Water obstacles. Ocean (Simulated) — Preset, Wave Height, Wave Period, Water obstacles, Bake. Everything else is Advanced.
- **Panel-level clutter moves behind Advanced:** the memory allowance and Set Up Render Layers show only while at least one box is in Advanced.
- **One-click Create:** no Create operator opens a dialog; each builds with its mode's default preset and keeps its options in the redo panel.
- **Water Lighting is an assembly** (a new mode, never a Beta mode): an AquaSuite-owned world with a sky texture and an owned sun light, plus render settings water needs; its restore record holds the previous world and every render setting it changed. Delete Assembly restores them exactly.
- **Water Lighting is suggested, never automatic:** a hint row appears when the scene has no lights and no world, or Blender's default grey world.
- **Load Demo** creates a new scene named "AquaSuite Demo" and builds only real-time modes plus Water Lighting and a camera; the user's scenes are not touched.
- **Preset tuning is review-driven:** values change only after the in-app review; each liquid preset is guarded by a bake test.

## UI / UX Notes

- **Panel top (Simple):** Quality, then the lighting hint when it applies ("Water may look invisible without lighting — Add Water Lighting"), then **Load Demo**, then the Create box.
- **Setup box header:** mode label, Beta tag when applicable, an **Advanced** toggle (icon button), Delete. Simple body per the specification above; Advanced shows today's full layout.
- **Create:** one click; a status-bar note "Change the look in the setup box" after liquid creates.
- **Water Lighting box:** Simple — Sun Strength, Sun Angle (time of day); Advanced — sky type, render-setting checklist (what was changed).
- **Demo:** "Load Demo" switches the window to "AquaSuite Demo"; the scene is deletable from Blender's scene selector.
- **Empty/edge states:** Still Water without an active mesh shows its existing hint; a scene that already has an AquaSuite Water Lighting shows no hint and disables a second Add.

## Acceptance Criteria

- [ ] **AC1 — Simple by default.** Every setup box opens in Simple showing exactly its specification's Simple controls; Advanced reveals the rest; the choice is per box and survives save/reload.
- [ ] **AC2 — One-click Create.** Every Create button builds immediately with the default preset; its options are available in the redo panel; no Create opens a dialog.
- [ ] **AC3 — Quiet panel top.** With all boxes in Simple, the memory allowance and Set Up Render Layers are hidden.
- [ ] **AC4 — Water Lighting.** One click adds a sky world, a sun and water-friendly render settings on 4.2+ and 5.x (EEVEE and, when enabled, Cycles); Delete restores the previous world and every changed setting exactly.
- [ ] **AC5 — Lighting hint.** The hint appears for a scene without lights and without a world or with the default grey world, and never once Water Lighting exists.
- [ ] **AC6 — Demo scene.** Load Demo builds "AquaSuite Demo" (ocean with a floater, rain, a hose hitting a Water Obstacles wall, Water Lighting, camera) that plays in real time with no bake; the user's scenes are unchanged.
- [ ] **AC7 — Presets tuned.** Every liquid preset bakes to real liquid in a low-res bake test; baked Ocean (Simulated) presets order Calm < Rolling Waves < Storm Surf, with Storm Surf's waves sustained to the end of the bake.
- [ ] **AC8 — Beginner gate.** Three to five Blender beginners each create a liquid and a real-time effect, adjust its look and render it without help; every blocker found is fixed or logged before launch.

## Technical Notes

- **Panel:** `ui/panel.py` — `AQS_PT_water.draw` (Quality, `memory.scene_allowance` readout, Create box, `aquasuite.setup_render_layers`, per-entry box with header and `_draw_entry`), per-mode drawers `_draw_ocean`, `_draw_particles`, `_draw_fluid_settings`, `_draw_bake`, `_draw_preset`, `_draw_whitewater`, `_draw_simulated_ocean`, `_draw_rain_sim`, `_draw_obstacles`, `_draw_hose`, `_draw_pre_release`.
- **Ocean inputs:** `level1/ocean.py` `INPUTS` (Size, Resolution, Amplitude, Wavelength, Choppiness, Direction, Spread, Speed), drawn through `_socket_identifier`.
- **Create dialogs to remove:** `level2/still_water.py` (invoke at ≈ line 162), `level2/rain_sim.py` (≈ 682), `level3/hose.py` (≈ 326, plus its `draw` for Simulate Liquid/Preset), `level2/simulated_ocean.py` (≈ 127). Default presets: `core/presets.DEFAULTS`.
- **Assembly machinery:** `core/registry.py` `AQS_AssemblyEntry` and `registry.add`; `core/naming.py` (`tag`, `new_assembly_collection`); `core/delete.py` (`delete_assembly`, `guarded_create`, `_TAGGED_COLLECTIONS` — `worlds` and `lights` are not swept today); modes in `constants.py` `MODE_*`, `MODE_LABELS`, `MODE_ICONS`; Beta modes `ui/beta.py`.
- **Materials:** `materials/mats.py` sets `use_screen_refraction` (4.1-era); 5.1 also needs `use_raytrace_refraction`.
- **Tests:** `tests/run_tests.py`, `tests/aqs_testlib.py`; existing `tests/test_presets.py`, `tests/test_whitewater.py`, `tests/test_simulated_ocean.py`, `tests/test_create_delete.py`, `tests/test_hose.py` call Create operators with keyword options (still valid without dialogs).

## Implementation Steps

| Phase | Meaning |
| ----- | ------- |
| F | Foundation |
| P | Persistence (saved .blend data) |
| S | Service (add-on logic) |
| U | UX (panel) |
| D | Docs |
| T | Tests |
| X | Cross-plan / review |

### Slice 1 — Tracer: Ocean (Simulated) in Simple, one-click

**Demoable when:** clicking "Ocean (Simulated)" builds a Rolling Waves tank at once; its box shows only Preset, Wave Height, Wave Period, Water obstacles and Bake; the Advanced toggle reveals the rest and is remembered after save/reload.
**Satisfies:** AC1 (one mode), AC2 (one mode)

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✓ | S001 | F | Control specification | Data listing Simple and Advanced controls per mode; first entry Ocean (Simulated). | — | `ui/` |
| ✓ | S002 | P | Per-box Advanced flag | Entry setting, default off; drawn as a header toggle. | — | `core/registry.py` |
| ✓ | S003 | U | Ocean (Simulated) box from the spec | Simple/Advanced drawing for this mode driven by the specification. | S001, S002 | `ui/panel.py` |
| ✓ | S004 | S | One-click ocean Create | Remove the dialog; default preset; options in the redo panel. | — | `level2/simulated_ocean.py` |
| ✓ | S005 | T | Tracer tests (new) | Spec entries name real settings; Simple ⊂ all controls; ocean Create executes without a dialog. | S003, S004 | new `tests/test_simple_view.py` |

### Slice 2 — Simple everywhere, one-click everywhere

**Demoable when:** every mode's box opens Simple, and Still Water, Rain Sim and Water Hose create in one click; the panel top hides the memory readout and Set Up Render Layers while all boxes are Simple.
**Satisfies:** AC1, AC2, AC3

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✓ | S006 | U | Spec + drawing for all modes | Plane Ocean, Rain, Snow, Reactive Rain, Still Water, Rain Simulation, Water Hose per the Architectural decisions. | S003 | `ui/panel.py`, spec module |
| ✓ | S007 | S | One-click Create (three modes) | Remove dialogs from Still Water, Rain Sim and Water Hose; defaults from `presets.DEFAULTS`; status note after liquid creates. | S004 | `level2/still_water.py`, `level2/rain_sim.py`, `level3/hose.py` |
| ✓ | S008 | U | Quiet panel top | Memory allowance and Set Up Render Layers only while any box is Advanced. | S006 | `ui/panel.py` |
| ✓ | S009 | T | Simple-view tests (extend) | Spec covers every mode; Create operators have no dialog; existing Create-with-options tests still pass. | S006, S007 | `tests/test_simple_view.py` |

### Slice 3 — Water Lighting

**Demoable when:** in a fresh scene the hint appears; Add Water Lighting gives a sky, a sun and refraction-ready render settings; Delete restores the original world and settings.
**Satisfies:** AC4, AC5

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✓ | S010 | F | Water Lighting mode | Mode constant/label/icon (not Beta); one per scene. | — | `constants.py` |
| ✓ | S011 | S | Build + restore record | Owned world with a version-appropriate sky type and an owned sun; render settings per version (EEVEE refraction/ray tracing; Cycles bounces when available); previous world and changed settings recorded. | S010 | new module, `core/registry.py` |
| ✓ | S012 | S | Delete restores | Delete Assembly restores the world and settings; worlds and lights join the tagged sweep. | S011 | `core/delete.py` |
| ✓ | S013 | U | Hint + box | Hint row with Add button; Water Lighting box (Sun Strength, Sun Angle; Advanced: sky type, changed settings). | S011 | `ui/panel.py` |
| ✓ | S014 | S | Material refraction on 5.x | Water materials also set the 5.x refraction flag. | — | `materials/mats.py` |
| ✓ | S015 | T | Lighting tests (new) | Add/remove round-trip restores world and every recorded setting on 4.1 and 5.1; hint logic; one per scene. | S012, S013 | new test file |

### Slice 4 — Demo scene

**Demoable when:** Load Demo switches to "AquaSuite Demo", which plays immediately: an ocean with a floating box, rain, and a hose hitting a wall, lit and framed.
**Satisfies:** AC6

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✓ | S016 | S | Load Demo | New scene; Plane Ocean + floater, Plane Rain, Water Hose aimed at a wall added to Water Obstacles, Water Lighting, camera; window switch when a window exists. | S011 | new module |
| ✓ | S017 | U | Button | "Load Demo" at the panel top. | S016 | `ui/panel.py` |
| ✓ | S018 | T | Demo tests (new) | Demo scene contents; user scene object/world/settings unchanged; demo plays (particles alive, floater moves) with no bake. | S016 | new test file |

### Slice 5 — Preset tuning (from REQ-002)

**Demoable when:** every liquid preset bakes cleanly and looks right in the review renders; Storm Surf keeps breaking waves to the end of the bake.
**Satisfies:** AC7

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S019 | X | In-app visual review | Render each of the twelve presets with Water Lighting (Cycles and EEVEE) in Blender 5.1; record what to change (REQ-002 Q5). | S013 | `docs/PRESET_REVIEW.md` |
|  | S020 | S | Storm Surf fix | Find why Storm Surf's waves fade (breaking vs lost paddle forcing — REQ-002 Q7) and fix the preset or paddle. | S019 | `core/presets.py`, `level2/simulated_ocean.py` |
|  | S021 | S | Apply tuned values | Update preset packages from the review. | S019 | `core/presets.py` |
| ✓ | S022 | T | Per-preset bake tests (new; REQ-002 S015) | `--bake`: each liquid preset produces liquid at low resolution. | S021 | `tests/test_presets.py` |
|  | S023 | T | Ocean ordering (extend; REQ-002 S027) | `--bake`: Calm < Rolling Waves < Storm Surf, Storm sustained in the last quarter of the bake. | S020 | `tests/test_simulated_ocean.py` |

### Slice 6 — Docs, hand-over, beginner gate

**Demoable when:** the README's quick start matches the Simple panel, REQ-002 records the hand-over, and the release checklist holds the beginner-session gate.
**Satisfies:** AC8

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✓ | S024 | D | User docs | README quick start (one-click Create, Simple/Advanced, Water Lighting, Load Demo); troubleshooting ("water is invisible"). | S017 | `README.md`, `docs/TROUBLESHOOTING.md` |
| ✓ | S025 | D | Thesaurus terms | Add: Simple view, Advanced view, Control specification, Water Lighting, Demo scene. | S024 | `docs/THESAURUS.md` |
| ✓ | S026 | X | REQ-002 hand-over | Record in REQ-002 that S015, S027, Q5, Q7 moved to REQ-003. | — | `requirements/InProgress/REQ-002-One-Click-Mantaflow-Presets.md` |
| ✓ | S027 | D | Beginner gate in checklist | Release checklist section: 3–5 beginners, tasks (create a liquid + a real-time effect, change the look, render), observations, fixes. | S024 | `docs/RELEASE_CHECKLIST.md` |
|  | S028 | X | Run the beginner sessions | Hold the sessions; fix or log every blocker. | S027, S022, S023 | `docs/RELEASE_CHECKLIST.md` |

### Dependency graph

```
S001 ─┐
S002 ─┴─ S003 ─┬─ S005 (+S004)
S004 ──────────┤
               └─ S006 ─┬─ S008
S007 (+S004) ───────────┴─ S009
S010 → S011 ─┬─ S012 ─┐
             ├─ S013 ─┴─ S015
             │     └─ S019 ─┬─ S020 → S023
             │              └─ S021 → S022
             └─ S016 → S017 → S024 → S025
                  └─ S018          └─ S027 → S028 (+S022, S023)
S014
S026
```

## Dependencies

| REQ ID | Title | Reason |
| ------ | ----- | ------ |
| REQ-001 | 1.0 Launch Readiness | Assembly/delete/restore machinery, error pipeline, test runner, release checklist. |
| REQ-002 | One-Click Mantaflow Presets | Presets, whitewater and Ocean (Simulated) that the Simple view and tuning build on; its open items S015, S027, Q5, Q7 move here. |

## Out of Scope

- Tutorial video, store page and screenshots (launch plan).
- New presets beyond the existing twelve.
- HDRI image environments (a bundled image file).
- Changing which modes are Beta.
- Automated tests of panel drawing or window behaviour.

## Open Questions

- [x] **Q1 — Switch location.** Per setup box, default Simple. *(Blaxine)*
- [x] **Q2 — Preset choice at Create.** Default preset; change it in the box; redo panel for options. *(Blaxine)*
- [x] **Q3 — Lighting.** One-click, removable Water Lighting, suggested by a hint, never automatic. *(Blaxine)*
- [ ] **Q4 — Sky in EEVEE.** Does the chosen sky type render in EEVEE on 4.2 and 5.x, or does EEVEE need a different sky? Deferred until Slice 3's first renders in both engines.
- [ ] **Q5 — Tuned values.** Exact preset values. Deferred until the Slice 5 visual review (S019).
- [ ] **Q6 — Beginner recruits.** Who the three to five beginners are and how sessions are run (in person / screen share). Deferred until Slices 1–5 are done.

## Smoke Test

> Developer runs the app; the agent does not self-run.

1. New file. The Water tab shows Quality, the lighting hint, Load Demo and Create — no memory lines, no render-layers button.
2. Add Water Lighting: the viewport (Material Preview / Rendered) shows a sky and sun. Delete it: the original grey world and settings return.
3. Click Ocean (Simulated): a tank appears immediately; the box shows Preset, Wave Height, Wave Period, Water obstacles, Bake. Toggle Advanced: everything else appears. Save, reopen: still Advanced.
4. Click Still Water (with a cube active), Rain Sim, Water Hose: each creates at once; the redo panel (bottom-left) shows their options.
5. Load Demo: "AquaSuite Demo" opens; press Play — the box floats, rain falls, the hose hits the wall. Your original scene is unchanged.
6. Bake Storm Surf: waves keep breaking until the last frame.

## Size

| T-Shirt Size | Estimated Hours | Notes |
| ------------ | --------------- | ----- |
| L | 40–55 | Slices 1–4 are mostly panel and operator work (~25 h); tuning (Slice 5) depends on the review and bake time; the beginner sessions are calendar time, not code. |

## Considered And Rejected

Nothing here is built. Each entry names the alternative, then why it lost.

- **One Simple/Advanced switch for the whole panel.** Power users get every box expanded at once; per-box keeps the rest of the panel quiet.
- **Simple/Advanced as an add-on preference.** Beginners rarely open Preferences.
- **Simple = preset + action only.** Even small tweaks (rain angle, wave height) would need Advanced.
- **Whitewater checkboxes in Simple.** Makes liquid boxes long for a detail most first results don't need.
- **Create buttons with a ▾ preset menu.** More buttons in the Create box; the preset dropdown already sits at the top of each box.
- **Redo panel as the only way to choose.** Many beginners never notice it.
- **Automatic lighting on first Create.** Silently changes the user's scene.
- **Better materials only.** Clear water in a grey world still reads as nothing.
- **Demo as a shipped .blend.** Adds megabytes to the zip and must be rebuilt every version.
- **Demo in the current scene.** Mixes the showcase with the user's work.
- **Keeping REQ-002's tuning items in REQ-002.** Splits tuning from the review that judges it and keeps two plans open.

## Revision History

| Date | Author | Summary of Change |
| ---- | ------ | ----------------- |
| 2026-10-18 | Blaxine | Initial plan. |
