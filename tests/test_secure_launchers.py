import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SecureLauncherTest(unittest.TestCase):
    def test_handy_launcher_oeffnet_nur_private_produktiv_url(self):
        cmd = (ROOT / "start-handy.cmd").read_text(encoding="utf-8")
        self.assertIn("https://finanz.tailb1b087.ts.net", cmd)
        self.assertNotIn("--host 0.0.0.0", cmd)
        self.assertNotIn("http://<IP-dieses-PCs>:8000", cmd)

    def test_autostart_empfiehlt_keine_lan_freigabe(self):
        script = (ROOT / "scripts" / "autostart-einrichten.ps1").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("durch '--host 0.0.0.0' ersetzen", script)
        self.assertIn("--host 127.0.0.1", script)


if __name__ == "__main__":
    unittest.main()
