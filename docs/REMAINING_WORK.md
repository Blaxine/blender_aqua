# AquaSuite 0.20.0 — remaining work

Updated: 2026-10-19. Scope: REQ-003 implementation and review against
`c8939f5`, through `f48d83c`, plus the 0.19.1 fix pass on top of `54e172d`
and the 0.20.0 wave maker on top of `193378b`.
This is a preview, not a release acceptance record.

**0.20.0** replaces Ocean (Simulated)'s paddle with a force-field wave maker
(S020, S023 below). It was validated on **Blender 4.5.4 and 5.2.2 LTS** only:
full `--bake` suite 489 passed, 0 failed, 1 skipped across both.

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
     gives 0.14 m mid-tank, so **Calm's preset resolution is now 200** (about
     2× the bake time). At Draft resolution 80, Rolling's waves reach only
     0.09 m near the zone and do not travel: Draft is for layout only.
  4. *Waves take ~10 s to fill the middle of the tank.* At resolution 160,
     Rolling's mid-tank height grows 0.06 → 0.24 → 0.39 m over the periods
     ending at frames 114, 230 and 288 (24 fps). New tanks still default to a
     144-frame cache, which shows the waves only about half-way down the tank.
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
  **0.20.0: metric replaced; passes on Blender 4.5; acceptance still waits for
  S019.** The test now bakes each preset for 288 frames (12 s) and measures
  wave height as crest-to-trough over the last full wave period at five fixed
  gauges x = −5, −4.5, −4, −3.5, −3 m (clear of the 4 m forcing zone), plus
  the same at the wall (x = −9.5) and the liquid volume at the first and last
  frame. Checks: mid-tank within 35% of the (capped) target, wall at most
  2.5 × mid-tank, volume within 1%, and Calm < Rolling < Storm. Measured:

  | Preset | Target | Mid-tank (gauges) | Wall | Volume |
  |---|---|---|---|---|
  | Calm (res 200) | 0.12 m | 0.141 m (0.145, 0.141, 0.144, 0.140, 0.137) | 0.179 m | 329.73 → 329.94 m³ (+0.06%) |
  | Rolling Waves (res 160) | 0.45 m | 0.400 m (0.372, 0.405, 0.400, 0.422, 0.398) | 0.521 m | 322.30 → 322.61 m³ (+0.10%) |
  | Storm Surf (res 160) | 0.90 m | 0.937 m (0.891, 0.908, 0.913, 0.951, 1.020) | 1.093 m | 322.30 → 322.72 m³ (+0.13%) |

  For comparison, the 0.19.1 paddle at Rolling Waves gave 0.38 m at the wall
  and 0.007–0.017 m from x = −5 onward. The 35% band and 2.5× wall limit are
  provisional, chosen before any render was seen; assess them in S019.
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
  bake test now bakes 3 × 288 frames (Calm at resolution 200), so it is the
  slowest file. The runner prints pass/fail only; the mid-tank heights under
  S023 are from a direct 4.5 run of the same test file. Not run on 5.1 or 4.1.

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
- [ ] Finish release notes and the remaining release checklist before publishing.
  Publishing is a later action; this document does not authorize an upload.

## Evidence already available

- 0.20.0 (Blender 4.5.4 and 5.2.2): full `--bake` suite 489 passed, 0 failed,
  1 skipped; ocean mid-tank heights, wall heights and volumes under S023;
  force-scaling, resolution and legacy-tank findings under S020.

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
