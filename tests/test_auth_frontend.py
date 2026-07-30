import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class AuthFrontendTest(unittest.TestCase):
    def test_studio_bietet_logout_ueber_post_an(self):
        index_html = (ROOT / "static-studio" / "index.html").read_text(
            encoding="utf-8"
        )
        app_js = (ROOT / "static-studio" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="logout-button"', index_html)
        self.assertIn('fetch("/api/auth/logout"', app_js)
        self.assertIn('window.location.replace("/login.html")', app_js)


if __name__ == "__main__":
    unittest.main()
