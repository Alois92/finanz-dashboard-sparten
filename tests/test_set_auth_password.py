"""Tests fuer das administrative Passwort-Setup."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.auth_store import AuthConfigStore
from scripts import set_auth_password


class SetAuthPasswordTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.auth_path = Path(self.tempdir.name) / "auth.json"

    def test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format(self):
        with (
            mock.patch.object(set_auth_password, "APP_DIR", Path(self.tempdir.name)),
            mock.patch.dict(
                "os.environ", {"FINANZ_AUTH_FILE": str(self.auth_path)}
            ),
            mock.patch("getpass.getpass", side_effect=["123456", "123456"]),
        ):
            self.assertEqual(set_auth_password.main(), 0)
        config = AuthConfigStore(self.auth_path).load()
        self.assertTrue(config.must_change_password)
        self.assertIsNone(config.recovery_hash)
        self.assertEqual(config.version, 1)
        self.assertNotIn("123456", self.auth_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
