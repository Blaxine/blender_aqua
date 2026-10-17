# SPDX-License-Identifier: GPL-3.0-or-later
"""A successful marker must never hide a failed Blender process."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aqs_testlib as lib
import run_tests as runner


def test_process_results():
    cases = (
        ('normal completion', 0, 'AQS_TEST| PASS | check |\nAQS_TEST| DONE\n', False),
        ('crash after DONE', 1, 'AQS_TEST| PASS | check |\nAQS_TEST| DONE\n', True),
        ('empty completion', 0, 'AQS_TEST| DONE\n', True),
        ('missing DONE', 0, 'AQS_TEST| PASS | check |\n', True),
        ('explicit skip', 0, 'AQS_TEST| SKIP | check | unavailable\nAQS_TEST| DONE\n', False),
    )
    for name, code, output, failure in cases:
        proc = SimpleNamespace(returncode=code, stdout=output, stderr='')
        with patch.object(runner.subprocess, 'run', return_value=proc):
            results = runner.run_file({'path': 'fake'}, 'fake.py', False, lib.WORKDIR)
        lib.check(name, any(r[0] == 'FAIL' for r in results) == failure, str(results))


def test_timeout_after_done():
    exc = runner.subprocess.TimeoutExpired('fake', 300,
                                         output=b'AQS_TEST| DONE\n')
    with patch.object(runner.subprocess, 'run', side_effect=exc):
        results = runner.run_file({'path': 'fake'}, 'fake.py', False, lib.WORKDIR)
    lib.check('timeout cannot pass even after DONE', any(r[0] == 'FAIL' for r in results))


lib.main(globals())
