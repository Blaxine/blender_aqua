# Running the AquaSuite tests

The suite runs the add-on headless (`blender -b --factory-startup`) in every
Blender you configure and reports PASS/FAIL per check. It needs only the
Python that runs the command (3.8+) and the Blender installs themselves — no
packages to install.

## One-time setup

Copy `tests/blender_paths.example.json` to `tests/blender_paths.local.json`
(git-ignored) and list the Blenders to test:

```json
{
  "blenders": [
    {"name": "4.2", "path": "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"},
    {"name": "5.1", "path": "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"}
  ]
}
```

Supported releases are Blender 4.2 and newer: list 4.2 and the latest 5.x.

## Running

```
python tests/run_tests.py            # fast suite: ~30 s for two Blenders
python tests/run_tests.py --bake     # + low-res bakes of every liquid mode
python tests/run_tests.py -k liquids # only files whose name contains "liquids"
```

`--bake` is required before every release (see the release checklist). The
exit code is 0 only when every check passed in every Blender.

## Reading the output

Each test file prints one line per Blender (`ok` or `FAIL`, checks passed),
followed by the detail of every failing check. A file that crashes or never
finishes is reported as a failure with the last lines of Blender's output.

## Writing tests

Add `tests/test_<area>.py`: define `test_*` functions and end the file with
`lib.main(globals())` (see `tests/aqs_testlib.py` for helpers). Each file runs
in its own fresh Blender process; functions run in definition order.

- Hold assembly **uuids**, never entry objects: adding or removing entries
  makes Python references into `scene.aqs_assemblies` point at the wrong entry.
- Call `bpy.context.view_layer.update()` before measuring positions, sizes or
  bounding boxes of objects that were just created, moved or resized.
- Bake tests check `lib.BAKE` and skip without `--bake`.
- Headless Blender has no windows: popups, the clipboard UI and panel text are
  covered by the release checklist, not here.
