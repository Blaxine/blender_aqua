# REQ-002 — One-Click Mantaflow Presets

| Field | Value |
| ----- | ----- |
| ID | REQ-002 |
| Title | One-Click Mantaflow Presets |
| Status | InProgress |
| Phase | Post-1.0 feature (can land before launch) |
| Tier | Major feature |
| Area | Liquid modes (Still Water, Rain Sim, hose Simulate Liquid), new Ocean (Simulated) mode, panel, render setup |
| Author | Blaxine |
| Created | 2026-10-17 |
| Last Updated | 2026-10-18 |

> Builds on REQ-001 (setup stamp, error pipeline, Water Obstacles, bake buttons, test runner).

## Short Description

### Implementation checkpoint — 2026-10-17

The 0.17.0 preview implements the twelve preset packages, saved snapshots and
modified marker, shared whitewater controls/render instances, Material
Cryptomatte and four AOVs, and the Beta wave tank with an animated paddle.
User documentation and `docs/PRESET_REVIEW.md` describe the manual checks.

Per the user's instruction, automated functional checks, bake/render checks,
and acceptance sign-off are deferred until after their manual review. The
acceptance boxes below remain open. Preset values and tank dimensions are
provisional pending visual tuning. Implementation uses shared Mantaflow spawn
thresholds plus per-element shader thinning for independent rendered Amount.
Renamed systems are tracked by ownership/element tags after adoption; an
unidentified renamed legacy system produces a warning instead of guessed ownership.

Makes AquaSuite's Mantaflow liquids one-click and art-directable for users who don't want to learn the fluid solver. Every liquid setup gets **presets** (three looks per mode) that write a tuned package of solver settings, **whitewater** controls (Spray, Foam, Bubbles: on/off, Amount, Size) whose particles actually render, and a one-click **render layers** setup that lets the compositor pull liquid and each whitewater element out of a single render. A new Beta mode, **Ocean (Simulated)**, is a wave tank: a box of water with an animated wave paddle sending waves into the scene's Water Obstacles, with its own three presets.

## Constraints

- **Mantaflow's whitewater particles don't render by default.** Enabling spray/foam/bubbles creates particle systems named `Spray`, `Foam`, `Bubbles` on the domain with `render_type = "HALO"` and no instance object; Cycles and EEVEE draw nothing (measured on 4.1 and 5.1).
- **Switching an element off deletes its particle system; switching it on creates a new one with fresh `ParticleSettings`** (HALO, no instance). Render setup must be re-applied after every enable; the old settings datablock is left orphaned and untagged.
- **The particle systems carry no API field identifying their element type**; the names `Spray`/`Foam`/`Bubbles` given by Mantaflow are the only handle.
- **`use_spray/foam/bubble_particles` toggle on every write** — always go through `still_water.set_flag`.
- **Whitewater cost (measured, 1 m cube, res 64, 24 frames, 5.1):** bake 5.5 s → 7.3 s, cache 39 MB → 70 MB with all three on; splashy scenes reach 2–4×.
- **Particles render only if the instancer renders** (the hose bug fixed in REQ-001): the domain must stay renderable for whitewater to show.
- **All solver settings this plan touches exist on 4.1 and 5.1:** `use_viscosity`, `viscosity_value/base/exponent`, `use_flip_particles`, `flip_ratio`, `particle_radius`, `particle_randomness`, `surface_tension`, `use_diffusion`, `use_collision_border_*`, effector `effector_type/use_effector/subframes/use_plane_init/surface_distance`, the `sndparticle_*` set, view-layer `use_pass_cryptomatte_*`, `ViewLayer.aovs`, `ShaderNodeOutputAOV`.
- **Mantaflow removes a whitewater particle system without lowering its settings' user count** (it stays 1): orphan detection must check whether any particle system still references the settings.
- **Ocean waves need cells of about 12 cm or less** (measured, 20 × 8 × 4 m tank): at Draft resolution 48 (42 cm cells) Calm and Rolling Waves read only as settling slosh; at resolution 160 Calm stays within 0.07 m and Rolling builds to ~0.4 m. A 160 tank is ~0.33 M cells.
- **Blender 4.1 crashes on exit after Mantaflow bakes** (access violation in `python311.dll`, also with v0.16.1), after every check has reported.
- **Draft forces secondary particles off today** (hose `apply_regime`, Rain Sim `apply_quality`); hose regimes Spray and Normal/Blast also write secondaries from `C.REGIME_PARAMS`.
- **Compatibility promise (REQ-001):** from 1.0 no update changes a saved setup; new settings must default to today's behaviour on old setups.

