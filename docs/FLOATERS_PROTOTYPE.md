# Floating objects in the liquid modes — prototype findings

> **Shipped in 0.21.0** as Floating Objects (`core/floating.py`), following §7.
> Differences from §7: the panel promises no Esc for the coupled bake (a
> blocking bake processes no window events; untested in the UI), it only
> says Blender is busy; Free Bake and
> Delete Assembly clear floater keys through `aquasuite.free_liquid` and
> `delete_assembly`; Ocean (Simulated) floaters use the depth decay of §2.3
> (heave/wave 1.28–1.31 → 1.22–1.28 on the same bake — not the fix for the
> over-response, which is mostly resonance).

Prototype for mass-based floating objects in AquaSuite's Mantaflow liquid
modes (Still Water, Ocean (Simulated); the same code reads any liquid
domain), including a hybrid "floater + water obstacle" that pushes water.
Code: `level2/floaters.py` (no UI, not registered), a small refactor in
`core/obstacles.py` (`add_fluid_effector`), tests in `tests/test_floaters.py`.
Built from master `cc0b02e` (0.20.0). Every number below is **Blender 4.5.4
LTS** unless it says otherwise. Spot checks on **5.2.2 LTS** gave identical
results: the bakes are bit-identical and so are the floater numbers. The
machine was running other Blender jobs during some runs, so timings are
indicative (±15%).

## Summary

- **One-way floaters work and are cheap.** On a baked Still Water tank,
  wood floats 60.0% submerged, ice 91.7%, and steel sinks in 0.67 s and rests
  on the floor. Floaters settle in 1.4–3 s with under 1 mm of residual bob.
  The cost is 2 ms per object per frame plus 50–130 ms per frame to read the
  liquid mesh. Results barely depend on the grid (4 to 16 cells across the
  object).
- **In waves the motion is plausible but over-responsive.** A wood box in
  Rolling Waves heaves 1.3× the local wave height and pitches 1.35–1.5× the
  wave slope. It drifts 0.1–0.75 m over 30 s.
- **"Pushes water" works only partly.** As an effector, a floater makes real
  splashes and wakes (31–46 mm ring waves against 6–8 mm without). But
  Mantaflow **deletes** water inside a moving or newly placed obstacle instead
  of displacing it, so the water level never rises:
  - the water level moves −0.7 mm against the ideal +9 mm;
  - a 0.3 m drop loses 0.72% of the tank's water;
  - with fractions on it loses 10.8%.
- **Frame-by-frame coupling is feasible, without the pause/resume cache.**
  Blender calls `frame_change_pre` before every frame of a blocking
  (EXEC) bake, after the previous frame's liquid mesh is on disk. A handler
  can read that mesh, move the floaters, and let the solver see the new pose
  in the same bake. That gives two-way coupling in **one** bake. The cost:
  - +8% over a two-pass re-bake for the drift;
  - ×1.15 over the plain bake for the 720-frame Rolling Waves tank.

  The pause/resume route works but costs 3.3–3.7× a normal bake.
- **One trap decides whether the coupled effector pushes or deletes water:**
  during the bake the handler must write the new pose into pre-created
  keyframe points. Writing to the object itself (its location, or
  `keyframe_insert`) makes Mantaflow see a teleporting obstacle: it moves
  without velocity and deletes the water it enters. For the same motion the
  object write loses 0.84% of the water, while editing the keys gains +0.04%.
- **Recommendation:** ship one-way **Bake Floaters** first. Ship "Pushes
  water" as the **coupled single bake** (blocking, with progress), not as two
  passes. Document that it makes splashes and wakes but no level rise. Keep
  fractions off. Plane Ocean's analytic floaters should take a density and
  derive their Buoyancy Offset from it (`floaters.buoy_offset`).

## 1. What the prototype does

