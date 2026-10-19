# Release checklist

Run this for every release in **Blender 5.1** (the release-test version).
Nothing ships until every box is ticked. (Internal document — not
included in the extension zip.)

Version under test: `________`  Date: `________`

## Feature review gate (introduced in 0.18.0; still open in 0.19.1)

Automated checks for several of these exist (see the coverage table in
[PRESET_REVIEW.md](PRESET_REVIEW.md)); a box is ticked only when the check was
**run in Blender 5.1** for the version under test, not when a test exists.
Simulated-ocean waves do not propagate yet (S020 in
[REMAINING_WORK.md](REMAINING_WORK.md)), so the ocean items below cannot pass
until its wave generator is replaced.

- [ ] Complete [the preset manual review](PRESET_REVIEW.md) in Blender 5.1.
- [ ] All twelve presets produce distinct, usable baked results.
- [ ] Whitewater renders in Cycles and EEVEE after off/on and Draft transitions.
- [ ] Cryptomatte and all four AOV masks separate the intended elements.
- [ ] Simulated-ocean waves propagate, hit an obstacle, and differ by preset.
- [ ] A v0.16.1 scene opens unchanged; save/reload preserves adopted controls.
- [ ] `python tests/run_tests.py --bake` passes, including `test_presets.py`,
      `test_whitewater.py` and `test_simulated_ocean.py`. Implementation alone does
      not satisfy this gate.

## 1. Automated suite

- [ ] `tests/blender_paths.local.json` lists Blender 5.1 (and 4.1 as an older-version check)
- [ ] `python tests/run_tests.py --bake` → **0 failed** (copy the summary line here)
- [ ] The version in `blender_manifest.toml` is the version being released

## 2. Build and install

- [ ] `blender --command extension build --source-dir <repo> --output-dir <dist>` produces `aquasuite-<version>.zip`
- [ ] Fresh Blender profile: Preferences → Get Extensions → ▾ → Install from Disk → the zip
- [ ] AquaSuite is enabled; the **Water** tab appears in the 3D Viewport N-panel
- [ ] Preferences → Add-ons → AquaSuite: the website link opens github.com/Blaxine/aquasuite

## 3. Every mode (Blender 5.1)

- [ ] Ocean: create, attach a floater (cube), play — it bobs and tilts; delete restores the cube
- [ ] Rain: create, play — streaks point along the fall, also with wind (particle Object Align X)
- [ ] Reactive Rain: create, play, Bake Ripples — ripples appear on the floor
- [ ] Snow: create, play — seven flake shapes tumble down
- [ ] Still Water (Beta): Beta note appears on the first create only; bake (Draft) — liquid appears
- [ ] Water Hose: no Beta note; press Play — Normal is a **thin stream along the nozzle's aim**, Spray a broken-up cone, Blast a long fast jet, Mist a fog cone; all render (F12) and Water Color tints them
- [ ] Hose aimed at a floor + wall in **Water Obstacles**: the water hits them and slides along; a Collision object **not** in the collection is ignored
- [ ] Hose → Simulate Liquid (Beta): bake (Draft) — liquid appears along the aim; turn it off — the jet is back
- [ ] Water obstacles row (＋ / −): add a cube from each liquid box; remove it, or unlink it in the Outliner — its added modifiers disappear, your own Collision stays
- [ ] Rain Sim (Beta): Beta note on first create; add a pool mesh; bake — splashes and ripples in the pool; rendered drops are thin and end at the water
- [ ] Rain Sim at Angle 45°: streaks lean along the direction of fall
- [ ] Rain Sim without a pool, Draft, 48 frames: splashes appear but the domain floor does not fill up; Splash Amount 0% = no splashes, 100% = visibly faster filling
- [ ] Start a liquid bake at High resolution: the panel shows "Baking…" with **Cancel Bake**; Cancel stops it within a few seconds, Blender stays responsive, frames baked so far still play; Free Bake removes them
- [ ] Start a liquid bake and press **Esc**: it stops the same way
- [ ] Bake buttons: **red** "Bake (required)" before baking with the trash button red and greyed out; after baking (or a cancelled part-bake) **blue** "Bake Again" with the trash button red and clickable; Free Bake turns them back. Bake Ripples: red before, blue after
- [ ] Reactive Rain → Bake Ripples: progress bar in the status bar, Blender stays responsive, the panel says "press Esc to stop", and Esc stops it
- [ ] Delete every setup: the scene is back to its previous state

## 4. Compatibility

- [ ] Open a .blend saved with the **previous release**: every setup looks and behaves exactly as before
- [ ] Open a .blend saved with **v0.14.0** (pre-release): each setup shows "Made with a pre-release version"; Rain Sim offers Rebuild

## 5. Errors and Beta notes

- [ ] Water Lighting in scene A, assign its sky world to scene B, delete A's lighting: A gets its old world back and B keeps the sky (also after save/reopen)
- [ ] Ocean (Simulated): set Wave Period to 1.5 s at Wave Height 0.9 m — a red "capped" notice appears; raise Period and it disappears
- [ ] Unsaved file → Still Water → Bake: popup with a plain message and Copy Report
- [ ] Copy Report → paste into a text editor: versions, OS, mode, message, traceback; **no** home folder, **no** .blend path or name
- [ ] Restart Blender: no Beta note on creating a Beta mode again
- [ ] Preferences → Show Beta Notes Again → the note returns on the next create

## 6. Render

- [ ] F12 with motion blur on a Rain + Ocean scene: renders without errors
- [ ] F12 on a baked Rain Sim: thin drops plus liquid splashes, no double rain
- [ ] During playback and during the render, no AquaSuite popup appears

## 7. Publish

- [ ] Changelog written; README "What's in this version" updated
- [ ] Zip uploaded to the store page (never to a public GitHub release)
- [ ] Public repo README/roadmap updated if anything changed
# REQ-003 beginner gate — not yet run

This gate requires real participants; automated tests are not a substitute.
Recruit **3–5 Blender beginners** and record their Blender version, experience,
date, and whether the session is in person or a screen share. No sessions have
been performed as part of this implementation.

- [ ] Each participant creates one liquid and one real-time effect without help.
- [ ] Each adjusts the look using Simple controls and finds Advanced if needed.
- [ ] Each saves, bakes when necessary, adds lighting and renders without help.
- [ ] Record time-to-first-result, assistance requested, errors and confusing labels.
- [ ] Every blocker has a linked fix and retest or a logged release decision.
- [ ] Visual review of all twelve presets in Cycles/EEVEE is complete.
- [ ] Storm Surf sustain and Calm < Rolling < Storm bake gates pass.
- [ ] UI/window smoke checks pass in actual Blender 4.2+ and 5.x sessions.

| Participant | Version / experience | Tasks and observations | Blocker / fix link | Retest |
| --- | --- | --- | --- | --- |
| Pending | | | | |