## Architectural decisions

- **Presets are editable starting points.** Applying one writes its values once; the setup stores the values and the id of the last-applied preset plus a "modified" flag (set when a preset-owned value is edited). Saved scenes never reference live preset definitions; changing a preset definition in a later version affects only new applications.
- **Preset catalogue:** Still Water — Calm Pour, Splashy, Thick; Rain Sim — Drizzle, Rain, Storm; hose Simulate Liquid — Garden, Fire Hose, Sprinkler; Ocean (Simulated) — Calm, Rolling Waves, Storm Surf. Each is a plain data package (solver, whitewater, mode-specific values) defined in one module.
- **Presets are offered at Create** (operator property, also shown in the redo panel) **and afterwards** from a panel dropdown + Apply.
- **Whitewater per element:** on/off, Amount (0–1, mapped to spawn thresholds and sampling), Size (render size in metres). Other `sndparticle_*` settings are derived. Draft suspends whitewater without changing the checkboxes.
- **Whitewater rendering:** each enabled element gets an AquaSuite-owned instance object and material (tagged to the assembly, removed by Delete Assembly); setup is re-applied whenever an element is enabled.
- **Hose regimes seed whitewater** the way they seed resolution: choosing a regime writes its whitewater defaults; the checkboxes own them afterwards.
- **Render layers = Cryptomatte + AOVs.** Liquid, Spray, Foam and Bubbles each use their own material; a one-click action turns on Material Cryptomatte and adds one AOV per element on the active view layer. No extra objects or view layers.
- **Ocean (Simulated)** is a new Beta mode in Level 2: a liquid domain tank, an AquaSuite-owned water block filling it (one-shot geometry flow), and an AquaSuite-owned paddle effector at one end animated by a sine F-Curve modifier (amplitude ↔ wave height, period ↔ wave period). Tank walls collide; Water Obstacles inside the tank are hit by the waves. It uses the same presets, whitewater, render-layer, bake and delete machinery as the other liquid modes.
- **Data version stays 1.** New settings default to today's behaviour (no preset applied, whitewater as currently set on the domain).

## UI / UX Notes

- **Liquid setup box (Still Water, Rain Sim, hose with Simulate Liquid, Ocean (Simulated)):** a Preset row — dropdown + Apply, showing the last-applied preset or "Custom", with "(modified)" when edited. Below it a **Whitewater** section: three rows (Spray, Foam, Bubbles), each a checkbox plus Amount and Size sliders, greyed while unchecked; a note "Off while Draft is on" when Draft suspends them.
- **Render layers:** a scene-level "Set Up Render Layers" button (in the Water panel, shown once any liquid setup exists) that enables Cryptomatte Material and the four AOVs on the active view layer and reports what it turned on; idempotent.
- **Create:** each liquid Create button opens with the default preset (Calm Pour / Rain / Garden / Rolling Waves); the operator's Preset property is changeable in the redo panel.
- **Ocean (Simulated):** Create button "Ocean (Simulated) · Beta" in the Create box; its box shows Preset, Wave Height, Wave Period, Tank Size, Draft/Resolution, Whitewater, Water obstacles row, Bake.
- **Empty/edge states:** applying a preset to a baked setup leaves the bake in place and shows the existing "Bake Again" state; whitewater sliders do nothing visible until re-bake (tooltip says so).

