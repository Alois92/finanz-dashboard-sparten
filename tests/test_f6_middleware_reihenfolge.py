"""F6: Schreibschutz-Middleware lief bisher aussen (vor Geraetefilter und
Anmeldung) und gab bei Migrationsfehlern den vollen Fehlertext preis. Sie
muss die innerste Middleware sein (zuerst registriert; Starlette baut den
Stack umgekehrt), damit ein nicht freigegebenes/nicht angemeldetes Geraet
403/401 bekommt statt 503 mit Details.

Direkte ASGI-Aufrufe gegen die echte App (kein FINANZ_TEST_AUTH_BYPASS,
damit AuthMiddleware tatsaechlich prueft) mit frei waehlbarem scope["client"]
- so laesst sich der Geraetefilter ohne echten uvicorn-Prozess/Proxy-Header
ansteuern (request.client kommt direkt aus dem ASGI-Scope).
"""
import asyncio
import json
import unittest
from urllib.parse import urlsplit

from app.main import app


class MiddlewareReihenfolgeTest(unittest.TestCase):
    def test_build_middleware_stack_hat_schreibschutz_innen(self):
        """Schreibschutz muss die innerste Middleware sein (naeher am Router
        als TrustedHost und Auth)."""
        stack = app.build_middleware_stack()
        namen = []
        node = stack
        while hasattr(node, "app"):
            namen.append(type(node).__name__)
            node = node.app
        self.assertLess(namen.index("AuthMiddleware"), namen.index("BaseHTTPMiddleware"))
        self.assertLess(namen.index("TrustedHostMiddleware"), namen.index("AuthMiddleware"))

    def _request(self, method, url, client_ip, cookie=None):
        parts = urlsplit(url)
        headers = [(b"host", b"localhost")]
        if cookie:
            headers.append((b"cookie", cookie.encode()))
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": method, "scheme": "http",
            "path": parts.path, "raw_path": parts.path.encode(), "query_string": b"",
            "headers": headers, "client": (client_ip, 51000), "server": ("localhost", 80),
            "root_path": "",
        }
        messages = []

        async def run():
            async def receive():
                return {"type": "http.request", "body": b""}

            async def send(message):
                messages.append(message)

            await app(scope, receive, send)

        asyncio.run(run())
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        try:
            return status, json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return status, body

    def test_schreibgeschuetzt_und_nicht_freigegebenes_geraet_gibt_403_nicht_503(self):
        app.state.schreibgeschuetzt = True
        app.state.migrationsfehler = "Migration 099 fehlgeschlagen: SQL-Fehler XY"
        self.addCleanup(setattr, app.state, "schreibgeschuetzt", False)
        self.addCleanup(setattr, app.state, "migrationsfehler", None)

        status, data = self._request("POST", "/api/buchungen", "100.72.201.96")

        self.assertEqual(403, status, data)
        self.assertNotIn("Migration", json.dumps(data))
        self.assertNotIn("Datenbank", json.dumps(data))

    def test_schreibgeschuetzt_und_keine_session_gibt_401_nicht_503(self):
        app.state.schreibgeschuetzt = True
        app.state.migrationsfehler = "Migration 099 fehlgeschlagen: SQL-Fehler XY"
        self.addCleanup(setattr, app.state, "schreibgeschuetzt", False)
        self.addCleanup(setattr, app.state, "migrationsfehler", None)

        # 100.105.4.18 ist in DEFAULT_ALLOWED_CLIENT_IPS - der Geraetefilter
        # laesst die Anfrage durch, aber es fehlt eine gueltige Session.
        status, data = self._request("POST", "/api/buchungen", "100.105.4.18")

        self.assertEqual(401, status, data)
        self.assertNotIn("Migration", json.dumps(data))
        self.assertNotIn("Datenbank", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
