# 0.18.0 efficiency preview

## Changes

- New Rain Sim setups keep visible drops instanced. Only liquid impact geometry
  is realized. Preview uses 25% of visible rain density through Is Viewport;
  rendering and liquid emission keep authored density.
- Existing Rain Sim setups offer **Optimize Visible Rain**, an undoable opt-in
  replacement of the visible drop node tree. It preserves named input values
  and the droplet material, and leaves the simulation emitter intact. Custom
  edits inside that visible node tree are replaced; duplicate the scene first
  if you want to retain them. Legacy emitters still use the existing rebuild path.
- Resolution and preset changes perform one whitewater application. Size edits
  change particle render size only after adoption. Wave Period edits change
  the wave maker's timing and strength (or an old tank's paddle timing and
  subframes) without rebuilding tank geometry or whitewater. Calm's 0.12 m
  waves need resolution 200 (about 2× the bake time of 160) to travel.
- **Generation Budget** caps shared whitewater generation (re-bake required).
  Zero suspends all elements without losing their choices. Default 1 preserves
  previous settings. Amount remains a relative visual density: unequal amounts
  still use shader thinning, not per-element removal from the simulation cache.
  Full-density elements bypass the transparency mix and use constant AOV masks.
  This is not a replacement particle renderer and does not promise proportional
  simulation savings for each individual Amount slider.
- Newly enabled secondary systems inherit Preview. Orphan cleanup visits only
  settings removed by the current toggle; unchanged values avoid repeat writes.
- Preset snapshots use a bounded decoded cache and relevant-ID checks; panel
  drawing reads the modified flag. Undo, redo and file load clear the cache.
- Buoy FIR smoothing uses equivalent cached amplitude/phase coefficients,
  reducing four temporal wave samples to one. Cache size is capped at 256.
- The UI distinguishes grid-only memory from an explicitly uncalibrated liquid
  planning range. That range includes mesh-grid and secondary allowances; scene
  totals feed the bake warning. Other geometry, render buffers, GPU allocations
  and Blender overhead are excluded. It is not a measured peak-memory bound.

## Verification and remaining review

Pure-Python checks compare buoy output against the previous FIR implementation
at 1,500 randomized samples, plus zero-speed/zero-smoothing and cache bounds.
Focused background-Blender checks cover update counts, particle settings,
Preview isolation, shader routing, native preset edits, registration within
RestrictBlend and existing regression cases. No bakes or renders are run here.

For visual review: compare Rain Sim in Preview/Final and a final render; test
Optimize Visible Rain on a copy of an old setup; compare whitewater budgets at
equal resolution; inspect all AOVs and compare wave period changes. Measure
peak RAM/VRAM and bake/render time on the same scene before claiming speedups.

Restart Blender before installing over an enabled older build, to avoid stale
Python modules from the previous version. Use aquasuite-0.18.0.zip.