## Acceptance Criteria

- [ ] **AC1 — Preset applies.** Choosing a preset at Create or from the dropdown writes its full package; the box shows its name; editing any preset-owned value marks it "(modified)".
- [ ] **AC2 — Twelve presets.** All twelve presets exist, apply without errors, and bake to visibly different results (a low-res bake test per preset produces liquid).
- [ ] **AC3 — Whitewater controls.** Spray, Foam and Bubbles each switch on/off independently with Amount and Size in Still Water, Rain Sim, hose Simulate Liquid and Ocean (Simulated); Draft suspends them without losing the checkbox state.
- [ ] **AC4 — Whitewater renders.** After a bake with an element on, its particles appear in Cycles and EEVEE renders, also after switching the element off and on again.
- [ ] **AC5 — Faster renders/bakes.** With every element off, no whitewater particle systems exist on the domain and the bake writes no secondary-particle cache.
- [ ] **AC6 — Render layers.** One click enables Material Cryptomatte and an AOV per element; Liquid, Spray, Foam and Bubbles each appear as a separable matte in the compositor.
- [ ] **AC7 — Ocean (Simulated).** One click creates a wave tank whose bake shows waves travelling from the paddle and hitting Water Obstacles; Delete restores the scene.
- [ ] **AC8 — Ocean presets.** Calm, Rolling Waves and Storm Surf produce visibly different wave height and period; Storm Surf has whitewater on.
- [ ] **AC9 — Old setups untouched.** Opening a scene saved before this change shows every liquid setup exactly as before, with Preset "Custom" and whitewater checkboxes matching the domain.

## Technical Notes

- **Shared liquid setup:** `level2/still_water.py` — `RES_PRESETS` (line 19), `set_flag` / `SECONDARY_FLAGS` (≈ line 30), `setup_domain_settings(dom_mod, uid, resolution, cfl, ts_min, ts_max, secondaries)` (line 109) is called by Still Water, Rain Sim (`level2/rain_sim.py` `_build`) and the hose (`level3/hose.py` `AQS_OT_hose_create`). `find_domain_object(entry)` (line 224) locates the domain for any mode.
- **Where secondaries are written today:** `level3/hose.py` `apply_regime` (liquid path: `for flag in sw.SECONDARY_FLAGS: sw.set_flag(ds, flag, secondaries)` with `secondaries = p["secondaries"] and not entry.draft`); `level2/rain_sim.py` `apply_quality` (Draft halving). `C.REGIME_PARAMS` in `constants.py` carries per-regime `secondaries`.
- **Registry:** `core/registry.py` `AQS_AssemblyEntry` holds per-mode settings with `update=` callbacks wrapped by `errors.guard_update`; `registry.add()` stamps `data_version` / `addon_version`.
- **Modes:** `constants.py` `MODE_*`, `MODE_LABELS`, `MODE_ICONS`; Beta modes in `ui/beta.py` `BETA_MODES` / `_FLAG` (preferences flags per Beta mode).
- **Panel:** `ui/panel.py` — `_draw_fluid_settings(box, entry)` (resolution presets, RAM readout, bake range), `_draw_bake`, `_draw_obstacles(box, context)`, per-mode `_draw_*` dispatched from `AQS_PT_water._draw_entry`.
- **Create guard:** `core/delete.guarded_create` (cleanup on failure, Beta note via `ui/beta.notify_created`); Delete sweeps tagged IDs in `objects, meshes, particles, node_groups, materials, collections` (`core/delete.py` `_TAGGED_COLLECTIONS` / `delete_assembly`).
- **Bake state:** `core/bakes.py` (`has_bake`, `is_baking`, Cancel Bake); bake operator `aquasuite.bake_fluid` in `level2/still_water.py`.
- **Obstacles:** `core/obstacles.sync(scene)` before every bake; effectors apply to every domain in the scene.
- **Materials:** `materials/mats.py` (`water_surface`, `droplet`, `mist`, `_new_mat` tags per assembly).
- **Tests:** `tests/run_tests.py`, `tests/aqs_testlib.py`; affected files `tests/test_liquids.py` (Spray regime secondaries / Draft check), `tests/test_bakes.py` (`--bake` liquid bakes), `tests/test_beta.py` (Beta modes), `tests/test_create_delete.py` (create/delete every mode), `tests/test_package.py` (zip contents).
- **Whitewater systems on a domain** are found by Mantaflow's names `Spray` / `Foam` / `Bubbles` in `dom.particle_systems`; the always-present `Liquid` system (FLIP) is left alone.
- **Paddle animation:** an F-Curve on the paddle's location with a sine `FModifierGenerator`/`FModifierFunctionGenerator`; the effector needs `use_effector = True` and enough `subframes` for its speed.

