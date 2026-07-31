"""Unit-Tests fuer das Aufraeumen gestarteter Integrationsserver."""
import unittest
from unittest.mock import patch

from tests import _process_cleanup as process_cleanup


class _LaufenderProzess:
    pid = 1234

    def __init__(self):
        self.wait_timeouts = []
        self.stdout = _Stream()
        self.stderr = _Stream()

    def poll(self):
        return None

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        return 0


class _Stream:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class ProcessCleanupTest(unittest.TestCase):
    def test_windows_cleanup_ist_idempotent_und_beendet_den_gestarteten_baum(self):
        process = _LaufenderProzess()
        with patch.object(process_cleanup.os, "name", "nt"), patch.object(
            process_cleanup.subprocess, "run"
        ) as taskkill:
            process_cleanup.cleanup_process_tree(process)
            process_cleanup.cleanup_process_tree(process)

        taskkill.assert_called_once_with(
            ["taskkill", "/PID", "1234", "/T", "/F"],
            check=False,
            stdout=process_cleanup.subprocess.DEVNULL,
            stderr=process_cleanup.subprocess.DEVNULL,
            timeout=5,
        )
        self.assertEqual(process.wait_timeouts, [5])
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)


if __name__ == "__main__":
    unittest.main()
