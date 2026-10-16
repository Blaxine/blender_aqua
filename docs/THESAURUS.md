# AquaSuite Thesaurus

The project's ubiquitous-language reference. Code, docs, panel text and
requirement plans use these terms with exactly these meanings. Add a term here
before introducing it anywhere else.

| Term | Definition | Notes |
| ---- | ---------- | ----- |
| Assembly | Everything one Create button builds: objects, meshes, node groups, particle settings, materials and collections, tracked as one unit. | Deleted as one unit by Delete Assembly. Users may rename every part. |
| Assembly entry | The registry record for one assembly in `Scene.aqs_assemblies` (`AQS_AssemblyEntry`): uuid, mode, primary object, root collection and per-mode settings. | Python references to entries go stale after any entry is removed; hold the uuid instead. |
| Base resolution | The user-chosen voxel resolution of a liquid assembly (`base_resolution`). | Draft halves it to get the effective resolution. |
| Buoy (floater) | A user object made to bob and tilt on an ocean through constraints to an AquaSuite empty driven by the buoy handler. | Deterministic: a pure function of position and time. |
| Delete Assembly | Teardown that restores tracked changes to user objects, releases effectors, then removes every ID carrying the assembly's owner tag. | Optionally removes the bake cache folder. |
| Domain | The Mantaflow fluid domain object of a liquid assembly. | Unrotated box; size it via `object_dims`, not `dimensions`. |
| Draft | Liquid quality switch: half resolution, 1× mesh, no secondary particles. | Hose and Rain Simulation. |
| Drop field | The Geometry Nodes tree that places Rain Simulation drops on their ballistic path from the emitter plane. | Shared by the emitter and the rain drops object. |
| Effector (refcounted) | A Fluid Effector modifier AquaSuite adds to a user mesh with Collision enabled, with an owner list of assembly uuids (`aqs_eff_owners`). | Removed when the last owning assembly is deleted. |
| Emission radius | The size of each drop the Rain Simulation emitter injects into the solver: at least ~0.75 voxel. | Smaller drops are invisible to Mantaflow. |
| Emitter (Rain Simulation) | The plane carrying the drop field in Emit Only mode plus the Fluid Flow that injects each drop in the frame before it hits the water. | Not rendered. |
| Fit Domain | Resizing a liquid domain to the region the liquid can reach. | Hose: the jet's path; Rain Simulation: water plus splash headroom. |
| Level 1 / 2 / 3 | Mode tiers: real-time surfaces and precipitation / liquid volume / directed emission. | Ocean, Rain, Reactive Rain, Snow / Still Water, Rain Simulation / Water Hose. |
| Mode | The kind of assembly: Plane Ocean, Plane Rain, Reactive Rain, Snow Plane, Still Water, Rain Simulation, Water Hose. | `MODE_*` constants. |
| Owner tag | The `aqs_owner` custom property `"<mode>:<uuid>"` on every ID an assembly created. | The only basis for deletion; never names. |
| Pool source | A user mesh added to a Rain Simulation as pool water. | Hidden, never converted, restored on delete. |
| Quality tier | Scene-wide Preview/Final switch that lowers particle display and ocean resolution non-destructively. | |
| Rain drops object | The rendered Rain Simulation rain: the full drop field at Drop Size, child of the emitter. | Unselectable. |
| Regime | The Water Hose flow type: Normal, Mist, Spray, Water Blast. | |
| Restore record | Saved pre-state of a user object AquaSuite changed (visibility, display type, constraints). | Applied by Delete Assembly. |
| Source marker | The `aqs_source_of` property marking a user mesh used as a liquid source. | Deliberately not the owner tag. |
| Water level | Where Rain Simulation rain meets water: top of the highest pool source, or z = 0 without pools. | |
| Wave table | The fixed Gerstner layer constants shared by the ocean node tree and the buoy handler. | Changing it changes every ocean. |
