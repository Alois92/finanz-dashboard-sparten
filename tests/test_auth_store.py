import os
import pathlib
import stat
import tempfile
import unittest

from app.auth_store import AuthConfig, AuthConfigStore, generate_recovery_code, validate_password
from app.auth import hash_password


class PasswordValidationTest(unittest.TestCase):
    def test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt(self):
        for value in ("123456", "abcdef", "ABCDEF", "Ab3!x?", "äÖ7-xy"):
            validate_password(value)

    def test_ungueltige_passwoerter_werden_abgewiesen(self):
        for value in ("12345", " " * 6, "abc\n12", "x" * 129):
            with self.assertRaises(ValueError):
                validate_password(value)

    def test_hashing_verwendet_die_flexible_passwortvalidierung(self):
        encoded = hash_password("123456", salt=b"0123456789abcdef")
        self.assertTrue(encoded.startswith("scrypt$"))


class AuthConfigStoreTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tempdir.name) / "auth.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_store_schreibt_atomar_und_laesst_keine_temporaere_datei(self):
        store = AuthConfigStore(self.path)
        config = AuthConfig("hash", "s" * 64, None, True, 1)
        store.save(config)
        self.assertEqual(store.load(), config)
        self.assertEqual(list(self.path.parent.glob("auth-*.tmp")), [])

    @unittest.skipUnless(os.name == "posix", "POSIX-Dateirechte")
    def test_store_setzt_dateimodus_0600(self):
        AuthConfigStore(self.path).save(AuthConfig("hash", "s" * 64, None, True, 1))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_wiederherstellungscode_hat_mindestens_128_bit(self):
        code = generate_recovery_code()
        self.assertGreaterEqual(len(code.replace("-", "")), 26)
        self.assertNotIn("O", code)
        self.assertNotIn("0", code)



if __name__ == "__main__":
    unittest.main()
