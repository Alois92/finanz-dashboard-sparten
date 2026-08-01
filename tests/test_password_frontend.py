import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def frontend_file(name):
    path = ROOT / "static-studio" / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


class PasswordFrontendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.login_html = frontend_file("login.html")
        cls.index_html = frontend_file("index.html")
        cls.setup_html = frontend_file("password-setup.html")
        cls.setup_js = frontend_file("password-setup.js")
        cls.change_html = frontend_file("password-change.html")
        cls.change_js = frontend_file("password-change.js")
        cls.recover_html = frontend_file("password-recover.html")
        cls.recover_js = frontend_file("password-recover.js")

    def test_login_verlinkt_passwort_vergessen(self):
        self.assertIn('href="/password-recover.html"', self.login_html)

    def test_setup_hat_zwei_passwortfelder_und_recovery_aktionen(self):
        self.assertIn('id="new-password"', self.setup_html)
        self.assertIn('id="repeat-password"', self.setup_html)
        self.assertIn('getElementById("download-code")', self.setup_js)
        self.assertIn("window.print()", self.setup_js)

    def test_mehr_menue_verlinkt_passwortaenderung(self):
        self.assertIn('href="/password-change.html"', self.index_html)

    def test_desktop_navigation_verlinkt_passwortaenderung(self):
        sidebar = self.index_html.split("</aside>", 1)[0]
        self.assertIn('href="/password-change.html"', sidebar)

    def test_setup_ruft_initial_password_mit_same_origin_credentials_auf(self):
        self.assertIn('fetch("/api/auth/state"', self.setup_js)
        self.assertIn('fetch("/api/auth/initial-password"', self.setup_js)
        self.assertIn('credentials: "same-origin"', self.setup_js)

    def test_passwortaenderung_sendet_altes_und_neues_passwort(self):
        self.assertIn('fetch("/api/auth/change-password"', self.change_js)
        self.assertIn('current_password:', self.change_js)
        self.assertIn('new_password:', self.change_js)

    def test_wiederherstellung_setzt_neues_passwort_und_zeigt_fehler(self):
        self.assertIn('fetch("/api/auth/recover"', self.recover_js)
        self.assertIn('recovery_code:', self.recover_js)
        self.assertIn('body.detail || "Vorgang fehlgeschlagen."', self.recover_js)

    def test_passwortfelder_begrenzen_laenge_und_verwenden_neues_autocomplete(self):
        for page in (self.setup_html, self.change_html, self.recover_html):
            self.assertIn('minlength="6"', page)
            self.assertIn('maxlength="128"', page)
            self.assertIn('autocomplete="new-password"', page)

    def test_aktuelles_passwort_ist_fuer_passwortmanager_gekennzeichnet(self):
        self.assertRegex(
            self.change_html,
            r'id="current-password"[^>]*autocomplete="current-password"',
        )

    def test_recovery_code_wird_nur_in_einem_sicheren_bereich_angeboten(self):
        self.assertIn('id="recovery-code"', self.setup_html)
        self.assertIn('hidden', self.setup_html)
        self.assertIn('text/plain;charset=utf-8', self.setup_js)
        self.assertIn('Hohenegg-Finanzstudio-Wiederherstellungscode.txt', self.setup_js)

    def test_recovery_code_kann_kopiert_werden(self):
        for page, script in (
            (self.setup_html, self.setup_js),
            (self.recover_html, self.recover_js),
        ):
            self.assertIn('id="copy-code"', page)
            self.assertIn("navigator.clipboard.writeText", script)
            self.assertLess(
                script.index("copyCode.addEventListener"), script.index("downloadCode.addEventListener")
            )

    def test_erfolgsmeldung_ist_fokussierbar_und_fuehrt_zur_anmeldung(self):
        for page, script in (
            (self.setup_html, self.setup_js),
            (self.recover_html, self.recover_js),
        ):
            self.assertIn('aria-live="polite"', page)
            self.assertIn('tabindex="-1"', page)
            self.assertIn('href="/login.html"', page)
            self.assertIn("recoveryPanel.focus()", script)
            show_start = script.index("function showRecoveryCode")
            show_end = script.index("copyCode.addEventListener")
            focus = script.index("recoveryPanel.focus()")
            self.assertLess(show_start, focus)
            self.assertLess(focus, show_end)

    def test_netzwerkfehler_werden_verstaendlich_angezeigt(self):
        for script in (self.setup_js, self.change_js, self.recover_js):
            self.assertIn("error instanceof TypeError", script)
            self.assertIn("Der Finanz-Server ist gerade nicht erreichbar.", script)



if __name__ == "__main__":
    unittest.main()
