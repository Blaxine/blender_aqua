# AquaSuite 0.19.0 — remaining work

Updated: 2026-10-19. Scope: REQ-003 implementation and review against
`c8939f5`, through `f48d83c`. This is a preview, not a release acceptance record.

## Confirmed review finding

- [ ] **P2 — Preserve a generated lighting world used by another scene.**
  Reproduced in Blender 5.1.2: add Water Lighting in scene A, assign its
  `AQS_Water_Sky` world to scene B, then delete A's lighting assembly.
  Scene B's world becomes `None`. The global world removal in
  `core/delete.py` unlinks the world from all users after restoring A.
  Update teardown to preserve externally used worlds and define how their
  ownership tags are relinquished. Add a regression test asserting A is
  restored and B retains its world and node tree. Keep ordinary unshared-world
  cleanup covered. This issue is confirmed; no fix has been applied.

## Implementation and bake validation

- [ ] **S019 — Review all twelve presets visually.** Render with Water Lighting
  in both Cycles and EEVEE on Blender 5.1. Record version, preset, resolution,
  Draft state, frame range, rendered frames, observations and proposed changes
  in [PRESET_REVIEW.md](PRESET_REVIEW.md). No user observations or renders have
  been supplied yet.
- [ ] **S020 — Diagnose and fix Storm Surf's late-bake decay.** Earlier recorded
  measurements show waves falling from approximately 1.2 m around frame 48 to
  0.2 m by frame 96 despite continued paddle motion. Investigate the cause and
  validate the correction against the visual review; this remains unfixed.
- [ ] **S021 — Apply review-supported preset tuning.** Update preset values only
  once the visual review establishes the needed changes. Recheck all affected
  presets after tuning.
- [ ] **S023 — Run and accept the 120-frame ocean bake test.** The test exists in
  `tests/test_simulated_ocean.py`, but has not been run as part of REQ-003.
  Verify Calm < Rolling Waves < Storm Surf and sustained late-quarter Storm
  waves. Record measurements and assess the provisional thresholds against
  visible results; do not lower thresholds merely to pass.
- [ ] Run the full `tests/run_tests.py --bake` suite after fixes and tuning.
  Retain logs, report failures and skips explicitly, and rerun affected
  regression tests before rebuilding the preview ZIP.

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

- [ ] Reconcile older headings and deferred-work lists in
  `PRESET_REVIEW.md` and `RELEASE_CHECKLIST.md` with the 0.19.0 implementation:
  several automated checks already exist. Distinguish implemented tests from
  tests actually run and accepted.
- [ ] Update [REQ003_REVIEW.md](REQ003_REVIEW.md) after addressing the new finding
  and completing validation. Mark requirement acceptance criteria only when
  supported by evidence.
- [ ] Rebuild and validate the extension ZIP after code changes; test installation
  from that ZIP in a fresh Blender profile and check upgrade/re-enable behavior.
- [ ] Finish release notes and the remaining release checklist before publishing.
  Publishing is a later action; this document does not authorize an upload.

## Evidence already available

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
