# AquaSuite — Troubleshooting

- **“My rain/snow doesn't move”** — press Play; particle systems
  simulate on playback. Jump to the scene start frame to reset.

- **“Ripples look like a grid / squares”** — the floor's vertex density
  *is* the ripple resolution, because ripples displace real vertices.
  Delete the assembly and recreate (higher floor detail is a per-create
  option in a future build), or subdivide `AQS_RRain_Floor` and re-bake.

- **“Ripples desync when I scrub backwards”** — Dynamic Paint waves are
  frame-order dependent. Use **Bake Ripples**, then scrub freely.

- **“The boat sinks / floats too high”** — pick the floater's
  **Material** next to it in the ocean assembly box: AquaSuite then works
  out how deep a closed mesh of that density sits. For a boat (hollow, or
  an open mesh) choose *Manual Offset* and set **Buoyancy Offset** by hand.

- **“Still Water does nothing”** — Level 2 and the hose's Simulate Liquid
  **must be baked**; use the red bake button in the assembly box. The
  file must be saved first (caches live next to the .blend).

- **“Water from two meshes doesn't mix”** — each Still Water setup is its
  own simulation. Keep one setup, select the other meshes and click **Add
  Mesh to Water** in its box (delete the other setups first). Don't join
  them (Ctrl+J): that changes your objects. A mesh named in an AQS-W021
  warning already has its own Fluid modifier and was left out; remove that
  modifier first.

- **“Meshes I never turned into water show up in my bake”** — in setups
  from older files, a domain took liquid from every Fluid flow inside it:
  other setups' water meshes or emitters, and your own Fluid flows. Bake
  again with the panel's Bake button: it gives the setup its own Flow
  collection (`AQS_Flows_<id>`), and only the meshes in its *Water meshes*
  list (and its own emitters) pour liquid. Blender's own Bake button in
  the Physics tab skips that step for an old setup.

- **“I added a water mesh but the liquid doesn't show it”** — the bake
  was made before the change, and the box says *Water meshes changed —
  Bake Again to include them*. Bake again.

- **“The bake folder's path is too long for Windows” (AQS-E021)** — Windows
  limits a file's full path to 259 characters, and Blender's liquid solver
  silently skips any cache file past it: the bake "finishes" but the liquid
  shows as a box. AquaSuite counts the longest cache file name before baking
  (whitewater particle files are the longest) and refuses instead. Save the
  .blend in a shorter folder (for example `C:\Projects\shot.blend`) or set a
  shorter Cache folder in the domain's Physics panel, then bake again.

- **“Water goes straight through my object”** — two rules to know.
  (1) Only objects in the **AQS Water Obstacles** collection block
  water: select the object and click **＋** next to *Water obstacles* in
  any liquid or hose box. AquaSuite adds what each simulation needs (a
  Collision modifier for the hose jet, a Fluid Effector for baked
  liquid) and re-checks at every bake. A Collision modifier you add
  yourself is not enough on its own. (2) Walls thinner than
  one simulation voxel leak regardless — AquaSuite pads obstacle
  influence by ~1 voxel automatically, but for very thin geometry
  raise Resolution or thicken the mesh. Note: the coupling is one-way —
  obstacles push water, but water never pushes a rigid body (a Blender
  limitation, not an addon setting).

- **“Water leaks through my floor”** — add the floor to Water
  Obstacles; for baked liquid it also needs a thickness comparable to
  one voxel — raise the domain Resolution or thicken the floor.

- **“Rain Sim fills up with giant water drops”** — every drop that
  splashes is injected as a blob at least one grid cell big (about 10 cm
  at Draft), which holds far more water than a real raindrop. Lower
  **Splash Amount** (Drops section) so fewer drops splash — every drop
  still renders — or raise Resolution so each blob is smaller. Older Rain
  Sims show "Old rain emitter — Rebuild": click it to get Splash Amount.

- **“The hose looks like a thick tube”** — that's *Simulate Liquid*
  (Beta): a liquid grid can't resolve a centimetre-wide stream. Turn it
  off for the thin real-time jet; turn on Motion Blur in render
  settings to stretch the droplets into streaks.