## Implementation Steps

| Phase | Meaning |
| ----- | ------- |
| F | Foundation |
| P | Persistence (saved .blend data) |
| S | Service (add-on logic) |
| U | UX (panel, dialogs) |
| D | Docs |
| T | Tests |

### Slice 1 — Tracer: Still Water "Splashy", foam that renders

**Demoable when:** Create → Still Water with preset Splashy, bake, F12 — foam particles appear in the render; the box shows "Splashy".
**Satisfies:** AC1 (one preset), AC4 (foam)

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S001 | F | Preset catalogue (one entry) | A module holding preset packages as data; first entry Still Water "Splashy" (resolution, solver values, foam on with Amount/Size). | — | new preset module under `level2/` or `core/` |
| ✅ | S002 | P | Preset + whitewater settings | Entry settings: last-applied preset id, modified flag, per-element on/Amount/Size; defaults = no preset, whitewater read from the domain. | S001 | `core/registry.py` |
| ✅ | S003 | S | Apply preset | Applies a package to a setup's domain (through `set_flag`), records the preset id, clears "modified". | S002 | `level2/still_water.py` |
| ✅ | S004 | S | Whitewater render setup | For each enabled element: tagged instance object + material, `render_type = "OBJECT"`, size from Size; re-applied after every enable; orphaned settings datablocks removed. | S003 | `level2/still_water.py`, `materials/mats.py` |
| ✅ | S005 | U | Preset at Create + in the box | Still Water Create gets a Preset property (default Calm Pour placeholder until Slice 3; Splashy selectable); the box shows Preset dropdown + Apply and the current name. | S003 | `level2/still_water.py`, `ui/panel.py` |
| ✅ | S006 | T | Tracer tests (new) | Splashy applies (values, preset id); after a `--bake` the Foam system exists, is `OBJECT` with an instance, and has alive particles. | S004, S005 | new `tests/test_presets.py` |

### Slice 2 — Whitewater controls everywhere

**Demoable when:** in Still Water, Rain Sim and the hose's Simulate Liquid, toggling Spray/Foam/Bubbles and moving Amount/Size changes the next bake; Draft greys them out.
**Satisfies:** AC3, AC4, AC5, AC9

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S007 | S | Whitewater apply | One routine writes on/off + derived `sndparticle_*` from Amount, and render setup from Size, for any liquid setup; Draft suspends (checkboxes kept). | S004 | `level2/still_water.py` |
| ✅ | S008 | S | Hook all liquid modes | Rain Sim `apply_quality` and hose `apply_regime` stop writing secondaries directly and call the whitewater routine; hose regimes seed whitewater defaults. | S007 | `level2/rain_sim.py`, `level3/hose.py`, `constants.py` |
| ✅ | S009 | U | Whitewater section | Three rows (checkbox, Amount, Size) in each liquid box; greyed when off; "Off while Draft is on" note. | S007 | `ui/panel.py` |
| ✅ | S010 | P | Old setups | Whitewater settings initialise from the domain's current flags for setups made before this change; preset shows "Custom". | S002 | `core/registry.py`, `level2/still_water.py` |
| ✅ | S011 | T | Whitewater tests (new/extend) | Independent toggles per mode; off → no Spray/Foam/Bubbles systems; Draft suspends and restores; off/on keeps render setup; extend the Spray-regime check in `tests/test_liquids.py` (regime seeds, checkboxes own afterwards). | S008, S010 | `tests/test_presets.py`, `tests/test_liquids.py` |

