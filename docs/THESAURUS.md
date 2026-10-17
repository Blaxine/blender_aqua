# AquaSuite Thesaurus

The project's ubiquitous-language reference. Code, docs, panel text and
requirement plans use these terms with exactly these meanings. Add a term here
before introducing it anywhere else.

| Term | Definition | Notes |
| ---- | ---------- | ----- |
| Add-on version | The AquaSuite release that created a setup, e.g. `1.0.0`; read from `blender_manifest.toml` and stored on each assembly entry. | For bug reports; upgrade decisions use the data version. |
| Assembly | Everything one Create button builds: objects, meshes, node groups, particle settings, materials and collections, tracked as one unit. | Deleted as one unit by Delete Assembly. Users may rename every part. |
| Assembly entry | The registry record for one assembly in `Scene.aqs_assemblies` (`AQS_AssemblyEntry`): uuid, mode, primary object, root collection and per-mode settings. | Python references to entries go stale after any entry is removed; hold the uuid instead. |
| Base resolution | The user-chosen voxel resolution of a liquid assembly (`base_resolution`). | Draft halves it to get the effective resolution. |
| Beta mode | Still Water and Rain Simulation (and the hose's Simulate Liquid): fully usable but bake-bound, slow and RAM-heavy at high resolution. | Labelled Beta in the panel; explained once per mode. |
| Bug report | Text copied by Copy Report: versions, OS, mode, plain message and traceback, with home folder and .blend path/name removed. | Pasted into public GitHub issues. |
| Buoy (floater) | A user object made to bob and tilt on an ocean through constraints to an AquaSuite empty driven by the buoy handler. | Deterministic: a pure function of position and time. |
| Data version | Integer on each assembly entry recording its saved-data layout: 0 = pre-release, 1 from 1.0. | Changes only when a mode's saved layout changes. |
| Deferred popup | The error popup for failures in sliders, the buoy handler or panel drawing, shown later by a timer. | Never during playback, rendering or headless runs. |
| Delete Assembly | Teardown that restores tracked changes to user objects, releases effectors, then removes every ID carrying the assembly's owner tag. | Optionally removes the bake cache folder. |
| Domain | The Mantaflow fluid domain object of a liquid assembly. | Unrotated box; size it via `object_dims`, not `dimensions`. |
| Draft | Liquid quality switch: half resolution, 1× mesh, no secondary particles. | Hose and Rain Simulation. |
| Drop field | The Geometry Nodes tree that places Rain Simulation drops on their ballistic path from the emitter plane. | Shared by the emitter and the rain drops object. |
| Effector | The Fluid Effector modifier AquaSuite adds to a Water Obstacle so baked liquid treats it as solid. | Pre-release files may still carry owner lists (`aqs_eff_owners`); Delete Assembly cleans those up. |
| Emission radius | The size of each drop the Rain Simulation emitter injects into the solver: at least ~0.75 voxel. | Smaller drops are invisible to Mantaflow. |
| Emitter (Rain Simulation) | The plane carrying the drop field in Emit Only mode plus the Fluid Flow that injects each drop in the frame before it hits the water. | Not rendered. |
| Fit Domain | Resizing a liquid domain to the region the liquid can reach. | Hose: the jet's path; Rain Simulation: water plus splash headroom. |
| Jet | The hose's real-time particle stream for Normal, Spray and Water Blast: droplets fired along the aim, under gravity, splashing on Water Obstacles. | Replaced by liquid when Simulate Liquid is on. |
| Level 1 / 2 / 3 | Mode tiers: real-time surfaces and precipitation / liquid volume / directed emission. | Ocean, Rain, Reactive Rain, Snow / Still Water, Rain Simulation / Water Hose. |
| Mode | The kind of assembly: Plane Ocean, Plane Rain, Reactive Rain, Snow Plane, Still Water, Rain Simulation, Water Hose. | `MODE_*` constants. |
| Owner tag | The `aqs_owner` custom property `"<mode>:<uuid>"` on every ID an assembly created. | The only basis for deletion; never names. |
| Pool source | A user mesh added to a Rain Simulation as pool water. | Hidden, never converted, restored on delete. |
| Pre-release setup | An assembly with data version 0 (made before 1.0). | Shows a notice; no compatibility promise. |
| Quality tier | Scene-wide Preview/Final switch that lowers particle display and ocean resolution non-destructively. | |
| Rain drops object | The rendered Rain Simulation rain: the full drop field at Drop Size, child of the emitter. | Unselectable. |
| Regime | The Water Hose flow type: Normal, Mist, Spray, Water Blast. | |
| Restore record | Saved pre-state of a user object AquaSuite changed (visibility, display type, constraints). | Applied by Delete Assembly. |
| Simulate Liquid | Per-hose Beta toggle that swaps the jet for a baked Mantaflow liquid. | Thicker than a real jet; needs a bake. |
| Source marker | The `aqs_source_of` property marking a user mesh used as a liquid source. | Deliberately not the owner tag. |
| Water Color | Per-hose tint of the jet droplets, mist and simulated liquid. | |
| Water level | Where Rain Simulation rain meets water: top of the highest pool source, or z = 0 without pools. | |
| Water Obstacles | The scene's `AQS Water Obstacles` collection: the only rule for what blocks water in every simulation. | AquaSuite adds Collision/Effector as needed and removes exactly that when an object leaves the collection. |
| Wave table | The fixed Gerstner layer constants shared by the ocean node tree and the buoy handler. | Changing it changes every ocean. |
