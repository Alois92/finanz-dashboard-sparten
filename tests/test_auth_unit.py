import unittest

from app.auth import (
    SESSION_SECONDS,
    AuthManager,
    AuthSettings,
    LoginRateLimiter,
    hash_password,
    verify_password,
)


class AuthUnitTest(unittest.TestCase):
    def test_passwort_hash_enthaelt_keinen_klartext(self):
        password = "Ein-langes-Testpasswort!"
        encoded = hash_password(password, salt=b"0123456789abcdef")
        self.assertNotIn(password, encoded)
        self.assertTrue(verify_password(password, encoded))
        self.assertFalse(verify_password("falsch", encoded))

    def test_session_gilt_hoechstens_zwoelf_stunden(self):
        manager = AuthManager(AuthSettings("hash", b"x" * 32))
        token = manager.create_session(now=1_000_000)
        self.assertTrue(manager.verify_session(token, now=1_000_000))
        self.assertTrue(
            manager.verify_session(token, now=1_000_000 + SESSION_SECONDS)
        )
        self.assertFalse(
            manager.verify_session(token, now=1_000_001 + SESSION_SECONDS)
        )

    def test_manipulierte_session_wird_abgewiesen(self):
        manager = AuthManager(AuthSettings("hash", b"x" * 32))
        token = manager.create_session(now=1_000_000)
        self.assertFalse(manager.verify_session(token + "x", now=1_000_000))

    def test_rate_limit_sperrt_nach_fuenf_fehlern(self):
        limiter = LoginRateLimiter(max_failures=5)
        for _ in range(5):
            self.assertFalse(limiter.is_blocked("geraet"))
            limiter.record_failure("geraet")
        self.assertTrue(limiter.is_blocked("geraet"))
        limiter.clear("geraet")
        self.assertFalse(limiter.is_blocked("geraet"))


if __name__ == "__main__":
    unittest.main()