`floaters.Body(obj, density | mass)`:
- Rejects open meshes and parented objects (`eligible`).
- Gets the mass from density × mesh volume (`bmesh.calc_volume` with the
  object's scale) unless a mass override is given.
- Fills the closed mesh with 1,000–1,800 sample points (10 layers across the
  smallest dimension; inside-test by vertical ray parity).
- Takes the centre of mass and inertia tensor from those points (within 5% of
  the box formula), and uses up to 400 hull vertices for contacts.

Per frame (`floaters.bake`, one-way), with 8 fixed substeps:
- **Water line:** a ring of 12 vertical probes at the object's footprint plus
  2 cells, fitted with a plane (height, slope). Each probe takes the top of the
  thickest liquid column, so droplets above are ignored. A ring is used because
  an object that pushes water leaves a hole in the liquid mesh: probing under
  it finds the hull, not the water line. The plane is interpolated between
  frames over the substeps.
- **Buoyancy:** each sample point is a slab one layer thick; its submerged
  share is `clip((h − z)/layer + ½)`. That makes the force smooth rather than
  stepping layer by layer. Force ρ_w·g·V_i·(−h_x, −h_y, 1): it follows the local
  slope (Froude–Krylov), so floaters slide down wave faces. Torque about the
  centre of mass comes from the same point forces, so the centre-of-buoyancy
  offset turns the object.
- **Drag:** per submerged point, −ρ_w·V_i·(k_lin + k_quad·|v_rel|/L)·v_rel,
  relative to the water velocity, with k_lin = 5 s⁻¹ and k_quad = 0.5.
  Angular drag follows from the point velocities.
- **Added mass:** 0.5 × the displaced water mass, scaling linear and angular
  inertia.
- **Contacts:** floor and four walls at the domain's inner bounds, inset one
  cell because Mantaflow keeps a one-cell obstacle border. Impulse-based, with
  restitution 0.2 (0 below 0.3 m/s) and friction 0.5.
- **Output:** one LINEAR key per frame on location and rotation (keeping the
  user's rotation mode, euler-continuous). They go in an `AQS_Float_<name>`
  action tagged `aqs_owner = "FLOAT:<name>"`. The pre-bake transform and the
  user's own action are recorded (`aqs_floater_restore`,
  `aqs_floater_prev_action`); `floaters.clear` restores both.

**Water velocity.** The liquid mesh's speed vectors were useless in the
add-on's MODULAR / BOBJECT bakes with `use_speed_vectors` on:
- Ocean: the `velocity` attribute was all zeros.
- Still Water: the attribute was absent; there are no mesh-velocity files in the
  cache.

So the drag uses the water line's own vertical speed, taken from consecutive
frames. Horizontal water velocity could come from the `velocity` grid in the
data `.vdb` (Blender bundles the `openvdb` module on 4.5 and 5.2); that's not
done here.

## 2. Phase 1 — one-way floaters

### 2.1 Still Water validation

Test tank: a 3 × 3 × 1 m water block, domain 3 × 3 × 2 m (bottom at the
block's bottom), preset Calm Pour, 144 frames at 24 fps. At resolution 96 a
cell is 3.1 cm, so a 0.5 m cube spans 16 cells. The 1 m block settles at
1.016 m (resolution 96), 1.031 m (48) or 1.061 m (24): the cells of the
domain border change how much of the source becomes water. Objects start with
their bottom touching the water at rest.

| Object (0.5 m cube unless noted) | Density | Submerged volume | Draft (vertical, level objects) | Tilt at 6 s | Settle (±1 cm) | Bob, last 1 s (peak to peak) |
|---|---|---|---|---|---|---|
| Wood plank 0.5 × 0.5 × 0.2 m | 600 | **60.0%** | **60.5%** | 0.2° | 1.4 s | 0.6 mm |
| Ice | 917 | **91.8%** | **91.7%** | 0.0° | 3.0 s | 0.8 mm |
| Steel | 7800 | 100% — hits the floor at **0.67 s**, rests on it (bottom = floor to < 1 mm) | — | 0.0° | 0.67 s | 0.2 mm |
| Wood cube, level start | 600 | 60.3% | (tilted) | 29° (still rolling) | 2.25 s | 4.1 mm |
| Wood cube, 5° start | 600 | 60.0% | (tilted) | **55°** | 2.5 s | 0.8 mm |

All targets are met: wood 60% ±10% and ice 92%; steel sinks and rests.
**The wood cube tips over, which is correct physics.** An upright cube of
relative density 0.6 has negative metacentric height (BM = a²/12d = 0.069 m
< BG = 0.10 m), so it rolls. From a 5° start it settles at 55°, with its body
diagonal close to vertical (corner down). That is a check that the torque
from the centre of buoyancy is right. The plank (B/D = 2.5) is stable level
and gives the clean 60% draft.

**Damping.** With k_lin = 2.5 s⁻¹ (damping ratio about 0.18), ice took 4.6 s
to settle and still bobbed 16 mm peak to peak at 5–6 s; wood took 5.0 s and
bobbed 15 mm. With k_lin = 5 (the default) the figures are those in the table.
In this one-way model, drag is the only damping: there is no wave radiation.
k_lin is the user-facing "water drag" if one is ever exposed.

### 2.2 Cells per object

Same tank and objects, k_lin = 5:

| Resolution | Cell | Cells across 0.5 m | Plank submerged / draft | Ice submerged | Steel on floor | Surface read per frame |
|---|---|---|---|---|---|---|
| 24 | 12.5 cm | 4 | 60.0% / 60.1% | 91.3% | 0.67 s | 14 ms |
| 48 | 6.25 cm | 8 | 60.0% / 60.0% | 91.7% | 0.67 s | 35 ms |
| 96 | 3.1 cm | 16 | 60.0% / 60.5% | 91.8% | 0.67 s | 127 ms |

One-way floating barely depends on resolution, because the water ignores the
object. The resolution matters only for how smooth the surface is (still-water
ripple ±3 mm at 96) and for the probe ring near walls: at resolution 24 the
2-cell gap is 25 cm, and a probe can land in the wall meniscus. The
"≥ 5 cells" rule matters for objects that **push** water (§3).

### 2.3 Ocean (Simulated), Rolling Waves

The tank is the preset's 20 × 8 × 4 m at resolution 160 (12.5 cm cells), with
a 720-frame bake (30 s; 345 s of baking). The floaters are wood (600):
- BoxA and BoxB: 1.0 × 0.6 × 0.4 m, at x = −4 and x = 0;
- CubeC: a 0.5 m cube at (0, 2).

Heave is crest-to-trough of the centre of mass per wave period (2.4 s). Wave
is crest-to-trough of the water line at the object. Both are averaged over the
last 3 periods (24–30 s):

| Object | Wave at object | Heave | Heave / wave | Pitch (peak to peak) | Wave slope (peak to peak) | Pitch / slope | Drift in 30 s |
|---|---|---|---|---|---|---|---|
| BoxA (x = −4) | 0.289 m | 0.370 m | 1.28 | 29.4° | 19.2° | 1.53 | +0.13 m |
| BoxB (x = 0) | 0.271 m | 0.350 m | 1.29 | 19.8° | 12.9° | 1.53 | +0.42 m |
| CubeC | 0.246 m | 0.322 m | 1.31 | 19.2° | 14.3° | 1.35 | +0.75 m |

At 12 s, BoxA heaved 0.43 m in a 0.35 m local wave. All three floated at
59–60% submerged on average. The boxes clearly ride and pitch with the waves
and drift slowly down-wave.
**The response is about 30% too large.** The box's heave natural period
(~1.2 s with added mass) is half the wave period. A spring–mass driven by the
full surface elevation then amplifies 1/(1 − ¼) = 1.33 in linear theory, and
that is what was measured. Real floaters respond less, because wave pressure
decays with depth (the Smith effect). Before the drag used the water's
vertical speed, the ratios were 1.23 / 1.48. A depth-decay factor e^(−k·depth)
on the per-point buoyancy would fix this; it needs a wave number, which a
Simulated Ocean tank knows (`simulated_ocean.wave_number`).

### 2.4 Runtime

Per object per frame, the dynamics take **1.8–2.5 ms** at 8 substeps and
1,000–1,800 points. Reading the liquid surface is the main cost:

| Liquid mesh | `frame_set` | Mesh to numpy + BVH of the region near the floaters | Read the `.bobj.gz` cache file directly instead |
|---|---|---|---|
| Still Water, res 96 (119k verts) | 52 ms | 74 ms | 56 ms |

- **Still Water, res 96, 5 objects:** 127 ms/frame for the surface plus
  1.8 ms/object. Before the BVH was limited to the region around the floaters,
  the surface took 262 ms/frame.
- **Ocean, res 160, 115k verts, 3 objects:** 109 ms/frame in total
  (53 ms surface).
- **720 frames, 3 floaters:** about 80 s.

This is tiny next to the liquid bake (0.5–0.7 s/frame for this Still Water
tank, 0.48 s/frame for the ocean).

## 3. Phase 2a — two-pass "pushes water"

Method:
1. **Pass 1:** bake the water, float the object (one-way), and key it.
2. **Pass 2:** give the object a collision Fluid effector,
   `floaters.set_pushes_water`. The effector is marked `aqs_floater_effector`,
   not `aqs_obstacle`, so `obstacles.sync` leaves it alone; surface distance is
   0, because any thickness displaces surface area × distance more water.
   Re-bake the water with the pass-1 keys, then float again on the new water.
3. **Pass 3:** repeat pass 2 with the pass-2 keys.

Each pass bakes into its own cache folder (see §5 for why), so pass 1's
cache survives.

Metrics are on the same 3 × 3 m tank at resolution 96 (16 cells per 0.5 m),
over 6 s:
- **Water volume:** signed volume of the liquid mesh. The mesh excludes the
  obstacle, so this is the liquid volume.
- **Far-field level:** the mean water line 1.05–1.4 m from the centre.
- **Splash:** the highest water line 0.42–0.75 m from the object in the first
  2 s, above the rest level.
- **Penetration:** the share of the object's submerged sample points that are
  still inside the liquid mesh (pass 1: 100%).

**Drop:** a wood cube (75 kg) dropped from 0.3 m above the water, landing at
2.4 m/s.

| | Pass 1 (no effector) | Pass 2 | Pass 3 | Pass 2, fractions on |
|---|---|---|---|---|
| Water volume, frame 1 → 144 | +0.09% | **−0.72%** | −0.79% | **−10.8%** |
| Far-field level vs pass 1 (ideal **+9.0 mm** = 0.075 m³ / 8.38 m²) | — | **−0.7 mm** | −1.3 mm | −96 mm |
| Splash peak (rest + …) | 8 mm (ripple) | **31 mm** | 31 mm | 67 mm |
| Penetration | 100% | 7.8% | 6.7% | 1.6% |
| Bake time vs pass 1 | 83 s | ×1.40 | ×1.37 | ×1.59 |
| Floater vs previous pass (centre of mass, RMS / max) | — | 29 / 39 mm | **10 / 16 mm** | — |
| Floater submerged / settle / tilt | 60.0% / 2.75 s / 56° | 60.1% / 3.7 s / 52° | 60.0% / 2.7 s / 52° | 60.3% / 4.8 s / 46° |

**Drift:** a wood plank (30 kg) floating at rest, pushed at 1 m/s along x.
Drag stops it after about 0.3 m.

| | Pass 1 | Pass 2 |
|---|---|---|
| Water volume at frame 1 vs pass 1 | — | **−0.25%** (water under the start pose deleted) |
| Water volume, frame 1 → 144 | +0.09% | +0.02% |
| Far-field level vs pass 1 (ideal **+3.6 mm**) | — | −0.6 mm |
| Wake peak 0.42–0.75 m from the plank | 5.7 mm | **40 mm** (bow wave in the first 0.5 s) |
| Floater vs pass 1 | — | 14 mm RMS (mostly horizontal), 2.9 mm RMS in z |
| Bake time | 88 s | ×1.18 |

**What the water does.**
- **It is excluded, not displaced.** Only 7–8% of the submerged points stay
  inside the liquid, and they sit at the boundary cells.
- **The level does not rise.** Mantaflow deletes liquid that ends up inside an
  obstacle, including the water under an object placed in it at frame 1. It
  does not push that water out, so the level never rises.
- **The drop's lost volume (0.062 m³) is 83% of the submerged volume.** Water
  is lost at impact (−0.44% in the first second) and then slowly while the
  cube rolls (−0.3% over 5 s).
- **Splash and wake are real.** The obstacle's velocity does reach the
  liquid: the drop throws a ring wave 4× the ripple, and the drifting plank
  pushes a 40 mm bow wave.
- **Fractions make it far worse.** Fractions-on is S020's "moving obstacle
  swallows liquid" at a larger scale (−10.8%, level −96 mm). Rejected again.

**Coarser grid: resolution 48 (8 cells per 0.5 m), same drop.** The
results were the same on 4.5 and 5.2: water volumes matched to 10 digits.

| | Pass 2 | Pass 3 | Coupled (§4.2) |
|---|---|---|---|
| Water volume, frame 1 → 144 | −0.42% | −0.42% | −0.37% |
| Far-field level vs pass 1 (ideal +9.4 mm) | +2.3 mm | +2.1 mm | +2.6 mm |
| Splash peak (pass 1: 1 mm) | 34 mm | 35 mm | 34 mm |
| Bake vs pass 1 (14.3 s) | ×1.25 | ×1.23 | ×1.49 |
| Floater vs previous pass (RMS / in z) | 58 / 15 mm | 40 / 3 mm | 26 / 5 mm vs pass 2 |

On the coarser grid a quarter of the displaced water does show up as a level
rise, and less is lost (−0.42% against −0.72% at resolution 96). The
cube's horizontal path still differs by 40 mm between passes 2 and 3. A cube
that rolls over is sensitive to small changes; its height path converges
(3 mm RMS).

**Volume budget (limit 1%).**
- Two-pass with fractions off stays within 1%: −0.72% / −0.79% for the
  drop, +0.02% for the drift (−0.25% from the start pose).
- Fractions on is ten times over.
- **Effector subframes 4 doesn't help.** It loses −0.71% (pass 2) and −0.67%
  (coupled) against −0.72% / −0.69% with 0 subframes, gives the same 31 mm
  splash, and makes the bake slower (×1.47 against ×1.40). Keep subframes at
  0.

**Convergence.** Pass 1 → 2 changes the cube's path by 29 mm RMS; pass 2 → 3
by 10 mm. The water barely changes between passes 2 and 3: same volume loss,
same splash. Two passes converge for practical purposes, and a third pass is
not worth its bake. The change is small to begin with because the water level
doesn't rise. All the second pass adds is local waves and the meniscus around
the object.

## 4. Phase 2b — frame-by-frame coupling

### 4.1 Pause/resume cache (`cache_frame_pause_data`, MODULAR)

This works. With `cache_resumable` on, set `cache_frame_end = f` and call
`fluid.bake_data`: it resumes at the pause frame (`cache_frame_pause_data`
advances 11, 12, 13, …) and bakes one more frame. Then `fluid.bake_mesh`
meshes it (it resumes too), and `frame_set(f)` reads it. Twenty stepped
frames matched the continuous bake: liquid volume 8.6227 vs 8.6227 m³, 118,470
vs 118,472 verts, top surface within 0.2 mm. The ocean matched as well (below).

Cost on the 3 × 3 × 2 m tank at resolution 96:

| | Per frame |
|---|---|
| Continuous `bake_all` | 0.67 s |
| Stepped: resume `bake_data` + `bake_mesh` + read | 0.96 + 0.92 + 0.29 = **2.18 s** (3.3×) |

| Rolling Waves ocean, resolution 160 (12 stepped frames) | Per frame |
|---|---|
| Continuous `bake_all` | 0.47 s |
| Stepped | 0.68 + 0.77 + 0.28 = **1.72 s** (3.7×); volume 322.294 vs 322.296 m³ |

Every call re-initialises Mantaflow and reloads the previous frame. A
720-frame bake would take 26 min instead of 8 for the Still Water tank, and
21 min instead of 5.6 for the ocean. **Feasible, but impractical for shipping.** It is still the only
way to couple without blocking the UI: each step is a short bake that could
run in a modal timer.

### 4.2 Coupling inside one bake (recommended)

Blender's bake loop runs `frame_change_pre` handlers for every frame. That is
verified on 4.5 and 5.2 with EXEC bakes; headless bakes always run EXEC. At
that moment `fluid_mesh_<f−1>.bobj.gz` is already written; it is readable
with gzip + numpy, in domain-unit coordinates × the domain's largest
dimension (verified exactly against the evaluated mesh). `floaters.CoupledBake`:

1. Before the bake, keys every frame of the cache range at the start pose
   (LINEAR) and adds a `frame_change_pre` handler.
2. In the handler for frame f, it reads the f−1 mesh, probes the water line,
   advances the floaters one frame, and **edits the key values of frame f**.
3. Mantaflow then evaluates the effector at the new pose, with a velocity
   from the keys.

The floater is one frame ahead of the water it sees. That is the usual lag of
a sequential fluid/rigid scheme; it is harmless at 24 fps.

**The trap.** Writing to the object during the bake breaks the effector:
setting `obj.location`, or `keyframe_insert` even with the value unchanged.
Mantaflow then treats it as moved without velocity, and it deletes the water
it enters. A plunger moving down 1 m/s into the res-48 tank shows it:

| How the motion was keyed | Volume after 2 s | Splash peak |
|---|---|---|
| All keys before the bake | +0.04% | 46 mm |
| Same keys + a handler that does nothing | +0.04% | 46 mm |
| Same keys + handler sets `obj.location` (same value) | **−0.84%** | 28 mm |
| Same keys + handler re-inserts the same key | **−0.84%** | 28 mm |
| `keyframe_insert` of the real value live (also with the next key ahead) | **−0.84%** | 28 mm |
| Placeholder keys before the bake, handler edits `keyframe_points[f]` | **+0.04%** | 46 mm |

The last row is bit-identical to the first.

Results, same tank as §3, resolution 96:

| | Drift: two-pass (pass 2) | Drift: coupled | Drop: two-pass (pass 2) | Drop: coupled |
|---|---|---|---|---|
| Bake time | 104.5 s | 113.0 s (+8%) | 116 s | 117 s (×1.29 its own pass 1) |
| Handler per frame | — | 52 ms (51 surface + 2 dynamics) | — | 54 ms |
| Water volume, frame 1 → 144 | +0.02% | **+0.004%** | −0.72% | **−0.69%** |
| Far-field level vs pass 1 (ideal +9 mm / +3.6 mm) | −0.6 mm | −0.6 mm | −0.7 mm | −0.3 mm |
| Wake / splash peak | 40 mm | 40 mm | 31 mm | 31 mm |
| Floater vs two-pass (centre of mass RMS) | — | 2.0 mm | — | 11 mm (z 8 mm) |

Resolution 48 gave the same picture on both Blender versions: coupled
−0.37% against two-pass −0.42%, the same 34 mm splash, and a 19 ms handler
(§3).

The coupled drop is the two-pass result but from one bake: the same volume
loss, splash and level. The floater differs from pass 2 by about as much as
pass 3 does (10 mm). The two-pass bakes ran while the machine was busier, so
the bake-time ratio is the fairer figure. The first coupled drop, which wrote
to the object live, lost **1.83%** with no splash at all. That is what exposed
the trap.

**Projection for a 720-frame bake.** The coupled bake costs the effector
(×1.2–1.4 bake time, also paid by two-pass) plus 50–65 ms/frame for the
handler (+8–12%). Two-pass costs two full liquid bakes.

**Rolling Waves, coupled, all three wood bodies pushing water:**
- **Bake:** the 720-frame res-160 coupled bake took **398 s**, against 345 s
  for the plain bake (×1.15). The handler took 49 ms/frame (42 ms surface,
  2.2 ms per body).
- **Volume:** the water volume rose +0.19% from frame 1 to 720, against
  +0.42% in the plain bake. The water under the start poses deleted at frame 1
  was −0.05%.
- **Motion:** the floater motion barely changed:

| Body | Heave / wave (one-way → coupled) | Pitch / slope | Drift in 30 s |
|---|---|---|---|
| BoxA | 1.28 → 1.29 | 1.53 → 1.55 | 0.13 → 0.40 m |
| BoxB | 1.29 → 1.37 | 1.53 → 1.51 | 0.42 → 0.52 m |
| CubeC | 1.31 → 1.36 | 1.35 → 1.17 | 0.75 → 0.77 m |

So the coupled bake is safe in waves (volume well inside 1%) and affordable.
It does not fix the over-response: the boxes are small next to a 0.45 m,
2.4 s wave. The local wave height at BoxB dropped from 0.27 to 0.21 m, a sign
that the water does feel the boxes, though the ring probe may see some of the
boxes' own disturbance.

**Limits of the coupled bake.**
- **It must be a blocking (EXEC) bake.** The add-on's UI bake is INVOKE (a job
  thread). There, Python handlers would run on the worker thread: not tested,
  and not safe.
- **Starting from a cache:** a re-bake into a cache folder that already holds
  files must not read stale meshes. The handler checks file times.

## 5. Blender problems found on the way

1. **Free Bake then Bake crashes Blender 4.5 headless.**
   - The crash is `EXCEPTION_ACCESS_VIOLATION` in `MANTA::initLiquid` /
     `MANTA::parseLine`, when the domain is re-evaluated after `fluid.free_all`.
   - It happens with no floaters, and with the add-on's own
     `aquasuite.free_fluid` operator too.
   - Blender 5.2 is fine.
   - Hiding the domain's Fluid modifier around `free_all` avoids it in simple
     cases, but not after `use_fractions` was written (point 2).
   - What worked every time: point the domain at a new cache folder, reset
     `cache_frame_pause_*` to 0 and `has_cache_baked_*` to False, then bake.
     Without the pause reset, the bake "resumes" at the last frame and writes
     only that frame.
   - Untested in the 4.5 UI. See follow-ups.
2. **Writing `use_fractions` after a bake, even the same value, breaks the
   next bake on 4.5.** Mantaflow script errors (`name 's5' is not defined`),
   then a crash.
3. **Speed vectors: no mesh velocities** in the add-on's MODULAR/BOBJECT
   bakes (§1).

## 6. Limits of the prototype

- The water line is a plane through a ring of probes. That's fine while the
  object is smaller than about ¼ of a wavelength; it misses short chop. Objects
  wider than the tank's gaps, or touching a wall, get probes clamped to the wall.
- **No pressure decay with depth:** about 30% too much heave and pitch in waves
  (§2.3).
- **No floater–floater collisions;** contacts are only against the domain's
  inner box. Water Obstacles are not collided with.
- One-way floaters don't disturb the water. Objects that push water delete
  water rather than raise the level (§3); that is a Mantaflow limit, not
  fixable here.
- The domain must be an unrotated box (true for every AquaSuite domain). Each
  floater object must be closed and unparented, and its keys replace its
  location and rotation animation while floating.
- The coupled bake needs a blocking bake.

## 7. Recommended design

**Scene collection "AQS Floating Objects".** It mirrors Water Obstacles: one
collection per scene, and membership is the rule. Adding an object checks
`floaters.eligible` (closed mesh, no parent, not an AquaSuite part or water
source, not in Water Obstacles). Removing it, by button or by unlinking it in
the Outliner (depsgraph sync like `obstacles._on_depsgraph`), runs
`floaters.clear`: the keys go, and the user's action and transform come back.
Floaters and Water Obstacles are mutually exclusive: an obstacle's effector is
static geometry, and the scene-wide `obstacles.sync` must never see a floater.
`floaters.set_pushes_water` uses its own mark for exactly that reason.

**Per-object settings** (a PropertyGroup on Object, stored on the user's
object like the obstacle mark):
- **Material:** a preset that fills the density.
  `DENSITY_PRESETS`: Foam 100, Cork 240, Wood 600, Oak 750, Ice 917,
  Plastic 950, Rubber 1100, Concrete 2400, Steel 7800, Custom.
- **Density** in kg/m³, and a **Mass override** (a checkbox + kg). Show the
  computed mass and "floats ~60% submerged / sinks" next to it.
- **Pushes water**, off by default.
- Water drag (k_lin) stays internal at 5 unless users ask for it.

**Bake Floaters**, in each liquid setup's panel (Still Water, Ocean
(Simulated); Rain Sim and the hose work the same way):
- **Enabled when the liquid is baked.** It runs `floaters.bake` over the cache
  range with a progress bar (about 2 ms per object plus ~100 ms per frame:
  80 s for 720 frames).
