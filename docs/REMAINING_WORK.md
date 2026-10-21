# AquaSuite 0.21.0 — remaining work

Updated: 2026-10-21. Scope: REQ-003 implementation and review against
`c8939f5`, through `f48d83c`, plus the 0.19.1 fix pass on top of `54e172d`,
the 0.20.0 wave maker on top of `193378b`, and 0.21.0 Floating Objects on top
of `cc0b02e`.
This is a preview, not a release acceptance record.

**0.21.0** adds Floating Objects (F1 below): mass-based floaters on the
Mantaflow liquids, Pushes Water as one coupled water + floaters bake, and a
density for Plane Ocean floaters. Validated on **Blender 4.5.4 and 5.2.2 LTS**
only: fast suite and the floater `--bake` tests; the full `--bake` suite was
not re-run for 0.21.0.

**0.20.0** replaces Ocean (Simulated)'s paddle with a force-field wave maker
(S020, S023 below). It was validated on **Blender 4.5.4 and 5.2.2 LTS** only:
full `--bake` suite 551 passed, 0 failed, 1 skipped across both (after the
far-tank follow-up: Calm at resolution 400, 30 s cache, resolution warning,
Storm whitewater fix).

0.19.1 was validated on **Blender 4.5.x and 5.2.2 LTS** — Blender 5.1 (the
release-test version) and 4.1 were not installed on the machine that ran it.
Every result below names the Blender it came from; nothing here is a 5.1
result unless it says so.

**Blender 5.2 compatibility (found and fixed in 0.19.1).** The first 5.2.2
fast-suite run failed 34 checks: Plane Ocean, Plane Rain and Rain Simulation
could not be created. Two 5.2 API changes caused it:
- Geometry Nodes modifier inputs are no longer ID properties
  (`mod["Socket_0"]` raises "this type doesn't support IDProperties"); they
  are now `mod.properties.inputs.Socket_0.value`. `level1/ocean.py`'s
  `input_prop` picks the right location; `get_input`/`set_input` and the
  panel's ocean controls use it.
- The Random Value node now has a single output instead of one per data type
  (float was `outputs[1]`). `rain_sim._random_out` takes the enabled output.

After the fix, both suites pass on both versions (numbers under "Run the full
suite" below), and the 5.2 ocean bake numbers match 4.5's exactly. The panel's
ocean controls resolve to valid properties on both versions, checked by
script; they have not been looked at in the UI.

## Floating Objects (0.21.0)

- [ ] **F1 — Floating Objects: accept in the UI and in renders.** Built from
  the prototype in [FLOATERS_PROTOTYPE.md](FLOATERS_PROTOTYPE.md) (physics,
  numbers and design; §7 is what shipped). `core/floating.py` holds the
  **AQS Floating Objects** collection (membership is the rule, as for Water
  Obstacles; the two exclude each other), per-object Material / Density / Mass
  Override / Pushes Water, Bake Floaters, Clear Floaters, and a Free Bake that
  clears the floaters keyed on that water; Delete Assembly does too.
  `level2/floaters.py` is the physics. Plane Ocean floaters gained a Material
  that sets Buoyancy Offset (`floaters.buoy_offset`; sinking densities are not
  offered, a sinking Custom density leaves the offset alone and the panel
  says why).
  **Automated (4.5.4 and 5.2.2):** `tests/test_floating.py` 38 fast checks
  (collection, eligibility and mutual exclusion, materials and mass note,
  Pushes Water effector following membership and surviving obstacle sync,
  Outliner unlink restoring the user's action and transform, tank membership
  and warnings, panel drawing, Clear/Delete restore, Plane Ocean density) and
  11 bake checks (one-way: plank ~60% deep, steel on the floor, re-bake starts
  from the user's pose, Clear; coupled: one bake, water volume −0.34%, crate
  floats, fractions off, Delete restores). `tests/test_floaters.py` covers the
  physics (16 fast checks plus the baked Still Water float/sink test).
  **Not done:** looking at the panel and a coupled bake in the Blender UI (the
  coupled bake is blocking: Blender is unresponsive until it finishes. Esc
  is not expected to cancel it, since a blocking bake processes no window
  events, but that is untested; the panel and confirmation say Blender is
  busy and promise no Cancel); renders; Blender 5.1.
- [ ] **F2 — Floaters over-respond in waves.** In Rolling Waves a wooden box
  heaves 1.28–1.31× the local wave and pitches 1.35–1.53× the slope. 0.21.0
  adds the depth decay of wave pressure for Ocean (Simulated) floaters
  (Smith effect, k from the tank's dispersion relation, measured from the
  still level): heave/wave 1.22–1.28 on the same bake, pitch barely changed.
  Most of the excess is the box's own resonance (natural period ~1.2 s in a
  2.4 s wave), which needs wave-radiation damping or a diffraction correction.
