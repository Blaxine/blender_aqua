# AquaSuite — Water FX

**One-click, layered water for Blender 4.2+** — oceans, rain, reactive
ripples, snow, object-to-liquid, and an aimable water hose, behind a
single panel with a consistent mental model:

> **Level 1** is cheap and always real-time (surfaces and precipitation).
> **Level 2** is true liquid volume (an object becomes water).
> **Level 3** is directed liquid emission (a hose with four flow regimes).

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

| I want… | Do this | Then |
|---|---|---|
| A believable ocean | **Create → Ocean** | Press Play. Select your boat, click **＋** next to *Buoys* — it bobs and tilts on the swell, deterministically (farm-safe, no bake needed) |
| Rain | **Create → Rain** | Press Play |
| Rain with impact ripples | **Create → Reactive Rain** | Press Play; use **Bake Ripples** before scrubbing the timeline |
| Falling snow (7 flake shapes) | **Create → Snow** | Press Play |
| Turn my mesh into liquid | Select the mesh → **Still Water** | Click the red **Bake (required)** button — Level 2 is Mantaflow FLIP and must bake |
| Real simulated rain splashing into water | **Create → Rain Sim** (a setup menu opens) | Set Angle/Direction/Speed; select a mesh and click **＋** next to *Pool meshes* — it becomes water the rain physically splashes into. Bake (Draft first!). The drops render right away; baking adds the splashes and ripples |
| An aimable hose / jet | **Create → Water Hose** | Keyframe the cone-shaped nozzle empty; pick a regime (**Normal / Mist / Spray / Blast**). Mist is real-time; the liquid regimes must bake |

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
- **Obstacles are universal.** Any mesh with `Physics > Collision`
  enabled participates as an obstacle wherever the backend supports it
  (particles bounce; Mantaflow gets automatic, reference-counted
  Effectors that are removed cleanly when the last assembly using them
  is deleted). AquaSuite never touches an existing user Fluid setup — such
  objects are skipped with a warning.
- **Quality is one switch.** The scene-wide **Preview/Final** tier
  reduces particle display and ocean resolution non-destructively;
  your authored values come back exactly when you return to Final.
- **Stability clamps are the law.** Where a setting could exceed the
  solver's stable range (Gerstner choppiness, hose jet velocity),
  AquaSuite clamps it and tells you what to change to go further — the
  hose panel shows a red notice for as long as the jet is being slowed.

## Baking

Caches are written to `//aquasuite_cache/<assembly-id>/` **next to your
.blend** (relative paths — render-farm friendly). Unsaved files can't
bake; save first. Liquid modes (Still Water, hose Normal/Spray/Blast)
show a bake button that is mandatory by nature of FLIP simulation;
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

## Build status — read this once

This is **v0.14.0**, an implementation preview of the AquaSuite v1.0
technical design (TDD + Revision R1). Implemented and functional:

- All seven modes create, play, and delete cleanly
- UUID ownership, reversible deletion with restore records
- Deterministic closed-form buoys (stateless FIR smoothing — identical
  results on isolated farm frames and sequential playback)
- Programmatic 5-layer Gerstner GN ocean (fully inspectable node tree)
- Procedural 7-shape snow collection (ball + 6 dendrite flake types)
- Reactive Rain with anti-tunneling canvas substeps
- Refcounted, conflict-safe Mantaflow effectors
- R1-corrected hose velocity clamp (with the fix suggestion in the
  warning and a persistent panel notice)
- Hose **Fit Domain**: the domain shrink-wraps the jet's path; it refits
  automatically when Range or Spread changes (re-click after re-aiming)
- Rain Sim: thin rendered raindrops (2.5 mm default) fall the whole
  way; each drop is injected into the liquid simulation only in the
  frame before it hits the water, at its impact velocity, so the
  solver simulates just the splashes and ripples — in a domain fitted
  to the water, not the fall column. Rain Sims made with v0.13.4 or
  older: click **Rebuild Emitter**
- Preview/Final tier for particles + ocean resolution

Not yet in this build (tracked for 1.0 final):

- **Ocean wake solver** (interactive ripple height-field layered on the
  swell) and buoy *Wake Reaction* — buoys currently ride the swell only
- GN sim-zone / ocean bake operator (unneeded until the wake ships —
  default buoys are already farm-safe without a bake)
- Hose domain refit on *aim* change (keyframed nozzles: click Fit
  Domain at the widest aim, or scale the domain manually)
- Wetness darkening map on the Reactive Rain floor
- Preset engine, addon preferences, headless pytest harness

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
(it must be baked), “water leaks through my floor” (enable Collision
physics on the floor), and more.

## License

GPL-3.0-or-later, as required for Blender addons. The bundled technical
design documents describe intended behavior and roadmap.
