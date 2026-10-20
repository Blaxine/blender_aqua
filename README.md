# AquaSuite — Water FX

**One-click, layered water for Blender 4.2+** — oceans, rain, reactive
ripples, snow, object-to-liquid, and an aimable water hose, behind a
single panel with a consistent mental model:

> **Level 1** is cheap and always real-time (surfaces and precipitation).
> **Level 2** is true liquid volume (an object becomes water).
> **Level 3** is directed water (a real-time hose with four flow regimes).

Every mode is a one-button setup. Every generated assembly is
**reversible** (one Delete button restores your scene) and
**inspectable** (open any generated node tree, particle system, or
domain — nothing is hidden magic).

---

## Requirements

- Blender **4.2 or newer** (installed as an extension)
- **Zero external dependencies** — AquaSuite uses only Blender's built-in
  Python (`bpy`, `bmesh`, `mathutils`) and the standard library. Nothing
  to pip-install, no internet access needed, nothing version-pinned
  beyond Blender itself.
- 1 Blender unit = 1 metre, default gravity (the tools assume real-world scale)

## Installation

Install the **`aquasuite-<version>.zip`** you downloaded — do **not**
unzip it first:

1. **Edit → Preferences → Get Extensions** (Blender 4.2+)
2. Click the **dropdown arrow (▾) in the top-right corner** →
   **Install from Disk…**
3. Select `aquasuite-<version>.zip`.
4. It installs **and enables automatically** — search **“aqua”** and you
   should see **AquaSuite — Water FX** with its checkbox already ticked.

If it doesn't appear: open **Window → Toggle System Console** *before*
installing and repeat — any registration error will print a Python
traceback there. (Also make sure the search box is clear and
*Enabled Add-ons Only* is unchecked.)

### After installing

In the 3D Viewport, press **N** and open the new **Water** tab.

To uninstall: disable/remove the addon in Preferences. Assemblies in
saved files keep working where the backend allows (see *Graceful
degradation* below).

## Quick start

Setups open in **Simple** view. Click the gear-shaped **Advanced** toggle in a
setup's header for all controls; each box remembers its choice. Create buttons
build immediately with their default look. Use Preset in the box, or Blender's
Adjust Last Operation panel (F9) immediately after creation, to change options.

Try **Load Demo** for a separate, lit real-time scene: press Play to see an ocean
floater, rain and a hose hitting a wall. Your original scene remains in the
scene selector. You can delete the demo scene there when finished.

If water is hard to see, choose **Add Water Lighting**. It adds an owned sky and
sun and adjusts supported water render settings. Delete that lighting assembly
to restore the previous world and changed settings. Use Rendered shading; in
Material Preview, enable Scene World and Scene Lights to see the actual setup.
Memory information and Set Up Render Layers appear while any box is Advanced.

| I want… | Do this | Then |
|---|---|---|
| A believable ocean | **Create → Ocean** | Press Play. Select your boat, click **＋** next to *Buoys* — it bobs and tilts on the swell, deterministically (farm-safe, no bake needed) |
| Rain | **Create → Rain** | Press Play |
| Rain with impact ripples | **Create → Reactive Rain** | Press Play; use **Bake Ripples** before scrubbing the timeline |
| Falling snow (7 flake shapes) | **Create → Snow** | Press Play |
| Turn my mesh into liquid | Select the mesh → **Still Water** | Click the red **Bake (required)** button — Level 2 is Mantaflow FLIP and must bake |
| Real simulated rain splashing into water | **Create → Rain Sim** | Pick a preset; adjust Drop Amount, Speed and Angle. Select a mesh and click **＋** next to *Pool meshes*, then save and Bake. Advanced holds Draft, resolution and other settings |
| An aimable hose / jet | **Create → Water Hose** | Press Play — rotate or keyframe the nozzle to aim; pick a regime (**Normal / Mist / Spray / Blast**), all real-time; set **Water Color**. Add floors and walls to **Water Obstacles** so the water hits them |

