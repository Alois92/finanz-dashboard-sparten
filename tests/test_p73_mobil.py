"""P73 - Mobil-Navigation und Handy-Fixes.

Statische Prüfungen ohne Browser-Werkzeug (das ist per Bericht docs/neubau/berichte/
P73-runde1.md belegt): Syntax der geänderten JS-Dateien, Vorhandensein des sechsten
Bottom-Nav-Eintrags ("Mehr"), Mindestgrößen für Tap-Ziele/Dialog im 760-px-Media-Query
und die min-width:0-Korrektur auf der Erfassen-Seite (QA5-01).
"""

import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "static-neu"


def _media_block(css_text: str, breakpoint_px: int = 760) -> str:
    """Extrahiert den Inhalt des ersten @media(max-width:<px>px)-Blocks (klammerbewusst,
    da die Datei größtenteils minifiziert ist und einfache Regex-Grenzen nicht reichen)."""
    marker = f"@media(max-width:{breakpoint_px}px)"
    start = css_text.index(marker)
    brace_start = css_text.index("{", start)
    depth = 0
    for i in range(brace_start, len(css_text)):
        if css_text[i] == "{":
            depth += 1
        elif css_text[i] == "}":
            depth -= 1
            if depth == 0:
                return css_text[brace_start + 1:i]
    raise AssertionError("Media-Query-Block nicht sauber geschlossen.")


class P73JsSyntaxTest(unittest.TestCase):
    """(a) node --check für alle im Zuge von P73 geänderten JS-Dateien."""

    GEAENDERTE_JS = ["app.js"]

    def test_node_check_geaenderte_dateien(self):
        for name in self.GEAENDERTE_JS:
            pfad = STATIC / name
            with self.subTest(datei=name):
                self.assertTrue(pfad.exists(), f"{pfad} fehlt")
                ergebnis = subprocess.run(
                    ["node", "--check", str(pfad)],
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    ergebnis.returncode, 0,
                    f"node --check meldet einen Syntaxfehler in {name}:\n{ergebnis.stderr}",
                )


class P73MobileMenuMarkupTest(unittest.TestCase):
    """(b) index.html enthält den sechsten Bottom-Nav-Eintrag für das Mehr-Menü."""

    def test_sechster_bottom_nav_eintrag_vorhanden(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        nav_match = re.search(r'<nav class="mobile-nav"[^>]*>(.*?)</nav>', html, re.S)
        self.assertIsNotNone(nav_match, "kein <nav class=\"mobile-nav\"> in index.html gefunden")
        nav_html = nav_match.group(1)
        buttons = re.findall(r"<button[^>]*data-route=\"([^\"]+)\"", nav_html)
        self.assertEqual(
            len(buttons), 6,
            f"Bottom-Nav soll 6 Einträge haben (5 Seiten + Mehr), gefunden: {buttons}",
        )
        self.assertIn("mehr", buttons, "kein data-route=\"mehr\"-Eintrag im Bottom-Nav")

    def test_mehr_button_ist_kein_routen_alias(self):
        # QA5-02: "mehr" darf keine Route aus app.js sein, sondern muss in app.js
        # gesondert behandelt werden (öffnet das Sheet statt einer Seite).
        app_js = (STATIC / "app.js").read_text(encoding="utf-8")
        routes_match = re.search(r"const routes=\{(.*?)\};", app_js)
        self.assertIsNotNone(routes_match, "routes-Map in app.js nicht gefunden")
        self.assertNotIn("mehr:", routes_match.group(1), "\"mehr\" darf keine echte Route sein")
        self.assertIn("openMoreSheet", app_js, "openMoreSheet() fehlt in app.js")
        self.assertIn("routes).filter", app_js, "Restrouten müssen aus der routes-Map abgeleitet werden, nicht hart kodiert sein")


class P73MobileCssTest(unittest.TestCase):
    """(c) Tap-Ziel- und Dialog-Mindestgrößen im 760-px-Media-Query von style.css."""

    @classmethod
    def setUpClass(cls):
        cls.css = (STATIC / "style.css").read_text(encoding="utf-8")
        cls.media = _media_block(cls.css)

    def test_mobile_nav_button_min_height(self):
        match = re.search(r"\.mobile-nav button\s*\{([^}]*)\}", self.media)
        self.assertIsNotNone(match, ".mobile-nav button-Regel fehlt im 760px-Media-Query")
        hoehe = re.search(r"min-height\s*:\s*(\d+(?:\.\d+)?)px", match.group(1))
        self.assertIsNotNone(hoehe, "keine min-height auf .mobile-nav button")
        self.assertGreaterEqual(float(hoehe.group(1)), 44, "min-height von .mobile-nav button unter 44px")
        breite = re.search(r"min-width\s*:\s*(\d+(?:\.\d+)?)px", match.group(1))
        self.assertIsNotNone(breite, "keine min-width auf .mobile-nav button")
        self.assertGreaterEqual(float(breite.group(1)), 48, "min-width von .mobile-nav button unter 48px")

    def test_dialog_max_width_100vw(self):
        match = re.search(r"dialog\s*\{([^}]*)\}", self.media)
        self.assertIsNotNone(match, "dialog-Regel fehlt im 760px-Media-Query")
        self.assertIn("100vw", match.group(1), "dialog-max-width im Media-Query referenziert nicht 100vw")
        self.assertIn("max-width", match.group(1))

    def test_tap_ziele_lnk_und_ktable(self):
        match = re.search(r"\.lnk,\s*#k-table \.act button\s*\{([^}]*)\}", self.media)
        self.assertIsNotNone(match, ".lnk/#k-table .act button-Regel fehlt im 760px-Media-Query (QA5-03)")
        hoehe = re.search(r"min-height\s*:\s*(\d+(?:\.\d+)?)px", match.group(1))
        self.assertIsNotNone(hoehe)
        self.assertGreaterEqual(float(hoehe.group(1)), 40)

    def test_tscroll_scroll_hinweis(self):
        # QA5-04: sichtbarer Verlaufsschatten am rechten Rand von .tscroll/.table-wrap.
        self.assertIn(".tscroll::after", self.media)
        self.assertIn("linear-gradient", self.media)

    def test_desktop_breakpoint_unveraendert(self):
        # Der 760px-Breakpoint selbst darf durch P73 nicht verschoben worden sein.
        self.assertEqual(self.css.count("@media(max-width:760px)"), 1)


class P73ErfassenGridTest(unittest.TestCase):
    """(d) QA5-01: min-width:0 auf den Grid-Items von .erfassen-page .quick-card form."""

    def test_min_width_0_auf_grid_items(self):
        css = (STATIC / "pages" / "erfassen.css").read_text(encoding="utf-8")
        self.assertIn(
            ".erfassen-page .quick-card form>*{min-width:0}", css,
            "min-width:0 auf den Grid-Items von .erfassen-page .quick-card form fehlt (QA5-01)",
        )

    def test_g2_1_kollabiert_auf_mobil_trotz_inline_style(self):
        # erfassen.js setzt grid-template-columns per Inline-style (1.3fr 1fr) auf
        # .grid.g2-1 - ohne !important-Override im Media-Query bleibt die Karte auf
        # eine schmale Spalte gequetscht (zweite Ursache neben dem fehlenden
        # min-width:0, siehe P73-runde1.md).
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        media = _media_block(css)
        match = re.search(r"\.grid\.g2-1\s*\{([^}]*)\}", media)
        self.assertIsNotNone(match, ".grid.g2-1-Regel fehlt im 760px-Media-Query")
        self.assertIn("!important", match.group(1))


if __name__ == "__main__":
    unittest.main()