- **Clear Floaters** restores every object. Deleting the liquid setup or
  freeing its bake also clears its floaters' keys: the keys belong to that
  water.
- **Warnings:** an object outside the domain, an open mesh, and an object
  smaller than about 5 cells when "Pushes water" is on.

**Which hybrid to ship.**
- **"Pushes water" uses the coupled single bake.** When any floater in the
  domain has Pushes water on, Bake runs `CoupledBake` around a blocking
  `bake_all`, keyed as in §4.2.
- **The water and the floaters come from one bake.** It costs 50 ms/frame
  for the handler on top of the effector. That came to ×1.15 for 720 frames
  of Rolling Waves and ×1.29 for the Still Water drop, both against a plain
  bake. Two-pass needs two full bakes and a
  second floater pass; the result matched within 2 mm RMS.
- **The panel should be honest about what it does:** "Pushed water splashes
  and makes wakes, but the water level does not rise — Mantaflow removes the
  water inside the object."
- **Keep fractions off.**
- **Re-bake into a fresh cache folder**, not free-then-bake (§5). That also
  keeps the plain bake available.
- **Accept the blocking bake for this mode,** stating "Blender is busy until
  the bake finishes; Esc cancels". Moving to a resumable modal stepper (§4.1,
  3.3× slower) is the fallback if blocking is unacceptable.