## The rules AquaSuite lives by

- **Names are yours.** Rename anything AquaSuite made — everything keeps
  working. Ownership is tracked by internal IDs, never names.
- **Delete is a real undo.** *Delete Assembly* removes exactly what
  AquaSuite created and restores anything it changed on your objects
  (visibility, constraints, Fluid modifiers — found by type, so renaming
  them doesn't strand them). If the assembly has bake files on disk,
  Delete asks whether to remove those too (off by default — undo can't
  bring files back).
- **Your data is never converted.** *Still Water* hides your source
  mesh and renders liquid in its place; delete the assembly and your
  object comes back untouched.
- **One place for obstacles.** Click **＋** next to *Water obstacles* in
  any Still Water, Water Hose or Rain Sim box to add the selected objects
  to the scene's **AQS Water Obstacles** collection: everything in it
  blocks water in every simulation (and only what's in it — the hose
  ignores other collision objects). Remove an object (**−**, or unlink it
  in the Outliner) and AquaSuite takes back exactly what it added.
  Water sources and existing user Fluid setups can't be obstacles.
- **Quality is one switch.** The scene-wide **Preview/Final** tier
  reduces particle display and ocean resolution non-destructively;
  your authored values come back exactly when you return to Final.
- **Stability clamps are the law.** Where a setting could exceed the
  solver's stable range (Gerstner choppiness, hose jet velocity),
  AquaSuite clamps it and tells you what to change to go further — the
  hose panel shows a red notice for as long as the jet is being slowed.

## 0.18.0 efficiency preview

Visible Rain Sim drops now stay instanced, Preview can reduce visible rain
without reducing rendered density, and settings updates avoid redundant work.
Whitewater has a shared **Generation Budget**; Size edits affect appearance only.
Existing Rain Sim setups can opt into **Optimize Visible Rain**.
See [performance changes and checks](docs/PERFORMANCE_REVIEW.md) for details,
memory-estimate limitations, and the remaining visual review.

## Liquid presets and whitewater

This implementation is ready for manual review; preset appearance, whitewater
renders and wave-tank behaviour still need acceptance checks. Automated functional
checks are deferred until after that review.

Liquid Create dialogs offer editable presets. The assembly's **Preset → Apply**
row applies another starting point later. Settings are saved in the .blend;
future catalogue changes do not rewrite them. Editing a preset-owned value shows
**(modified)**. Apply resets that marker. Applying a preset does not delete your
cache files: **Bake Again** to update the result.

| Mode | Presets |
| --- | --- |
| Still Water | Calm Pour, Splashy, Thick |
| Rain Sim | Drizzle, Rain, Storm |
| Hose → Simulate Liquid | Garden, Fire Hose, Sprinkler |
| Ocean (Simulated) | Calm, Rolling Waves, Storm Surf |

**Whitewater** gives Spray, Foam and Bubbles their own enable switch, Amount and
Size in metres. Draft suspends them and keeps the checkboxes for later. Amount 0
also suspends an element. Presets with whitewater, including Splashy and Storm
Surf, start with Draft off. Regime changes on the hose seed whitewater defaults;
subsequent pressure edits preserve your choices. Re-bake after changing these
controls. Mantaflow shares spawn thresholds between elements; Amount tunes that
shared budget and independently thins each element's rendered instances.

**Set Up Render Layers** enables Material Cryptomatte and four scalar AOVs on the
active view layer: `AQS_Liquid`, `AQS_Spray`, `AQS_Foam`, `AQS_Bubbles`. Pick the
separate materials in a compositor Cryptomatte node, or use the AOV masks from
Render Layers. No additional view layers are created. This action intentionally
leaves those view-layer settings in place when an assembly is deleted.

**Ocean (Simulated) · Beta** creates a closed tank filled with still water and a
wave maker: a Wind force field whose push swings back and forth at the wave
period over the first few metres of water next to the left wall, top to bottom.
Wave Height is the target height mid-tank — the push is derived from it, the
period and the water depth with linear wave theory — and Wave Period is in
seconds. Waves too steep to exist (they would break where they are made) are
capped, and the panel says so: raise Period for taller waves. Tank Size
defaults to 20 × 8 × 4 metres (Calm: 20 × 4 × 2.5). The push fades in over the
first wave period; wave fronts take 20–25 seconds to reach the far end of a
20 m tank, so new tanks bake 30 seconds (720 frames at 24 fps) and extend the
timeline to match. The far wall reflects the waves, so late in a long bake the
tank holds a partly standing wave: some spots rise and fall less for a while
and others more (Storm Surf reaches about 1.9× its set height mid-tank by
30 s). Place a rock inside the tank and add it to Water Obstacles, save, then
bake. Waves smaller than about one simulation cell do not travel — Blender's
liquid solver puts the surface on whole cells — so the panel warns when the
resolution (or Draft's halved one) is too low for the waves to cross the tank
and names the resolution that works: High (160) for Rolling Waves and Storm
Surf, 400 for Calm. Bake still runs, for layout previews. This mode does not
use the procedural ocean's buoys or wake system.

Tanks made before 0.20 keep their original paddle and bake exactly as before.
Their panel offers **Upgrade Wave Maker**, which swaps the paddle for the new
wave maker (Bake Again afterwards).

Existing setups initially show **Custom**. Their whitewater flags are read from
the domain without applying a preset or modifying its solver/render setup. Edit
Whitewater or explicitly apply a preset to adopt the new controls.

## Baking

Caches are written to `//aquasuite_cache/<assembly-id>/` **next to your
.blend** (relative paths — render-farm friendly). Unsaved files can't
bake; save first. Liquid modes (Still Water, Rain Sim, Ocean (Simulated), and the hose with
*Simulate Liquid* on) show a bake button that is mandatory by nature of
FLIP simulation;
Reactive Rain's ripple bake is optional but recommended before
timeline scrubbing.

## Baking speed & stability (read if bakes feel slow)

Bakes run as a **background job**: Blender stays responsive, a progress
bar appears in the status bar, and **Esc cancels**. A liquid bake that
looks frozen almost never is — but you no longer have to guess.

What actually costs time, in order:

1. **Resolution** — cost scales roughly with the cube. 96 → 160 is
   about 5× slower; 160 → 256 another ~4×. It's the panel's
   *Resolution* slider; iterate low, finish high.
2. **Domain size** — voxels spent on empty air are wasted. For the
   hose, use **Fit Domain** after aiming: it shrink-wraps the domain to
   the jet's actual path (typically several times fewer cells than a
   generic box).
3. **Frame range** — cost is linear in frames. New assemblies default
   to a 60-frame cache; extend *Bake Start/End* only when you need to.
4. **Draft quality** (hose, Rain Sim) — on by default: half resolution, 1× mesh,
   no secondary particles. Roughly 8–15× faster. Turn it off only for
   the final bake.
5. **Secondaries** (Spray regime) — foam/spray/bubbles are a second
   simulation pass, 2–4× the time. Draft disables them automatically.
6. **Blast physics** — high jet velocity forces up to 12 solver
   substeps per frame for stability. That's inherent; lower *Pressure*
   if a draft blast is still too slow.

Crash avoidance: the addon clamps velocities to the solver's stable
range, shows a live RAM estimate in the panel, **asks for confirmation**
before baking anything estimated above 2 GB, and never blocks the UI
during a bake. If Blender's memory climbs into swap during a big
final bake, cancel (Esc), lower Resolution one notch, and re-bake —
liquid at 200+ resolution can genuinely need many GB of RAM.

## What's in this version

- Eight modes, including the new simulated-ocean preview; every setup records
  the version that made it. Feature validation is tracked in `docs/PRESET_REVIEW.md`.
- Deterministic buoys: floating objects ride the ocean with no bake and
  give identical results on render farms.
- Programmatic 5-layer Gerstner ocean (fully inspectable node tree).
- Rain, Reactive Rain and Snow: real-time, with streaks that follow the
  direction of fall.
- Rain Sim: thin rendered raindrops fall the whole way; the liquid
  simulation only handles the splashes and ripples where they land.
  **Splash Amount** (default 10%) sets how many drops splash, so the
  pool doesn't fill up with simulated water.
- Water Hose: an aimable, keyframable nozzle with four real-time
  regimes — a thin Normal stream, a broken-up Spray, a fast Water Blast
  and Mist — that hit Water Obstacles and splash along them; Water Color
  tints it. *Simulate Liquid* (Beta) swaps the jet for a baked Mantaflow
  liquid when you need pools.
- 0.20.0: Ocean (Simulated) makes waves with a force-field wave maker instead
  of a paddle, so waves now travel down the tank and reach about their target
  height mid-tank (Calm, Rolling Waves and Storm Surf were measured). Old tanks
  keep their paddle until you choose Upgrade Wave Maker. Waves now cross the
  whole tank: Calm bakes at resolution 400 in a 20 × 4 × 2.5 m tank, new tanks
  bake 30 s, and the panel warns when the resolution is too low for the waves
  to travel. Storm Surf no longer crashes Blender on long bakes (its
  whitewater lives 1–3 s instead of 4–10 s). Liquid bakes refuse to start when
  a cache file path would pass Windows' 260-character limit. The hose's cone now
  points where the water goes, so aiming the cone aims the jet (hoses saved
  earlier keep spraying where they did).
- 0.19.1 fixes: deleting Water Lighting no longer strips the sky from
  another scene that uses it; Ocean (Simulated) caps waves that would break,
  and Storm Surf uses a 2.8 s period so its 0.9 m waves can exist. Plane
  Ocean, Plane Rain and Rain Simulation work again on Blender 5.2, which
  changed how Geometry Nodes modifier inputs and the Random Value node are
  accessed.
- If anything fails, a popup explains it in plain words and **Copy
  Report** puts a ready-to-paste bug report on your clipboard (personal
  paths removed).

## Beta modes

**Still Water, Rain Sim, Ocean (Simulated), and the hose's Simulate Liquid are Beta.** They run Blender's
Mantaflow liquid solver, so they must be baked, bakes slow down and use
a lot of RAM as Resolution rises, and Draft (fast) results are coarse.
They're fully usable — just plan bake time into your shot. A short note
explains this the first time you create each one; *Preferences → Add-ons
→ AquaSuite → Show Beta Notes Again* brings it back.

## Roadmap

Planned for future free 1.x updates, in no fixed order and without dates:

- **Ocean wake**: interactive ripples behind moving objects, with buoys
  reacting to them.
- Hose domain refit when the nozzle is re-aimed (today: click Fit Domain
  at the widest aim).
- A wetness effect on the Reactive Rain floor.
- More preset looks after the initial liquid-preset catalogue.

## Support

Found a bug or have a question? Open an issue at
**https://github.com/Blaxine/blender_aqua/issues** — paste the text from
**Copy Report** if AquaSuite showed an error. Support is best-effort.

Field names in the Blender Python API occasionally shift between
versions; AquaSuite sets solver fields defensively and logs anything it
couldn't set to the console rather than failing your setup.

## Graceful degradation

A file full of AquaSuite assemblies opened **without the addon** keeps its
ocean surface animating (the node tree is self-contained), keeps baked
caches playing, and keeps all materials. Buoys freeze in place (their
driver is the addon) and the Water panel is absent. Nothing errors.

## Troubleshooting

See `docs/TROUBLESHOOTING.md` (also shipped inside the addon), which
covers the common cases: “my rain doesn't move” (press Play), “ripples
look like squares” (raise floor detail), “Still Water does nothing”
(it must be baked), “water leaks through my floor” (add the floor to
Water Obstacles), and more.

## License

GPL-3.0-or-later, as required for Blender addons. The bundled technical
design documents describe intended behavior and roadmap.
