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

## Open acceptance gates

- No in-app panel/window smoke test or Cycles/EEVEE visual render review has
  been performed here. Blender 4.2 specifically is not installed; 4.1 exercises
  the legacy API path but is below the extension's declared minimum version.
- S019–S021: user has no visual observations yet. Preset values and paddle
  forcing are unchanged; Storm Surf late-bake decay remains an open issue.
- S023: the new 120-frame ordering/sustain test is implemented but not run or
  accepted as part of the review-driven tuning slice.
- S028: sessions with 3–5 beginners require real participants. Protocol and
  observation table are in RELEASE_CHECKLIST.md; no sessions are claimed.

These gates prevent calling REQ-003 launch-ready even though the implementation
preview is packaged for manual review.