- **Two-pass stays a manual workflow:** Bake Floaters, then turn on Pushes
  water and bake. Passes beyond two don't pay (§3).

**Density for Plane Ocean's analytic floaters.** Keep them massless and
closed-form (farm-safe), but add the same Material/Density field to Attach
Floater. Set the buoy's existing **Buoyancy Offset** from it:
- `floaters.buoy_offset(obj, density)` finds the static waterline of the
  closed mesh at that density. It bisects the submerged share of the sample
  points; for a 0.5 m cube, wood gives −0.05 m and ice −0.21 m, exact.
- Densities ≥ 1000 return None: refuse those ("sinks — use a liquid mode").
- Bob Smoothing could also follow the size (a natural period of
  2π√((m + m_a)/(ρ g A_wp)) is available from the same mass and footprint).
  Not done.

## 8. Tests

`tests/test_floaters.py`:
- **Fast checks (4.5 and 5.2, 16/16):**
  - mass = density × volume, with scale, and a mass override;
  - inertia within 5% of the box formula;
  - an open mesh is rejected;
  - on a synthetic flat water box: plank, ice and cork float at their density
    ±3%, the plank settles, and steel rests on the floor;
  - a level wood cube tips (> 20°);
  - `buoy_offset` (wood −0.05, ice −0.2085, steel None);
  - keys go in their own action, and clearing restores the user's action and
    transform;
  - the Pushes water effector survives `obstacles.sync` and is removed cleanly.
- **Bake-gated (`--bake`):** a resolution-48 Still Water tank, 120 frames:
  plank 54–66% submerged, ice 87–97%, steel on the floor, all keyed, all
  cleared. It passes on 4.5 and 5.2 (21/21 checks each, 41 s for both). The
  floaters cost 29–32 ms/frame for 3 objects on a 28k-vert liquid mesh.

The hybrid is not under test: its numbers (§3–4) are measurements for this
report, not guarantees to lock in.

## 9. Follow-ups

- Free Bake → Bake crashes headless Blender 4.5 (§5.1). Check the 4.5 UI path
  and switch AquaSuite's re-bake to a fresh cache folder if it crashes there
  too.
- Pressure decay with depth for floaters in waves (§2.3).
- Horizontal water velocity from the data `.vdb` velocity grid (§1).
