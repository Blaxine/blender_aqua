# Preset manual review (current preview: 0.20.0)

## 0.20.0 changes to review — 2026-10-20

- **New wave maker for all three ocean presets.** New tanks push the water
  with a Wind force field over the 4 m next to the left wall instead of
  moving a paddle, so waves now travel down the tank. Strength comes from
  linear theory (no per-preset tuning). Measured on Blender 4.5 and 5.2
  (identical), mid-tank (x = −5…−3 m) at 12 s and far tank (x = +4…+6 m)
  averaged over the last 3 periods before 30 s: Calm 0.116 / 0.105 m
  (target 0.12), Rolling Waves 0.40 / 0.28 m (0.45), Storm Surf 0.94 /
  1.80 m (0.90); see S020/S023 in [REMAINING_WORK.md](REMAINING_WORK.md).
  Wave Height and Wave Period values are unchanged.
- **Calm: resolution 160 → 400 and tank 20 × 8 × 4 → 20 × 4 × 2.5 m.** Blender
  puts the water surface on whole cells, so a wave lower than about one cell
  stalls; Calm's 0.12 m waves need 5 cm cells to cross the tank. The narrower,
  shallower tank keeps the bake to about 19–20 min (4.5/5.2). Calm tanks made
  earlier keep their saved size and resolution; the panel warns that they
  need 400.
- **Bakes are now 30 s (720 frames at 24 fps) by default**, and creating a
  tank extends a shorter timeline. Wave fronts reach the far end only 20–25 s
  in. Measured bake times (4.5/5.2): Calm 1219/1112 s, Rolling 291/249 s,
  Storm 504/466 s.
