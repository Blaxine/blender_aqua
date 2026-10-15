# AquaSuite — Troubleshooting

- **“My rain/snow doesn't move”** — press Play; particle systems
  simulate on playback. Jump to the scene start frame to reset.

- **“Ripples look like a grid / squares”** — the floor's vertex density
  *is* the ripple resolution, because ripples displace real vertices.
  Delete the assembly and recreate (higher floor detail is a per-create
  option in a future build), or subdivide `AQS_RRain_Floor` and re-bake.

- **“Ripples desync when I scrub backwards”** — Dynamic Paint waves are
  frame-order dependent. Use **Bake Ripples**, then scrub freely.

- **“The boat sinks / floats too high”** — adjust that buoy's
  **Buoyancy Offset** in the ocean assembly box; AquaSuite samples the
  water surface — it doesn't know your boat's waterline.

- **“Still Water does nothing”** — Level 2 and the liquid hose regimes
  **must be baked**; use the red bake button in the assembly box. The
  file must be saved first (caches live next to the .blend).

- **“Mantaflow water goes straight through my collision object”** —
  two rules to know. (1) Mantaflow never reads the Collision modifier
  (that's for particles only); liquid obstacles need a Fluid *Effector*
  modifier. AquaSuite adds these for you automatically — and since
  v0.12.2 it re-scans at **every bake**, so a cube added after the
  assembly was created becomes a real obstacle on the next bake. Just
  enable Collision on the object and re-bake. (2) Walls thinner than
  one simulation voxel leak regardless — AquaSuite pads obstacle
  influence by ~1 voxel automatically, but for very thin geometry
  raise Resolution or thicken the mesh. Note: the coupling is one-way —
  obstacles push water, but water never pushes a rigid body (a Blender
  limitation, not an addon setting).

- **“Water leaks through my floor”** — the floor needs
  `Physics > Collision` enabled (that's the universal obstacle switch),
  and for Mantaflow, thickness comparable to one voxel — raise the
  domain Resolution or thicken the floor.

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
