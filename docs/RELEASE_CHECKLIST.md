# Release checklist

Run this for every release in **Blender 5.1** (the release-test version).
Nothing ships until every box is ticked. (Internal document — not
included in the extension zip.)

Version under test: `________`  Date: `________`

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
- [ ] Water Hose (Beta): Beta note on first create; jet fires **along the nozzle's aim**; Normal bake shows a stream; switch to Mist — mist cone along the aim
- [ ] Rain Sim (Beta): Beta note on first create; add a pool mesh; bake — splashes and ripples in the pool; rendered drops are thin and end at the water
- [ ] Rain Sim at Angle 45°: streaks lean along the direction of fall
- [ ] Start a liquid bake at High resolution: the panel shows "Baking…" with **Cancel Bake**; Cancel stops it within a few seconds, Blender stays responsive, frames baked so far still play; Free Bake removes them
- [ ] Start a liquid bake and press **Esc**: it stops the same way
- [ ] Bake buttons: **red** "Bake (required)" before baking with the trash button red and greyed out; after baking (or a cancelled part-bake) **blue** "Bake Again" with the trash button red and clickable; Free Bake turns them back. Bake Ripples: red before, blue after
- [ ] Reactive Rain → Bake Ripples: progress bar in the status bar, Blender stays responsive, the panel says "press Esc to stop", and Esc stops it
- [ ] Delete every setup: the scene is back to its previous state

## 4. Compatibility

- [ ] Open a .blend saved with the **previous release**: every setup looks and behaves exactly as before
- [ ] Open a .blend saved with **v0.14.0** (pre-release): each setup shows "Made with a pre-release version"; Rain Sim offers Rebuild

## 5. Errors and Beta notes

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
