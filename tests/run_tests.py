#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the AquaSuite test suite in every configured Blender.

    python tests/run_tests.py              fast suite (seconds per Blender)
    python tests/run_tests.py --bake       + low-res bake tests (required before a release)
    python tests/run_tests.py -k stamp     only test files whose name contains "stamp"

Blender executables are listed in tests/blender_paths.local.json (git-ignored;
copy tests/blender_paths.example.json to create it).  Each test file runs in a
fresh `blender -b --factory-startup` process per Blender.  Exit code is 0 only
when every check in every Blender passed.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CONFIG = os.path.join(HERE, "blender_paths.local.json")
EXAMPLE = os.path.join(HERE, "blender_paths.example.json")
TAG = "AQS_TEST|"


def load_blenders():
    if not os.path.isfile(CONFIG):
        print(f"No test config found. Copy\n  {EXAMPLE}\nto\n  {CONFIG}\n"
              "and list the Blender executables to test with.")
        sys.exit(2)
    with open(CONFIG, encoding="utf-8") as fh:
        blenders = json.load(fh).get("blenders", [])
    missing = [b for b in blenders if not os.path.isfile(b.get("path", ""))]
    for b in missing:
        print(f"Blender '{b.get('name')}' not found at {b.get('path')}")
    if missing or not blenders:
        sys.exit(2)
    return blenders


def run_file(blender, test_file, bake, workdir, info=None):
    """Check results; INFO lines (measurements a test reports) go to `info`."""
    cmd = [blender["path"], "-b", "--factory-startup", "--python", test_file,
           "--", "--repo", REPO, "--workdir", workdir]
    if bake:
        cmd.append("--bake")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    returncode = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env,
                              # The ocean bake test bakes 3 x 720 frames (~45 min).
                              timeout=10800 if bake else 300)
        out = proc.stdout + proc.stderr
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        out += f"\n{TAG} FAIL | timeout | gave up after {exc.timeout} s\n"
    results, done = [], False
    for line in out.splitlines():
        if not line.startswith(TAG):
            continue
        parts = [p.strip() for p in line[len(TAG):].split("|")]
        if parts[0] == "DONE":
            done = True
        elif parts[0] == "INFO":
            if info is not None:
                info.append(" | ".join(parts[1:]))
        elif parts[0] in ("PASS", "FAIL", "SKIP"):
            results.append((parts[0], parts[1] if len(parts) > 1 else "?",
                            parts[2] if len(parts) > 2 else ""))
    if returncode not in (None, 0):
        if done and blender.get("known_exit_crash"):
            # Opt-in per Blender (config): a crash while quitting AFTER every
            # check reported is shown, not failed (Blender 4.1 + Mantaflow).
            results.append(("SKIP", "known crash on exit",
                            f"exit {returncode} after DONE (known_exit_crash)"))
        else:
            results.append(("FAIL", "Blender process exited unsuccessfully", str(returncode)))
    if done and not results:
        results.append(("FAIL", "test file produced no results", "DONE without PASS, FAIL or SKIP"))
    if not done:
        tail = "\n".join(out.splitlines()[-15:])
        results.append(("FAIL", "test file crashed or never finished",
                        tail.replace("\n", " / ")[-400:]))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bake", action="store_true",
                    help="include low-resolution bake tests")
    ap.add_argument("-k", default="", help="only test files containing this text")
    args = ap.parse_args()

    blenders = load_blenders()
    files = sorted(f for f in glob.glob(os.path.join(HERE, "test_*.py"))
                   if args.k in os.path.basename(f))
    if not files:
        print("No test files matched.")
        return 2

    totals = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    failures = []
    start = time.time()
    for blender in blenders:
        print(f"\n=== Blender {blender['name']} ===")
        for test_file in files:
            workdir = tempfile.mkdtemp(prefix="aqs_test_")
            try:
                info = []
                results = run_file(blender, test_file, args.bake, workdir, info)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
            name = os.path.basename(test_file)
            for status, check, detail in results:
                totals[status] += 1
                if status == "FAIL":
                    failures.append(f"[{blender['name']}] {name}: {check} — {detail}")
            bad = sum(1 for r in results if r[0] == "FAIL")
            ran = sum(1 for r in results if r[0] != "SKIP")
            skipped = len(results) - ran
            mark = "ok  " if not bad else "FAIL"
            print(f"  {mark} {name}: {ran - bad}/{ran} checks passed"
                  + (f", {skipped} skipped" if skipped else ""))
            for status, check, detail in results:
                if status == "FAIL":
                    print(f"         FAIL {check}: {detail}")
            for line in info:  # measurements a test chose to report
                print(f"         INFO {line}")

    print(f"\n{totals['PASS']} passed, {totals['FAIL']} failed, "
          f"{totals['SKIP']} skipped across {len(blenders)} Blender(s) "
          f"in {time.time() - start:.0f} s"
          + ("" if args.bake else "  (bake tests skipped: use --bake)"))
    return 1 if totals["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