### Slice 3 — The other eight liquid presets

**Demoable when:** every liquid mode offers its three presets at Create and in the box, each bakes to a distinct look, and edits show "(modified)".
**Satisfies:** AC1, AC2

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S012 | S | Liquid presets | Still Water Calm Pour, Thick (viscosity on); Rain Sim Drizzle, Rain, Storm (density, speed, splash amount, whitewater); hose Garden, Fire Hose, Sprinkler (regime, pressure, spread, whitewater). | S008 | preset module |
| ✅ | S013 | U | Preset at Create for every liquid mode | Create operators of Rain Sim and the hose (Simulate Liquid) gain the Preset property; defaults Rain / Garden; Still Water default Calm Pour. | S012 | `level2/rain_sim.py`, `level3/hose.py`, `level2/still_water.py` |
| ✅ | S014 | S | "Modified" marker | Editing a preset-owned setting sets the flag; Apply clears it. | S012 | `core/registry.py` |
|  | S015 | T | Preset tests (new) | Each preset applies cleanly; `--bake` low-res bake per preset produces liquid; modified flag behaviour; existing create/delete tests still pass. | S013, S014 | `tests/test_presets.py`, `tests/test_bakes.py` |

### Slice 4 — Render layers

**Demoable when:** one click, then render — the compositor's Cryptomatte node picks Liquid, Spray, Foam and Bubbles apart, and the four AOV passes exist.
**Satisfies:** AC6

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S016 | S | Per-element materials + AOV outputs | Liquid and each whitewater element use distinct materials, each writing its own AOV. | S007 | `materials/mats.py`, `level2/still_water.py` |
| ✅ | S017 | S | Set Up Render Layers | Scene action: enable Material Cryptomatte and add the four AOVs on the active view layer; idempotent; reports what changed. | S016 | new operator in `ui/` or `core/` |
| ✅ | S018 | U | Button | "Set Up Render Layers" in the Water panel once any liquid setup exists. | S017 | `ui/panel.py` |
| ✅ | S019 | T | Render-layer tests (new) | Passes and AOVs enabled after the action, unchanged on a second run; element materials distinct. | S017 | new test file |

### Slice 5 — Ocean (Simulated) tracer

**Demoable when:** Create → Ocean (Simulated), add a rock to Water Obstacles, bake at Draft — waves roll from the paddle and break on the rock; Delete restores the scene.
**Satisfies:** AC7

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S020 | F | New mode | Mode constant, label, icon; Beta (`ui/beta.py`); registered with create/delete, bake buttons, Cancel Bake, obstacles row. | S007 | `constants.py`, `ui/beta.py` |
| ✅ | S021 | S | Tank build | Domain box, tagged water-block mesh with one-shot geometry flow, walls colliding, Draft/Resolution like other liquids, bake cache under `//aquasuite_cache/<id>`. | S020 | new module under `level2/` |
| ✅ | S022 | S | Wave paddle | Tagged paddle effector at one end with a sine F-Curve modifier on its location (Wave Height → amplitude, Wave Period → period); enough subframes. | S021 | new module |
| ✅ | S023 | U | Ocean box | Create button "Ocean (Simulated) · Beta"; box with Wave Height, Wave Period, Tank Size, Draft/Resolution, Water obstacles, Bake. | S022 | `ui/panel.py` |
| ✅ | S024 | T | Ocean tests (new/extend) | Create/delete leaves nothing tagged; `--bake` produces liquid whose surface height varies along the tank; obstacle inside the tank gets an effector; extend `tests/test_create_delete.py` and `tests/test_beta.py`. | S023 | new test file, `tests/test_create_delete.py`, `tests/test_beta.py` |

