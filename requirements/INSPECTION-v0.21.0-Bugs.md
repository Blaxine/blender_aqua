# AquaSuite v0.21.0 inspection: bugs

Inspected on 2026-10-31, on `master` at `2249192`. No code was changed.

**Summary:** 12 bugs, 3 of them high priority. All automated tests pass, but those tests don't catch any of these. It isn't ready to sell yet: the three high-priority items need fixing first, and the release checks are still open.

## Status in 0.22.0

11 of the 12 bugs are fixed, each with a regression check in `tests/test_inspection_fixes.py`. The "Also delete bake files" box no longer stays ticked, by the same kind of fix, but that can't be checked without a window.

**Not fixed: the support link.** The owner decided to keep `Blaxine/blender_aqua` as the support link for 0.22.0. It works while that repo is public; it breaks if the repo is made private before the link is changed.

Still limited: a copied scene's setup shares its bake folder with the original, so baking or freeing in one affects the other. Delete with "Also delete bake files" keeps the files while a copy exists.

Not verifiable without a window: the Reactive Rain re-bake is checked by watching for the free that makes Blender bake again, because headless Dynamic Paint writes no frames.

The rest of this file is the inspection as written.

## Test results

| Run | Result |
| --- | ------ |
| Fast suite, Blender 5.1 and 4.1 | 710 passed, 0 failed, 24 skipped |
| Bake tests: liquids, free/re-bake, floating objects, whitewater (both Blenders) | 162 passed, 0 failed |
| Other bake tests, including per-preset and the long ocean bake | Not run |
| Checks in the real Blender window | Not run |

## Bugs

| Priority | Bug | Description | Fix | Description of the fix | How it was checked |
| -------- | --- | ----------- | --- | ---------------------- | ------------------ |
| **High** | Deleting in a copied scene destroys the original | Make a Full Copy of a scene, then delete a setup in the copy. The original's object disappears too, leaving its box pointing at nothing. Both copies share one ID, and Delete removes everything with that ID. | `core/delete.py:200` | Only delete objects in this scene's own setup collection, and give copied setups a new ID. | Reproduced in 5.1 |
| **High** | Simulated hose has no Bake button in Simple view | Turn on Simulate Liquid, then click Fewer Settings. The real-time jet is off, there's no Bake button, and no hint appears, so the hose looks broken. | `ui/control_spec.py:17` | Show Bake in Simple view whenever Simulate Liquid is on. | Read from the code |
| **High** | Support link will break for buyers | `Blaxine/blender_aqua` is still public and `Blaxine/aquasuite` doesn't exist. The app sends bug reports to the code repo, so that link dies when the repo is made private. | `constants.py:65` | Create the public repo and make the code repo private (owner tasks), then update the links. | Checked on GitHub |
| Medium | Deleting Water Lighting replaces your newer world | Add Water Lighting, switch to your own HDRI, then delete the lighting. Your HDRI is swapped for the old world. | `core/lighting.py:62` | Only restore the old world if the sky world is still the active one. | Reproduced in 5.1 |
| Medium | Reactive Rain's Bake Again does nothing | After changing Count, Bake Again finished in 0.00 s and Blender still treated the old bake as current. The panel has no Free button, so you can't re-bake from it. | `level1/rain_reactive.py:168` | Free the old bake first, and add a Free button. | Timed in 5.1 |
| Medium | Deleting a wave tank leaves the timeline longer | Creating a tank extends the timeline from 250 to 720 frames. Deleting the tank leaves it at 720, even though the tooltip promises a restore. | `level2/simulated_ocean.py:404` | Save the old end frame and restore it on delete, unless it has been changed since. | Reproduced in 5.1 |
| Medium | Rain and hose stop at the old timeline end | Extend the timeline to 1000 and rain and hose still stop emitting at frame 250. Snow and Reactive Rain set their range the same way, and creating a wave tank triggers this too. | `level3/hose.py:108`, `level1/rain.py:53` | Update emitter ranges when the scene range changes. | Rain and hose reproduced in 5.1; the rest read from the code |
| Medium | A Floating Object can also become water | Clicking Still Water on a floater succeeds, so it ends up as both. The Add Mesh button correctly refuses this, but Create skips that check. | `level2/still_water.py:485` | Use the same `source_problem` check in Create and in Add Pool. | Reproduced in 5.1; Add Pool read from the code |
| Low | Water Blast button just says "Water" | The hose buttons read Normal, Mist, Spray, Water, because the label is cut to its first word. | `ui/panel.py:516` | Use "Blast" as the label. | Label logic run in 5.1 |
| Low | Copy Report garbles words | With a file named `water.blend`, the report says `Mode: Still <blend-name>`. Hiding the file name replaces that word everywhere in the report. | `core/errors.py:106` | Only replace the name where it appears in a file path. | Reproduced in 5.1 |
| Low | Empty collection left after deleting a hose | Creating a hose adds "AQS Water Obstacles" to the scene, and it stays after the hose is deleted. | `level3/hose.py:92` | Create it only when needed, or remove it when it's empty and unused. | Reproduced in 5.1 |
| Low | Outdated text | The Rain Sim tooltip says "opens a setup menu" and Still Water mentions an "amber banner"; neither exists now. `docs/PRESET_REVIEW.md` still says 0.20.0. | `level2/rain_sim.py:661` | Update the wording. | Read from the code |

None of these has been seen in the real panel, because the checks ran without a Blender window.

## Still unknown

- **Do Reactive Rain ripples appear?** This can't be measured without a window: the measurement read zero, but so did a plain Blender test with no AquaSuite. No automated test covers it, so it has to be checked by eye; it's on the release checklist.
- **Does "Also delete bake files" stay ticked?** From how Blender handles operator settings, that box is expected to stay ticked for the next delete, which could remove bake files by accident. It needs a check in the real app (`ui/panel.py:21`).
- **Blender versions:** the add-on says it supports 4.2+, but this PC only has 3.0, 4.1 and 5.1. Docs mention earlier runs on 4.5 and 5.2 elsewhere, which can't be re-checked here.

## Still open before launch

- **REQ-003:** no acceptance criterion is ticked yet, and the visual review of presets and the beginner sessions haven't happened.
- **REQ-001:** making the repo private, creating the public issues repo and the final release checks are all still open.
