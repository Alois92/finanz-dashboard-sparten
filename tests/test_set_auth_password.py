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
            self.assertEqual(set_auth_password.main([]), 0)
        config = AuthConfigStore(self.auth_path).load()
        self.assertTrue(config.must_change_password)
        # Seit dem Nachziehen der Wiederherstellung legt auch das Skript einen
        # Recovery-Hash an - sonst waere "Passwort vergessen" wirkungslos.
        self.assertIsNotNone(config.recovery_hash)
        self.assertEqual(config.version, 1)
        self.assertNotIn("123456", self.auth_path.read_text(encoding="utf-8"))

    def test_nur_recovery_code_laesst_passwort_unveraendert(self):
        umgebung = {"FINANZ_AUTH_FILE": str(self.auth_path)}
        with (
            mock.patch.object(set_auth_password, "APP_DIR", Path(self.tempdir.name)),
            mock.patch.dict("os.environ", umgebung),
            mock.patch("getpass.getpass", side_effect=["123456", "123456"]),
        ):
            set_auth_password.main([])
        vorher = AuthConfigStore(self.auth_path).load()

        with (
            mock.patch.object(set_auth_password, "APP_DIR", Path(self.tempdir.name)),
            mock.patch.dict("os.environ", umgebung),
        ):
            self.assertEqual(set_auth_password.main(["--nur-recovery-code"]), 0)
        nachher = AuthConfigStore(self.auth_path).load()

        self.assertEqual(nachher.password_hash, vorher.password_hash)
        self.assertEqual(nachher.session_secret, vorher.session_secret)
        self.assertEqual(nachher.must_change_password, vorher.must_change_password)
        self.assertNotEqual(nachher.recovery_hash, vorher.recovery_hash)

    def test_nur_recovery_code_ohne_bestehende_datei_scheitert_sauber(self):
        with (
            mock.patch.object(set_auth_password, "APP_DIR", Path(self.tempdir.name)),
            mock.patch.dict("os.environ", {"FINANZ_AUTH_FILE": str(self.auth_path)}),
        ):
            self.assertEqual(set_auth_password.main(["--nur-recovery-code"]), 1)
        self.assertFalse(self.auth_path.exists())


if __name__ == "__main__":
    unittest.main()