- [ ] **F3 — Pushes Water re-bake on 4.5 depends on the Free Bake fix.** Bake
  Water + Floaters frees an existing liquid bake first. It calls
  `still_water.free_bake` when present (the separate Free Bake → Bake crash
  fix) and otherwise `aquasuite.free_fluid`, which crashes headless Blender
  4.5 when a bake follows. A first bake (nothing to free) works everywhere.
  Re-test a coupled re-bake on 4.5 once both are merged.

## Confirmed review finding

- [x] **P2 — Preserve a generated lighting world used by another scene.**
  Reproduced in Blender 5.1.2: add Water Lighting in scene A, assign its
  `AQS_Water_Sky` world to scene B, then delete A's lighting assembly.
  Scene B's world becomes `None`. The global world removal in
  `core/delete.py` unlinks the world from all users after restoring A.
  **Fixed in 0.19.1.** After restoring scene A, teardown asks
  `bpy.data.user_map` who still uses each owned world. If anything other
  than scene A (whose registry entry still points at it) uses it — another
  scene's world slot, another registry, or a fake user — the world is kept
  and ownership is relinquished by deleting its `aqs_owner` tag, so it becomes
  ordinary user data that no later sweep can touch. Otherwise it is removed
  as before. Regression tests in `tests/test_lighting.py`: shared world kept
  with its sky node tree and untagged, both directly and after save/reload;
  fake-user world kept and untagged; scene A restored. The existing
  unshared-world sweep check still passes. Reproduced failing first (6 checks)
  and passing after the fix on Blender 4.5.

## Implementation and bake validation

- [ ] **S019 — Review all twelve presets visually.** Render with Water Lighting
  in both Cycles and EEVEE on Blender 5.1. Record version, preset, resolution,
  Draft state, frame range, rendered frames, observations and proposed changes
  in [PRESET_REVIEW.md](PRESET_REVIEW.md). No user observations or renders have
  been supplied yet.