- **“My table was ‘kept out of the liquid simulation’”** — it already
  has a Fluid modifier of its own. AquaSuite never modifies existing Fluid
  setups; remove or change that modifier to include the object.

- **“Everything got slow after I added an assembly”** — switch Quality
  to **Preview** at the top of the Water panel; for Reactive Rain, bake
  the ripples.

- **“Blast won't go as fast as I asked”** — the velocity is clamped to
  what the solver can integrate stably at the current resolution and
  timestep budget. The warning tells you the **Max Timesteps** value
  that would admit your requested speed. (Counter-intuitively, raising
  Resolution makes the limit *tighter*, not looser.)

- **“I baked my rain but can't see it”** — three usual causes, all now
  handled automatically but worth knowing: the domain must not be in
  wireframe display (the liquid mesh IS the domain's display); drops
  must be at least ~1.6 voxels wide or the grid never registers them
  (AquaSuite now sizes drops from the voxel size — at very low
  resolutions rain is honest-but-chunky); and playback must be inside
  the baked frame range. Also raise *Drop Count* if rain reads sparse.

- **“Water looks opaque/solid in EEVEE”** — enable *Screen Space
  Reflections → Refraction* (4.1) or *Raytracing* (4.2+) in Render
  Properties. AquaSuite doesn't change your render settings for you.

- **“I renamed something and I'm scared”** — you're fine; AquaSuite tracks
  its objects by internal IDs, not names.

- **“A setting printed ‘could not set …’ in the console”** — a solver
  field name didn't match your exact Blender version. The setup still
  completes; set that one field manually in the physics panel and
  please report your Blender version.

## Presets, whitewater and the simulated ocean (0.18.0 preview)

- **No foam/spray/bubbles:** turn Draft off, enable the element and set Amount
  above zero, then re-bake. The domain must remain visible to renders. Do not hide
  it to isolate particles; use the AOV masks or Material Cryptomatte instead.
- **Whitewater disappears after a toggle:** use the AquaSuite controls and bake
  again. The add-on binds its render instances to the newly created systems. A
  legacy system renamed before first discovery cannot be identified safely:
  restore its original Spray/Foam/Bubbles name and change a Whitewater control.
  Once adopted, role tags preserve identification across renames.
- **Different Amount values affect bake cost together:** Mantaflow has a shared
  spawn budget. AquaSuite derives this from the largest enabled Amount and thins
  each element's render independently. Turning all three off disables their
  systems; Free Bake and bake again to remove stale cache data.
- **Preset says modified:** a saved preset-owned value differs, including edits
  in Blender's Physics panel. Apply explicitly to reset to the current recipe.
  This keeps old scenes independent of catalogue changes.
- **No AOV masks in the compositor:** run Set Up Render Layers on the view layer
  being rendered, then render again. The four AOVs are Value passes. If a Color
  AOV already uses one of their names, rename it first. Pick materials with a
  Cryptomatte node for material mattes.
- **Ocean waves are too coarse or die out part-way down the tank:** a wave
  lower than about one simulation cell does not travel — Blender's liquid
  solver puts the water surface on whole cells, so it stops where it shrinks
  below one. At 20 m tank length resolution 160 gives 12.5 cm cells and Draft
  halves that resolution, so small waves need Draft off and a higher
  resolution (Calm uses 400 in a narrower, shallower tank: 5 cm cells), or a
  smaller tank. No other liquid setting (APIC, FLIP ratio, particle count or
  band) changes this. The tank's panel warns in red when the resolution, or
  Draft's halved one, is too low ("Waves this small need resolution 160 or
  more (High) to cross the tank") — at Medium (96) Rolling Waves stall
  part-way. The rule: cells no bigger than the wave height ÷ 2.4 and no
  bigger than 12.5 cm. Bake still runs at a lower resolution, for layout.
- **Ocean waves do not reach the far end:** bake long enough. Wave fronts
  creep down the tank much slower than real waves (their low leading edge is
  under a cell), so they reach the far end only 20–25 s in; new tanks bake 30 s
  (720 frames at 24 fps) and extend the timeline to match. Tanks made before
  0.20 still use the old paddle, which barely makes travelling waves: click
  **Upgrade Wave Maker** in the tank's panel, then
  Bake Again.
- **Some spots in the far half stay flat for a while:** waves bounce off the
  far wall and the returning waves cancel the incoming ones at drifting
  points (a partial standing wave). Averaged over a few wave periods the far
  half keeps most of the mid-tank height.
- **Storm whitewater crashed Blender or filled the disk on long bakes:**
  before 0.20 spray and foam lived 4–10 s, so a whole tank of breaking waves
  piled up over 10 million particles by frame 300 and Blender crashed loading
  them. Every ocean bake now sets 1–3 s lifetimes and a lower spawn rate: Free
  Bake and Bake Again.
- **Ocean waves do not hit a rock:** place it inside the tank and add it to Water
  Obstacles. The wave maker is part of the tank and does not need adding there.
- **Other force fields have no effect on the tank:** each tank only listens to
  force fields in its own collection, so its calibrated waves stay as set. Move
  a field into the tank's collection to make it push the water.
- **Old scene looks different:** compare a saved copy before adopting controls.
  Loading alone only initialises metadata; it does not apply presets, add
  whitewater render objects, or change solver flags.
# Floating objects (0.21.0)

- **Bake Floaters is greyed out:** bake the liquid first — floaters ride
  the baked water. With Pushes Water on it bakes the water too, so it is
  always available.
- **An object isn't listed under Floating objects:** each liquid setup lists
  the floating objects whose origin is inside its tank. "N floating object(s)
  are in no liquid tank" means one is outside every tank: move it in.
- **“The mesh has holes” / “has a parent”:** the volume of an open mesh is
  undefined, so it can't float; close it (Fill, Solidify and apply) or use a
  closed stand-in and parent the detailed mesh to it — but the floater itself
  must have no parent. Unparent it with *Clear Parent and Keep Transform*.
- **The object doesn't move when I drag it:** after Bake Floaters it is keyed.
  Clear Floaters (×) puts it back and removes the keys; move it and bake again.
  Removing it from Floating Objects does the same.
- **A wood cube tips over onto a corner:** that is real. A cube between about
  a fifth and four fifths of water's density (cork, wood, oak) is unstable
  floating flat; ice and foam cubes stay level. Make it flatter (a plank or
  raft stays level).
- **Floaters in waves bob too much:** they respond to the full wave height with
  their own natural bounce; in Rolling Waves a wooden box heaves about 1.3× the
  wave. Heavier (deeper) objects and longer waves respond less.
- **Pushes Water: the water level doesn't rise:** Mantaflow removes the water
  inside an object instead of pushing it aside, so you get splashes and wakes
  but not a higher level (it loses under 1% of the water). Raising the water
  source slightly makes up for big objects.
- **Pushes Water: Blender stops responding while baking:** the water and
  floaters bake together in one blocking bake; Blender is busy until it
  finishes and has no Cancel. The confirmation gives a rough time. For a long
  shot, bake a short frame range first.
- **“Only N cells across: too small to push water”:** an object needs about 5
  simulation cells across to move water; raise Resolution or turn Pushes Water
  off (it still floats).
- **Free Bake or Delete moved my object:** floaters keyed on that water lose
  their keys and go back where they were, with your own animation restored.

# Beginner workflow (0.19.0 preview)

- **Water is invisible or looks like glass:** add Water Lighting, then use
  Rendered shading. Material Preview normally uses its own environment; enable
  Scene World and Scene Lights to see the added sky and sun. Liquid modes still
  need a saved file and a bake. Lighting does not generate liquid or add a camera.
- **Controls disappeared:** each setup defaults to Simple. Click its Advanced
  gear for whitewater, resolution details, bake range and specialist settings.
  Memory information and Set Up Render Layers require at least one Advanced box.
- **Create did not ask for options:** this is intentional. Change the preset in
  the setup box or open Adjust Last Operation (F9) immediately after creating.
- **A second Water Lighting cannot be added:** each scene permits one. Adjust
  its Sun Strength/Angle, or Delete it before creating another. Delete restores
  the saved previous world and every recorded scene setting, even if you edited
  those settings while Water Lighting was active.
- **Demo did not switch scenes:** choose AquaSuite Demo in Blender's scene
  selector. Background/script builds create the scene without switching a window.
  The demo uses only real-time effects; no liquid bake is needed.