### Slice 6 — Ocean presets, whitewater and layers

**Demoable when:** Calm, Rolling Waves and Storm Surf bake to visibly different waves; Storm Surf shows foam and spray; render layers work on the ocean too.
**Satisfies:** AC2, AC8

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S025 | S | Ocean presets | Calm / Rolling Waves / Storm Surf: wave height, period, tank size, resolution, whitewater. | S022, S012 | preset module |
| ✅ | S026 | S | Ocean whitewater + layers | Ocean uses the whitewater routine and per-element materials. | S025, S016 | ocean module |
|  | S027 | T | Ocean preset tests (new) | Each preset applies; `--bake` wave amplitude ordering Calm < Rolling < Storm; Storm Surf has whitewater systems. | S026 | ocean test file |

### Slice 7 — Docs and release

**Demoable when:** README, troubleshooting, release checklist and thesaurus describe presets, whitewater, render layers and the simulated ocean.
**Satisfies:** AC9 (verified in checklist)

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S028 | D | User docs | README (what's in this version, Beta modes), troubleshooting (whitewater not rendering, slow bakes, ocean RAM), public README. | S027 | `README.md`, `docs/TROUBLESHOOTING.md`, `public_repo/README.md` |
| ✅ | S029 | D | Thesaurus terms | Add: Preset, Whitewater (Spray / Foam / Bubbles), Render Layers, Ocean (Simulated), Wave Paddle. | S028 | `docs/THESAURUS.md` |
| ✅ | S030 | D | Release checklist | In-app steps: each preset bakes, whitewater renders in Cycles and EEVEE, render layers separate in the compositor, ocean waves hit an obstacle, old scene opens unchanged. | S028 | `docs/RELEASE_CHECKLIST.md` |

### Dependency graph

```
S001 → S002 → S003 → S004 → S006
                │      └─ S007 ─┬─ S008 ─┬─ S011
                │               │        └─ S012 ─┬─ S013 ─┐
                │               │                 ├─ S014 ─┴─ S015
                │               │                 └─ S025 (+S022)
                │               ├─ S009
                │               ├─ S016 → S017 → S018
                │               │          └─ S019
                │               └─ S020 → S021 → S022 → S023 → S024
                ├─ S005 (→ S006)
                └─ S010 (→ S011)
S025 → S026 (+S016) → S027 → S028 → S029
                              └─ S030
```

## Dependencies

| REQ ID | Title | Reason |
| ------ | ----- | ------ |
| REQ-001 | 1.0 Launch Readiness | Uses its setup stamp, error pipeline, Water Obstacles, bake state/cancel, Beta labelling and test runner. |

## Out of Scope

- True separate view layers or proxy domain objects per element.
- Driving the simulated ocean from the Gerstner ocean, or blending the two.
- Buoys floating on the simulated ocean.
- Exposing Mantaflow's raw `sndparticle_*` settings in the panel.
- User-defined or saved custom presets.
- Migrating presets onto setups made before this change.

## Open Questions

- [x] **Q1 — Preset model.** Editable starting points; scenes store values, never live presets. *(Blaxine)*
- [x] **Q2 — Render layers.** Cryptomatte material mattes + AOVs, no extra view layers. *(Blaxine)*
- [x] **Q3 — Ocean waves.** Wave paddle in a tank. *(Blaxine)*
- [x] **Q4 — Resolved.** Systems are found by Mantaflow's names only on first discovery, then tagged; an unidentifiable renamed system shows a warning asking to restore its name. *(Blaxine)*
- [ ] **Q5 — Preset values.** Exact numbers per preset (resolution, viscosity, wave height/period, whitewater amounts). Deferred to tuning during Slices 3 and 6, judged from in-app renders.
- [x] **Q6 — Resolved.** Tank stays 20 × 8 × 4 m; Calm and Rolling Waves ship at resolution 160 with Draft off (~0.33 M cells). *(Blaxine)*
- [ ] **Q7 — Storm Surf decay.** Its baked crest-to-trough peaks at ~1.2 m around frame 48 and falls to ~0.2 m by frame 96 while the paddle keeps moving. Breaking waves, or lost paddle forcing? Deferred until the in-app visual review of Storm Surf.

## Smoke Test

> Developer runs the app; the agent does not self-run.

1. Create → Still Water, Preset Splashy (redo panel). Box shows "Splashy". Bake. F12 in Cycles and EEVEE: foam visible.
2. Untick Foam, re-bake: no foam particles, faster bake. Tick it again, re-bake: foam renders again.
3. Change Resolution: "(modified)" appears. Apply Calm Pour: the marker clears.
4. Rain Sim → Storm; hose Simulate Liquid → Fire Hose: both bake with whitewater.
5. Set Up Render Layers, render, compositor: Cryptomatte isolates Liquid, Spray, Foam and Bubbles.
6. Create → Ocean (Simulated), add a rock to Water Obstacles, Rolling Waves, bake at Draft: waves reach and break on the rock. Storm Surf: taller waves with foam.
7. Open a scene saved with v0.16.1: every liquid setup unchanged, Preset "Custom".

## Size

| T-Shirt Size | Estimated Hours | Notes |
| ------------ | --------------- | ----- |
| XL | 55–80 | Whitewater render setup across four modes and preset tuning are the bulk; the ocean (Slices 5–6) carries most of the risk and bake time. |

## Considered And Rejected

Nothing here is built. Each entry names the alternative, then why it lost.

- **Live presets.** Editing a preset definition in an update would change every saved scene using it — breaks the REQ-001 compatibility promise.
- **Locked presets with a Custom switch.** Power users lose fine control; tweaking would discard the preset label entirely.
- **Two presets per mode.** Too few looks for a one-click selling point.
- **Shared Quality + Look dropdowns for all modes.** Some looks don't fit some modes (a "stormy" Still Water).
- **Whitewater checkboxes only.** Every tweak would mean switching presets.
- **Simple + Advanced fold-out with raw `sndparticle_*`.** More UI and support surface than the convenience pitch needs.
- **True separate view layers via proxy domains.** Unproven that two domains can read one cache; doubles scene objects.
- **Cryptomatte plus experimental view-layer split.** Carries the proxy-domain risk for a duplicate path.
- **Ocean edges driven by the Gerstner ocean.** Mantaflow has no edge-forcing; weeks of work with high risk.
- **Wavy starting surface without a driver.** Waves die within seconds.
- **Identifying whitewater systems by particle type.** No API field exposes Mantaflow's internal particle types.
- **Leaving whitewater in HALO mode.** Neither Cycles nor EEVEE renders halos.

## Revision History

| Date | Author | Summary of Change |
| ---- | ------ | ----------------- |
| 2026-10-17 | Blaxine | Initial plan. |
| 2026-10-17 | Fabio Lopez | Implemented Slices 1–7 (commit f257622, v0.17.2): presets, whitewater, render layers, Ocean (Simulated); registration hardening; regression tests. |
| 2026-10-18 | Fabio Lopez | 0.18.0 efficiency pass (uncommitted at review): instanced visible rain, Preview rain fraction, write-only-on-change, scoped preset-edit detection, Generation Budget, planning memory allowance. |
| 2026-10-18 | Blaxine | Review fixes: Calm/Rolling ocean presets to resolution 160 (Draft off); whitewater settings no longer leak on toggle-off; stale tests updated (Beta modes, instanced rain streaks, 4.1-only import, opt-in known exit crash); new tests `test_presets.py`, `test_whitewater.py`, `test_simulated_ocean.py`; docs at 0.18.0. S015 (bake per preset) and S027 (baked Calm < Rolling < Storm) stay open; Q7 added. |