- [ ] **S020 — Diagnose and fix Storm Surf's late-bake decay.** Earlier recorded
  measurements show waves falling from approximately 1.2 m around frame 48 to
  0.2 m by frame 96 despite continued paddle motion. Investigate the cause and
  validate the correction against the visual review.
  **Diagnosed in 0.19.1; the underlying wave generation is not fixed.**
  Measured by baking at resolution 160 (and 80 for controls) on Blender 4.5,
  sampling the liquid mesh's surface height every frame in 0.5 m bins along
  the tank centreline:
  1. *The "decay" is a sampling artefact.* The test's per-frame range is
     dominated by water heaping against the paddle face, which swings with the
     stroke: peaks at frames 45, 81, 117 (36 frames = one 1.5 s period apart),
     troughs between. Frames 48 and 96 just fall on different phases.
  2. *Old Storm Surf asked for an impossible wave.* 0.9 m at 1.5 s has a 3.5 m
     wavelength, steepness H/L ≈ 0.26; real waves break above ≈ 0.142. Wave
     height over a period fell 1.45 → 0.91 → 0.14 → 0.08 m at x = −9, −8, −7,
     −4: it broke at the paddle. **Fixed:** the paddle stroke now comes from
     linear piston-wavemaker theory (dispersion relation for the 2.2 m water
     depth), requests are capped at 80% of the Miche breaking limit with a
     panel notice, and Storm Surf uses a 2.8 s period (H/L ≈ 0.085). Fast tests
     cover the theory, the cap, and paddle/wall clearance across periods.
  3. *The paddle does not drive travelling waves in any preset.* Even with
     valid settings, wave height dies within ~3 m (Rolling: 0.22–0.26 m near
     the paddle, 0.01–0.05 m from x = −6; at x ≥ −3 the surface stays flat to
     ±0.5 cm for all 120 frames). The decay length matches the paddle's local,
     non-travelling modes (≈ h/π). Controls: a dam-break hump with the paddle
     disabled travels the whole tank by frame ~60, so the solver propagates
     waves. Effector subframes 2 → 8, per-frame sine keyframes instead of the
     F-curve generator, CFL/timesteps, and FLIP ratio changed nothing.
     Blender's embedded Mantaflow script uses the obstacle-velocity grid as a
     wall condition (fractions off) or in the pressure solve (fractions on), so
     the paddle reaches the liquid with little or no velocity.
     Turning **fractions on** lets waves travel (x = 0 responds by frame ~90)
     but the moving paddle then swallows liquid: volume 262.5 → 246.7 m³ in
     120 frames (−6%), versus 272.1 → 269.4 m³ for a static fractions tank.
     Rejected.
  4. *A body-force wavemaker works in principle.* A Wind force field (plane,
     1.5 m reach) with a sine-animated strength produced waves that reach the
     far wall with the volume conserved, but every strength tried (1.5–40)
     overdrove the water at the wall. **Recommended follow-up:** replace the
     paddle with a calibrated full-depth forcing zone, calibrate strength per
     preset against target wave height mid-tank, then redo S023 and S019.

  **0.20.0: wave generation fixed; visual validation (S019) still pending.**
  New tanks drive their waves with a Wind force field instead of the paddle
  (`level2/simulated_ocean.py`): full depth and width, a zone `l` metres from
  the left wall, strength a sine at the wave period that fades in over the
  first period. All numbers below are Blender 4.5, liquid-mesh surface height
  in 0.5 m bins along the centreline (|y| < 1 m), probes in the 20 × 8 × 4 m
  tank (2.2 m water).
  1. *Why every earlier strength overdrove.* Blender passes a force field to
     the liquid as 0.2 × strength per frame and Mantaflow adds it to the
     velocity once per solver step, so Wind strength S accelerates the water
     by 0.2·S·fps m/s² (whole-tank static tilt: 0.195·S·fps at 24 and 48 fps,
     the same at resolution 80 and 160, doubled with two steps per frame).
     Strength 1.5 is ~7 m/s²; the waves need 0.2–1 m/s², i.e. S ≈ 0.04–0.2.
  2. *A strength from theory, not a fit.* A horizontal force uniform over the
     depth is curl-free, so it acts exactly like a surface pressure: the zone
     is a triangular pressure patch at the wall. Linear theory for an
     oscillating surface pressure gives H = 4ωF sin²(kl/2)/(g k² c_g), most
     efficient at l = λ/2; the zone is min(λ/2, 0.2 × tank length) (4 m for
     all three presets). The strength is that F / (0.2·fps), with no fudge
     factor: measured mid-tank height / theory is 1.17 (Calm), 0.87 (Rolling),
     1.04 (Storm).
  3. *Small waves need small cells.* Under a steady push the liquid surface
     settles into flat terraces one cell high: Mantaflow does not hold
     sub-cell slopes, so waves lower than about a cell do not travel. Calm's
     0.12 m waves at 12.5 cm cells (resolution 160) died within 3 m of the
     zone (≤ 0.03 m from x = −3) at the theory strength, while doubling it
     jumped to 0.25 m. At 10 cm cells (resolution 200) the theory strength
     gives 0.14 m mid-tank, so Calm's preset resolution became 200 (superseded:
     the waves still stalled further on, so Calm is now 400 in a smaller tank,
     point 8). At Draft resolution 80, Rolling's waves reach only
     0.09 m near the zone and do not travel: Draft is for layout only.
  4. *Waves take ~10 s to fill the middle of the tank.* At resolution 160,
     Rolling's mid-tank height grows 0.06 → 0.24 → 0.39 m over the periods
     ending at frames 114, 230 and 288 (24 fps). The 144-frame default cache
     showed them only about half-way down the tank (now 30 s, point 10).
  5. *Isolation.* The Wind is limited to the tank (tube falloff over the tank
     cross-section, positive side of the left wall only), and the domain's
     effector collection is the tank's own collection, so scene force fields
     do not disturb the calibrated waves and the wave maker does not push
     anything outside the tank.
  6. *Old files.* A tank saved with the paddle keeps it: opening, editing and
     baking it run the 0.19 paddle code unchanged (fast test: same stroke,
     phase and water block after save/reload; Wave Period edits still re-plan
     the stroke). Its panel offers **Upgrade Wave Maker**, which swaps the
     paddle for the wave maker and removes the paddle animation (undoable).
  7. *Unrelated finding (Windows).* When a mesh file's full path reaches
     Windows' 260-character limit, Mantaflow silently writes no liquid mesh:
     Bake All reports success, the data files (shorter names) are all there,
     and the domain shows as a box. Seen with mesh paths of 260–262
     characters (fine at ≤ 257). Fixed: Bake now counts the longest cache
     file path first (data, mesh, particles, guiding; frame digits from the
     end frame) and refuses at 260+ with AQS-E021 before Mantaflow runs
     (`tests/test_cache_path.py`, fast; Windows only for the refusal).

  **0.20.0 far-tank follow-up (2026-10-20): waves now cross the tank.** Report:
  after a 1500-frame bake the waves did not travel all the way across. The
  S023 gauges only covered x = −5…−3 m, so the far half had never been
  measured. Probes: Blender 4.5, 720 frames (30 s) at preset resolution,
  crest-to-trough per wave period in 0.5 m bins along the centreline.
  8. *Calm stalled — waves under a cell high do not travel.* At resolution 200
     (10 cm cells) Calm was 0.14 m at x = −4, 0.06 m at +2 and 0.002 m from
     +3 on, at every time. The solver's own velocity at the wave frequency
     (read from the data cache) fell to ~1% of its near-maker value past +2,
     so the water really stops; the mesh was not hiding waves. Cause, from
     Blender's liquid step script: `solvePressure` gets the cell flags but no
     level set (no ghost-fluid surface), so the free surface sits on whole
     cells and a displacement under about one cell gets no restoring force.
     It is a threshold, not damping: at resolution 80, Rolling forcing ×1, ×2,
     ×4 gave 0.034, 0.28 and 0.86 m mid-tank (8× for 2×). APIC, FLIP ratio
     1.0, particle band 30, 3 particles per cell and fractions did not help
     (fractions lost 1.8% of the water). Coarse cells also damp waves roughly
     as cell size squared (Rolling: 0.25/m at 25 cm, 0.03–0.07/m at 12.5 cm).
     **Fix: Calm is resolution 400 in a 20 × 4 × 2.5 m tank** (5 cm cells,
     2.5× Rolling's cell count): its waves reach the far wall (decay
     0.025/m). Old Calm tanks keep their own 20 × 8 × 4 m tank and resolution
     200 (fast test: reopen unchanged, not marked modified; Bake keeps both);
     their panel now says 400 would carry the waves.
  9. *Resolution warning.* The panel warns in red when the effective
     resolution (after Draft) is below `ceil(longest side / min(H / 2.4,
     0.125 m))` — Calm 400, Rolling and Storm 160 — and names the button that
     reaches it (High) or Custom; with Draft on at a sufficient resolution it
     says to turn Draft off. Bake shows the same text as a warning but still
     runs: a coarse or Draft bake is a valid layout preview, and blocking it
     would make Draft useless for ocean tanks. The 2.4-cells figure is Calm's
     measured crossing (stalled at 1.4); the 12.5 cm cap is the largest cell
     measured to carry waves across (Rolling stalled at Medium's 21 cm, 2.2
     cells, ~0.2/m decay). Fast tests cover Medium, Draft, Calm at Ultra and
     the panel text.
  10. *Rolling did reach the far wall — the far half is a standing wave.* At
     resolution 160, H at x = +4…+6 averaged over the last three periods was
     0.22–0.28 m against 0.36 m mid-tank, and 0.37 m at the far wall. In any
     one period the far wall's reflection (fitted R ≈ 1 up to x = +6; the fit
     is noisy) leaves near-flat nodes about λ/2 = 4.2 m apart (x = +4: 0.06 m,
     +8: 0.12 m) that drift from one period to the next. Wave fronts creep
     at ~0.7 m/s (linear group velocity 2.2 m/s) because their low leading
     edge is under a cell: they reach x = +4 only after 20–24 s, so the old
     144-frame (6 s) default never showed them. **New tanks bake 30 s**
     (`CACHE_SECONDS`, 720 frames at 24 fps) and extend the timeline if it is
     shorter (fast test).
  11. *Absorbers tried and rejected (volume).* A Drag force field does nothing
     to the liquid (Blender passes it no velocity). A 1:2.5 beach rising
     above the water cut reflection to R ≈ 0.23 but grew the liquid +0.87% to
     +0.94% (Rolling) and +10.9% (Storm, 720 frames); a submerged shelf (top
     0.6 m under water) gave +0.24% (Rolling) but +2.49% (Storm). The tank
     stays closed with a flat far wall. Consequence: Storm's mid-tank height
     matches its target until the reflection returns (0.90–0.94 m at
     11–17 s), then the standing wave stacks to 1.6–1.7 m (≈1.9×) by 30 s.
     The bake test therefore checks the target at 12 s and only bounds the
     late build-up.
  12. *Storm Surf crashed long bakes — whitewater never expired.* Mantaflow's
     secondary-particle lifetimes are solver time units (one frame =
     0.1 × 25/fps × time scale, so 1 s = 2.5 units at any fps); Blender's
     defaults 10–25 are 4–10 s. A whole tank of breaking waves passed ~10 M
     particles by frame 300 (particle cache 365 MB/frame and climbing) and
     Blender aborted loading them ("Calloc array aborted due to integer
     overflow … in particles", frame 303). Ocean tanks now use 1–3 s
     (2.5–7.5 units) and a quarter of the wave-crest/trapped-air sampling
     (`core/whitewater.py`, applied at every bake): a 720-frame Storm baked
     in 499 s with no crash, the particle cache levels off at 26–29 MB/frame,
     and the liquid volume changed +0.15% (peak +0.32%).
- [ ] **S021 — Apply review-supported preset tuning.** Update preset values only
  once the visual review establishes the needed changes. Recheck all affected
  presets after tuning.
- [ ] **S023 — Run and accept the 120-frame ocean bake test.** The test exists in
  `tests/test_simulated_ocean.py`, but has not been run as part of REQ-003.
  Verify Calm < Rolling Waves < Storm Surf and sustained late-quarter Storm
  waves. Record measurements and assess the provisional thresholds against
  visible results; do not lower thresholds merely to pass.
  **Run on Blender 4.5 (thresholds unchanged); passes, but not accepted.**
  Before 0.19.1: ordering passed; Storm sustain failed, samples
  `[0.70, 0.20, 0.53, 0.25, 0.96, 1.01]` m (min 0.20 < 0.3). With 0.19.1:
  Calm `[0.06, 0.08, 0.09, 0.10, 0.09, 0.07]`, Rolling
  `[0.15, 0.18, 0.14, 0.13, 0.17, 0.18]`, Storm
  `[0.48, 0.55, 0.57, 0.57, 0.59, 0.54]` m (mean 0.55 > 0.45, min 0.48 > 0.3).
  Blender 5.2.2 gives the same samples to two decimals.
  The metric is the spatial range over x = −9…6 m, which includes the bins
  next to the paddle, so it rewards slosh at the paddle as much as travelling
  waves (S020 point 3). Acceptance waits for a mid-tank wave-height metric
  alongside S020's new wave generator, and for S019.
  **0.20.0: metric replaced; passes on Blender 4.5 and 5.2; acceptance still
  waits for S019.** The test bakes each preset for 720 frames (30 s, the new
  default cache length) and measures wave height as crest-to-trough at five
  fixed gauges x = −5, −4.5, −4, −3.5, −3 m (clear of the 4 m forcing zone),
  at the wall (x = −9.5) and at five far-tank gauges x = +4 … +6 m, plus the
  liquid volume at the first and last frame. Two windows:
  - **calibration**, the last full wave period ending at 12 s (frame 288),
    before the reflection from the far wall returns: mid-tank and wall;
  - **late**, the mean over the last 3 wave periods before 30 s: far tank,
    mid-tank and wall.

  Checks: mid-tank (calibration) within 35% of the (capped) target; far tank
  (late) at least 0.5 × mid-tank; late mid-tank at most 2.5 × target; wall at
  most 2.5 × mid-tank; volume within 1%; Calm < Rolling < Storm. The runner
  now prints each preset's measurements as `INFO` lines. Measured on the full
  suite (identical on Blender 4.5.4 and 5.2.2):

  | Preset | Target | Mid-tank, 12 s (gauges) | Far tank, late | Mid-tank, late | Wall / late | Volume | Bake 4.5 / 5.2 |
  |---|---|---|---|---|---|---|---|
  | Calm (res 400, 20×4×2.5 m) | 0.12 m | 0.116 m (0.129, 0.106, 0.102, 0.130, 0.115) | 0.105 m | 0.078 m | 0.119 / 0.084 m | 104.26 → 104.82 m³ (+0.54%) | 1219 / 1112 s |
  | Rolling Waves (res 160) | 0.45 m | 0.400 m (0.372, 0.405, 0.400, 0.422, 0.398) | 0.280 m | 0.356 m | 0.521 / 0.468 m | 322.30 → 323.66 m³ (+0.42%) | 291 / 249 s |
  | Storm Surf (res 160) | 0.90 m | 0.937 m (0.891, 0.908, 0.913, 0.951, 1.020) | 1.801 m | 1.683 m | 1.093 / 1.561 m | 322.30 → 322.78 m³ (+0.15%) | 504 / 466 s |

  The far wall reflects almost everything, so after about 19 s the tank holds
  a partial standing wave whose nodes drift. Rolling's far half keeps 0.6–0.7 ×
  the mid-tank height on average; Storm's crests stack to about 1.9 × target
  (antinodes 2.0–2.2 m, nodes 0.3–0.4 m at x ≈ −7, −2, +2.5, +7.5). Calm's late
  heights fall below target because its waves are still close to the one-cell
  limit (S020 point 8). Absorbing the reflection was tried and rejected (S020
  point 11). Before the follow-up, Calm (res 200, 20×8×4 m) gave 0.141 m at
  12 s but stalled: about 0.03 m beyond x = 0.

  For comparison, the 0.19.1 paddle at Rolling Waves gave 0.38 m at the wall
  and 0.007–0.017 m from x = −5 onward. The 35% band, 0.5 × far share and 2.5×
  limits are provisional, chosen before any render was seen; assess them in
  S019.
- [x] Run the full `tests/run_tests.py --bake` suite after fixes and tuning.
  **Blender 4.5, 0.19.1: 219 passed, 0 failed, 1 skipped in 225 s** (the skip is
  `test_efficiency.py`'s restricted-registration check: Blender 4.5 has no
  `_bpy_restrict_state`). Before the fixes the
  same suite gave 207 passed, 1 failed (Storm sustain), 1 skipped.
  **Blender 5.2.2 LTS, 0.19.1 with the 5.2 fixes: 220 passed, 0 failed,
  0 skipped in 243 s**; 4.5 re-run after those fixes: 219 passed, 0 failed,
  1 skipped. Fast suite on 5.2.2: 200 passed, 0 failed, 4 skipped (bake-only
  files). Not run on 5.1 or 4.1 — repeat there before release.
  **0.20.0: Blender 4.5.4 244 passed, 0 failed, 1 skipped (same skip);
  Blender 5.2.2 245 passed, 0 failed, 0 skipped; 2069 s for both.** The ocean
  bake test then baked 3 × 288 frames (Calm at resolution 200).
  **0.20.0 after the far-tank follow-up (2026-10-20): 551 passed, 0 failed,
  1 skipped across both in 4704 s** — Blender 4.5.4 275 passed, 0 failed,
  1 skipped (same `test_efficiency.py` skip); Blender 5.2.2 276 passed,
  0 failed, 0 skipped. The ocean bake test now bakes 3 × 720 frames with Calm
  at resolution 400 (about 30 min per Blender of the 78 min total), and the
  runner's bake timeout is 3 h per file. Its heights and volumes under S023
  come from this run's `INFO` lines. Fast suite afterwards: see the zip entry
  below. Not run on 5.1 or 4.1.

## Manual acceptance

- [ ] Run the REQ-003 UI smoke checklist in Blender: Simple/Advanced for every
  mode, persistence after save/reload, one-click Create and redo options,
  lighting hint, hidden advanced panel controls, and usable Cancel Bake.
- [ ] Check Water Lighting in actual EEVEE and Cycles renders on Blender 4.2+
  and 5.x. Resolve Q4: whether the selected sky works in EEVEE on each supported
  version. Blender 4.1 test results do not establish compatibility with the
  declared minimum of 4.2.
- [ ] Verify lighting deletion restores the original world and changed settings
  after saving/reopening, including the multi-scene regression above.
- [ ] Verify Load Demo switches the visible window to the new scene, plays
  without baking, shows the floater/rain/hose hitting the wall, and renders
  correctly from its camera. Confirm the original scene is unchanged.
- [ ] Complete outstanding visual checks for whitewater toggles and Draft,
  Cryptomatte/AOV masks, ocean obstacle interaction, and legacy-scene behavior.
  Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the full procedure.
- [ ] **S028 — Run sessions with 3–5 Blender beginners.** Recruit participants
  (Q6); have each create a liquid and a real-time effect, adjust the look, bake
  when needed, add lighting and render without help. Record assistance,
  blockers, fixes/release decisions and retests. No sessions have been run.

## Documentation and release preparation

- [x] Reconcile older headings and deferred-work lists in
  `PRESET_REVIEW.md` and `RELEASE_CHECKLIST.md` with the 0.19.0 implementation:
  several automated checks already exist. Distinguish implemented tests from
  tests actually run and accepted.
  **0.19.1:** PRESET_REVIEW's deferred list is now a coverage table (implemented
  in / run on which Blender) plus what is still not automated; the checklist's
  feature gate says a box needs a 5.1 run, not just a test, and gained manual
  checks for the shared lighting world and the wave-height cap.
