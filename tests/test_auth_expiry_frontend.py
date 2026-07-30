import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class AuthExpiryFrontendTest(unittest.TestCase):
    def test_abgelaufene_api_session_fuehrt_zur_loginseite(self):
        app_js = (ROOT / "static-studio" / "app.js").read_text(encoding="utf-8")
        self.assertIn("if (res.status === 401)", app_js)
        self.assertIn('window.location.replace("/login.html")', app_js)


if __name__ == "__main__":
    unittest.main()