- **Resolution warning.** The tank's panel and Bake warn in red when the
  resolution (or Draft's halved one) is too coarse for the wave height and
  name the one that works, e.g. "Waves this small need resolution 160 or more
  (High)". The bake still runs (a layout preview is legitimate).
- **Ocean whitewater lives 1–3 s** (was 4–10 s) and spawns at a quarter of the
  rate: Storm Surf crashed Blender at frame 303 with over 10 million particles.
  Judge whether foam trails now look too short.
- **To look at in the review:** the water within 4 m of the left wall moves
  up and down more than mid-tank (Rolling 0.52 m there vs 0.40 m) — decide
  whether it is visible in the shipped camera framings. After about 19 s the
  far wall's reflection makes a partial standing wave: some spots in the far
  half stay flat for a while, and Storm's crests grow to about 1.9 × the set
  height. Decide whether a shorter shot range or a smaller Storm height reads
  better.
- S021 can now tune the ocean presets: the generator no longer blocks it.

## 0.19.1 changes to review — 2026-10-19

- **Storm Surf period 1.5 s → 2.8 s.** Not a taste change: 0.9 m at 1.5 s is
  steeper than any water wave can be (H/L ≈ 0.26 vs ≈ 0.142 breaking) and broke
  at the paddle. Wave Height and the other presets' values are unchanged.
- **Paddle stroke from wavemaker theory** for all three ocean presets, so the
  paddle moves less than before for Rolling Waves (0.45 → 0.30 m stroke) and
  slightly more for Calm (0.12 → 0.13 m). Too-steep requests are capped with a
  red panel notice.
- **Known limitation, not tuning:** the paddle barely drives travelling waves
  in any preset (S020 in [REMAINING_WORK.md](REMAINING_WORK.md)). Do not tune
  ocean preset values (S021) against the current paddle; review the other nine
  presets as usual.

## REQ-003 review gate — 2026-10-18

The user has no visual observations/renders yet. No preset values or wave-paddle
forcing have been tuned in REQ-003. S019–S021 remain pending; the known Storm
Surf late-bake decay is not claimed fixed. Do not treat a mesh-presence smoke
test as visual acceptance or evidence of sustained breaking waves.

`tests/test_preset_bakes.py --bake` checks all twelve presets at capped resolution
over 16 frames. `tests/test_simulated_ocean.py --bake` samples the last quarter
of a 120-frame bake for all three ocean presets and checks ordering and Storm
sustain. Its provisional acceptance thresholds are mean >0.45 m and each late
sample >0.3 m; record actual measurements and review before changing them.

For every preset record Blender version, engine, resolution, Draft, frame range,
frame(s) rendered with Water Lighting, observed liquid/whitewater appearance,
and a proposed change. Render both Cycles and EEVEE. Keep current preset values
until that review establishes what should change.

Validation 2026-10-18: all twelve low-resolution preset smoke bakes passed on
Blender 5.1.2 (16 frames each). The 120-frame ocean ordering/sustain gate is
implemented but remains pending with S019–S021; no review renders were made.

The efficiency changes and their focused verification are documented in
`PERFORMANCE_REVIEW.md`. The bake/render acceptance steps below remain applicable.

0.17.2 adds rollback after failed registration and cleanup of partial
registration before retrying with the same loaded classes. It also prevents
repeated operator error wrapping. Restart before installing to clear any
classes/modules left in memory by earlier builds.

0.17.1 defers legacy whitewater initialization until after add-on registration,
fixing the `_RestrictData` / `scenes` error when enabling the extension.
Restart Blender before installing this build if a previous enable attempt failed.

Implementation preview, not a validated release. Automated functional checks
now cover the features (`tests/test_presets.py`, `tests/test_whitewater.py`,
`tests/test_simulated_ocean.py`; run with `--bake`); the visual review below is
still required. 0.18.0 also raises Calm and Rolling Waves to resolution 160
(Draft off): at Draft resolution 48 a cell is 42 cm, larger than their waves.

1. Install the preview ZIP in Blender 5.1. Open Water and confirm the new Ocean
   (Simulated) Create button. Keep an untouched copy of your old scenes.
2. Create a raised cube → Still Water → Splashy. Save, use a short bake range,
   bake, then render in Cycles and EEVEE. Check for liquid and foam. Toggle foam
   off/on and re-bake each time; it should return with a render instance.
3. Try Calm Pour and Thick. Change Resolution or an Amount: the label should say
   modified. Apply again: it should clear. Check that Apply retains cache files
   and that you can re-bake through the normal controls.
4. Toggle Spray/Foam/Bubbles independently and change Amount/Size. Draft should
   suppress whitewater without losing your checkbox choices. Turn Draft off and
   re-bake. With all elements off, free and re-bake: no secondary systems/cache.
5. Try Drizzle/Rain/Storm on Rain Sim with a pool. Try Garden/Fire Hose/Sprinkler
   by creating a hose with Simulate Liquid enabled. Switching a hose regime
   should seed whitewater defaults; editing Pressure afterwards should preserve
   the checkbox choices.
6. Click Set Up Render Layers twice. The active layer should have Material
   Cryptomatte and exactly one Value AOV for each AQS_Liquid/AQS_Spray/AQS_Foam/
   AQS_Bubbles name. Render and inspect all four masks in the compositor.
7. Create Ocean (Simulated) → Rolling Waves. Add a rock inside the tank to Water
   Obstacles. Save and bake several periods. Compare Calm, Rolling Waves and
   Storm Surf; test Wave Height/Period and Tank Size. Storm Surf starts with
   Draft off and whitewater enabled. Delete the tank; the rock must remain and
   generated objects/materials/actions should be removed.
8. Open a copy of a v0.16.1 scene. Setups should show Custom, with whitewater
   flags matching their domains and the same appearance. Save/reopen, then opt
   one setup into the new controls; other setups should remain unchanged.
9. Rename a whitewater particle system after adoption and toggle its element.
   For an unidentified renamed legacy system, expect a warning, not guessed
   ownership. Check Cancel Bake, Copy Report, and the new Beta note as well.

Record the preset, engine, resolution/Draft, frame range, and the visible result
for anything that fails. Exact preset values and the 20 × 8 × 4 m tank default
(Calm 20 × 4 × 2.5 m) are initial choices awaiting this review.

## Automated coverage (reconciled 2026-10-19)

Implemented means a test exists; run means it was executed and the result is
recorded. The 0.19.1 runs were on Blender 4.5 only.

| Check | Implemented in | Run |
|---|---|---|
| Create/delete, Beta and package cover the new mode/actions | `test_create_delete`, `test_beta`, `test_package` | 4.5 (0.19.1); 5.1.2 + 4.1.1 (0.19.0) |
| All twelve preset packages apply; modified marker | `test_presets` | same |
| Whitewater toggles off/on, Draft suspends and restores, render-ready | `test_whitewater` | same |
| Idempotent Cryptomatte + AOV setup | `test_presets` | same |
| Each preset bakes liquid (16 frames, capped resolution) | `test_preset_bakes --bake` | 4.5 (0.19.1); 5.1.2 (0.19.0) |
| Baked Spray/Foam/Bubbles have particles | `test_whitewater --bake` | 4.5 (0.19.1) |
| Ocean mid-tank, far-tank and wall wave height per preset, volume, ordering (720 frames) | `test_simulated_ocean --bake` | 4.5 + 5.2.2 (0.20.0), see S023 |
| Minimum-resolution warning (panel, Draft, old Calm tank) | `test_simulated_ocean` | 4.5 + 5.2.2 (0.20.0) |
| Wave-maker theory, steepness cap, zone/water placement, fps scaling | `test_simulated_ocean` | 4.5 + 5.2.2 (0.20.0) |
| Legacy paddle tank unchanged after reload; Upgrade Wave Maker | `test_simulated_ocean` | 4.5 + 5.2.2 (0.20.0) |
| Shared/fake-user lighting world survives delete | `test_lighting` | 4.5 (0.19.1) |

Still not automated: legacy (v0.16.1) whitewater hydration from a real saved
file, renamed legacy whitewater systems, rendered AOV mask contents in either
engine, baked wave interaction with an obstacle, and a real pre-0.20 saved
file (the legacy-tank test rebuilds a paddle tank in the current version).