- [ ] Update [REQ003_REVIEW.md](REQ003_REVIEW.md) after addressing the new finding
  and completing validation. Mark requirement acceptance criteria only when
  supported by evidence.
  **Partly done:** a 0.19.1 section records P2, S020's diagnosis and the
  packaging fix; acceptance criteria stay unmarked because validation (5.1,
  visual review, beginner sessions) is incomplete.
- [x] Rebuild and validate the extension ZIP after code changes; test installation
  from that ZIP in a fresh Blender profile and check upgrade/re-enable behavior.
  **0.19.1, Blender 4.5:** `aquasuite-0.19.1.zip` built with Blender's extension
  builder and validated (41 files; no tests, plans, dotfiles, `dist/` or
  nested zips). In isolated profiles, both a fresh install and an upgrade over
  an installed 0.19.0 report v0.19.1, create Storm Surf (2.8 s) and Water
  Lighting, unregister cleanly on disable, and come back on re-enable.
  **Blender 5.2.2:** rebuilt after the 5.2 fixes with 5.2's builder (still 41
  files, same exclusions). A fresh install and an upgrade over 0.19.0 both
  report v0.19.1, create Plane Ocean, Plane Rain, Rain Simulation, Storm Surf
  and Water Lighting, and survive disable/re-enable; the same ZIP passes the
  same check in a fresh 4.5 profile. Repeat in Blender 5.1 before release.
  **0.20.0:** `dist/aquasuite-0.20.0.zip` built with Blender 5.2.2's extension
  builder (4.5's gives the same 41 files) and validated (41 files, same exclusions; the packaged
  `simulated_ocean.py`, `presets.py`, `panel.py` and manifest match the
  source). Fresh installs in isolated 4.5 and 5.2.2 profiles report v0.20.0,
  create Calm (resolution 200) and Storm Surf with a Wind wave maker, and
  re-enable. Upgrade check on 4.5: a Rolling Waves tank created and saved
  with the installed 0.19.1 opens under an installed 0.20.0 with the same
  paddle stroke (0.150 m), phase, rest position and water block; a Wave
  Height edit still runs the paddle path; Upgrade Wave Maker then swaps in
  the Wind wave maker (strength 0.108). Not baked under 0.20.0; repeat in 5.1.
  **0.20.0 rebuilt after the far-tank follow-up (2026-10-20)** with Blender
  5.2.2's builder: `extension validate` passes; 41 files, each byte-identical
  to the source; manifest version 0.20.0, website
  `https://github.com/Blaxine/blender_aqua`. Fresh install into an isolated
  5.2.2 profile (`extension install-file`) loads `bl_ext.user_default.aquasuite`
  v0.20.0 and creates all three ocean presets with a Wind wave maker and a
  1–720 cache: Calm 20 × 4 × 2.5 m at 400, Rolling and Storm 20 × 8 × 4 m at
  160, none warned; at 96 the warning names "160 or more (High)". Storm (and
  Rolling once Foam is on) gets 2.5–7.5-unit (1–3 s) whitewater lifetimes;
  the add-on disables cleanly. Fast suite on the final tree: 483 passed,
  0 failed, 9 skipped across 4.5.4 and 5.2.2 in 67 s (skips: the four bake-only
  files on each, plus 4.5's restricted-registration check).
  **0.21.0 (2026-10-21):** `dist/aquasuite-0.21.0.zip` built with Blender
  5.2.2's extension builder; `extension validate` passes; 43 files (41 plus
  `core/floating.py` and `level2/floaters.py`), each byte-identical to the
  source, with `docs/FLOATERS_PROTOTYPE.md` excluded like the other plans.
  Fresh install into an isolated 5.2.2 profile (`extension install-file`)
  loads v0.21.0; a Still Water tank at resolution 32 bakes, Bake Floaters keys
  a crate, Clear Floaters puts it back, a Plane Ocean floater attached as Wood
  gets Buoyancy Offset −0.05 m, and the add-on disables and re-enables
  cleanly. Not installed in 4.5 or 5.1; no upgrade-over-0.20.0 check.
