# AquaSuite — Water FX for Blender

**One-click, layered water for Blender 4.2+**: oceans with floating
objects, rain, rain with impact ripples, snow, object-to-liquid, rain
splashing into pools, and an aimable water hose — all from one panel,
every setup reversible with one Delete button.

This repository is AquaSuite's **public home for bug reports, questions
and the roadmap**. The add-on itself is available from the store page.

## Report a bug

1. If AquaSuite showed an error popup, click **Copy Report** (personal
   paths are removed automatically).
2. [Open a new issue](../../issues/new/choose) and paste the report.
3. Say what you did just before it happened, and attach a small .blend
   if you can.

Support is best-effort; known issues stay visible here so nobody has to
report the same thing twice.

## Beta modes

**Still Water, Rain Sim and the hose's Simulate Liquid are Beta.** They use Blender's
Mantaflow liquid solver: they must be baked, bakes get slow and RAM-heavy
at high Resolution, and Draft results are coarse. Plan bake time into
your shot.

## Roadmap

Planned for future free 1.x updates, in no fixed order and without dates:

- **Ocean wake**: interactive ripples behind moving objects, with
  floating objects reacting to them.
- Hose domain refit when the nozzle is re-aimed.
- A wetness effect on the Reactive Rain floor.
- One-click presets (drizzle, storm, calm sea, …).

Have a request? Open an issue with the **Feature request** template.

## Compatibility promise

From 1.0, updates never change or break setups in your saved files.
Improvements to existing setups are always opt-in.
