# REQ-003 implementation review — 2026-10-18

Scope: changes from `c8939f5` across six implementation slices, reviewed by the
implementing agent. This is a local code review, not an independent reviewer or
an in-app UI/visual acceptance session.

## Findings addressed

- Demo context isolation: scene/view-layer overrides alone did not guarantee the
  active object used by Attach Floater. An explicit object override prevents
  constraints from being added to the user's active object. Regression checks
  compare original-scene constraints and verify the demo owns its floater.
- Failed demo rollback: referenced materials/node groups could survive a single
  cleanup pass. Sweep only newly created IDs until no further orphan IDs are
  released. Tests compare all relevant datablock collections before/after failure.
- Panel specification drift: remove the unreachable old per-mode drawing path;
  all modes use the shared control specification. Remove duplicate Still Water
  resolution buttons and disable settings groups while a bake is running.
- Refraction scope: apply version-compatible refraction flags only to generated
  water, droplet and whitewater materials, not every material in the library.
- Restore coverage: test EEVEE settings, enabled Cycles bounce settings, None
  worlds, duplicate prevention, and failed Lighting creation rollback. Package
  tests now include all nine modes and require the new modules/control spec.

## Validation

The initial fast suite passed 364 checks with 0 failures and 10 skips across
Blender 5.1.2 and 4.1.1. Twelve low-resolution preset bakes passed on 5.1.2.
The post-review suite passed **372 checks, 0 failures, 10 skips** across both
versions. The runner
reports known 4.1 Mantaflow shutdown crashes after DONE as explicit configured
skips; those are not silently treated as ordinary successful exits.

Final packaging uses Blender's extension builder for `aquasuite-0.19.0.zip`.
Syntax, ZIP integrity, source consistency, and packaged-module presence were
checked. The package test registers and creates all nine modes from the ZIP.
The final Cancel Bake layout adjustment was inspected statically; panel/window
drawing remains part of the manual smoke gate.

## 0.19.1 fix pass — 2026-10-19

Done by an agent on Blender 4.5.x and 5.2.2 LTS (5.1 and 4.1 were not available), on top of
`54e172d`. Details and measurements are in [REMAINING_WORK.md](REMAINING_WORK.md).

- **P2 fixed:** deleting Water Lighting keeps a sky world that another scene,
  another registry or a fake user still uses, and drops its owner tag.
  Regression tests cover direct, reloaded and fake-user cases.
- **S020 diagnosed, partly fixed:** the late "decay" was the test sampling
  paddle slosh at different stroke phases. Storm Surf's settings were steeper
  than a real wave can be; the stroke now follows wavemaker theory, requests
  are capped below breaking, and Storm uses a 2.8 s period. The paddle still
  barely drives travelling waves in any preset (Mantaflow receives little or
  no paddle velocity); a body-force wavemaker is the recommended replacement.
- **Blender 5.2 compatibility:** on 5.2.2 LTS, Plane Ocean, Plane Rain and
  Rain Simulation failed to create (Geometry Nodes modifier inputs moved from
  ID properties to `mod.properties.inputs`; Random Value lost its per-type
  outputs). Fixed with version-agnostic accessors; full `--bake` suites pass
  on 5.2.2 (220/0/0) and 4.5 (219/0/1).
- **Packaging:** `dist/` is excluded from the extension build, so installers
  built inside the repo no longer get packed into the next one
  (`test_package` caught this).

## 0.20.0 wave maker — 2026-10-19

Done by an agent on Blender 4.5 (and the fast suite on 5.2.2). Details and
measurements are in [REMAINING_WORK.md](REMAINING_WORK.md) (S020, S023).

- **S020 wave generation fixed:** new Ocean (Simulated) tanks use a
  sine-driven Wind force field over a full-depth zone at the left wall, with
  its strength from linear surface-pressure wave theory and Blender's
  measured force scaling (0.2·strength·fps m/s²). Mid-tank heights reach
  0.14 / 0.40 / 0.94 m for Calm / Rolling / Storm (targets 0.12 / 0.45 /
  0.90 m) with volume within 0.13%. Calm's resolution rose to 200 because
  waves under one cell do not travel.
- **Old files:** paddle tanks keep the 0.19 paddle path; an Upgrade Wave
  Maker button replaces it on request.
- **S023 metric replaced:** the ocean bake test measures mid-tank wave height
  at fixed gauges over the last full period, wall height and volume.

## Open acceptance gates

- No in-app panel/window smoke test or Cycles/EEVEE visual render review has
  been performed here. Blender 4.2 specifically is not installed; 4.1 exercises
  the legacy API path but is below the extension's declared minimum version.
- S019–S021: user has no visual observations yet. Storm Surf's period, the
  wave maker (0.20.0) and Calm's resolution changed (physics, not taste);
  the ocean presets can now be reviewed and tuned.
- S023: passes on Blender 4.5 with the 0.20.0 mid-tank metric (see
  REMAINING_WORK.md); not accepted until its provisional thresholds are
  checked against renders (S019) and it is run on 5.1.
- S028: sessions with 3–5 beginners require real participants. Protocol and
  observation table are in RELEASE_CHECKLIST.md; no sessions are claimed.

These gates prevent calling REQ-003 launch-ready even though the implementation
preview is packaged for manual review.