- [ ] Finish release notes and the remaining release checklist before publishing.
  Publishing is a later action; this document does not authorize an upload.

## Evidence already available

- 0.20.0 (Blender 4.5.4 and 5.2.2): full `--bake` suite 551 passed, 0 failed,
  1 skipped in 4704 s (489 passed before the far-tank follow-up); ocean
  mid-tank, far-tank and wall heights, volumes and bake times under S023;
  force-scaling, resolution, legacy-tank and Storm whitewater findings under
  S020.

- 0.19.1 (Blender 4.5 only): fast suite 199 passed, 0 failed, 5 skipped; full
  `--bake` suite 219 passed, 0 failed, 1 skipped; P2 regression tests fail
  before the fix and pass after; ZIP fresh-install, upgrade-from-0.19.0 and
  re-enable checks pass. S020 diagnosis probes and controls are summarised
  under S020 above.
- 0.19.1 on Blender 5.2.2 LTS: the first fast run found two API breaks (see
  the top of this file); after fixing them, fast suite 200 passed, 0 failed,
  4 skipped and `--bake` suite 220 passed, 0 failed, 0 skipped; ZIP
  fresh-install, upgrade-from-0.19.0 and re-enable checks pass.

- Six implementation slices and a follow-up self-review commit are complete.
- Previous fast-suite run: **372 passed, 0 failed, 10 skipped** across Blender
  5.1.2 and 4.1.1. These results predate any future fixes listed here.
- All twelve low-resolution preset smoke bakes passed on 5.1.2 over 16 frames.
  Mesh presence does not prove visual quality or sustained waves.
- The 0.19.0 preview ZIP was built and checked for integrity/source consistency.
- The current review reproduced shared-world deletion and successfully exercised
  demo creation while the original object was in Edit Mode on Blender 5.1.2.
  It did not repeat the full suite or complete UI/render acceptance.

Source plan: [REQ-003](../requirements/InProgress/REQ-003-Beginner-Friendly-Experience.md).
