"""HTTP-Integrationstest fuer Gruppen mit temporaerer SQLite-DB."""
import json, os, pathlib, socket, subprocess, sys, tempfile, time, unittest
import urllib.error, urllib.request

TEMP_DB = tempfile.TemporaryDirectory(prefix="finanz-gruppen-")
os.environ["FINANZ_DB"] = str(pathlib.Path(TEMP_DB.name) / "test.db")
ROOT = pathlib.Path(__file__).resolve().parents[1]

class GruppenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); cls.port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"], cwd=ROOT,
            env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                cls.raw("GET", "/api/health"); break
            except Exception:
                if cls.server.poll() is not None: raise RuntimeError("uvicorn beendet")
                time.sleep(.2)
        else: raise RuntimeError("uvicorn nicht bereit")

    @classmethod
    def tearDownClass(cls):
        if cls.server.poll() is None:
            cls.server.terminate(); cls.server.wait(timeout=10)
        TEMP_DB.cleanup()

    @classmethod
    def raw(cls, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(cls.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def req(self, method, path, expected=200, body=None):
        status, content = self.raw(method, path, body)
        self.assertEqual(status, expected, content.decode(errors="replace"))
        return json.loads(content) if content else None

    def test_auswertungsgruppen_crud_und_spartenzuordnung(self):
        self.assertIn(
            "Name",
            self.req("POST", "/api/auswertungsgruppen", 400,
                     {"name": "   ", "sparte_ids": []})["detail"],
        )
        sparten = self.req("GET", "/api/sparten")[:2]
        gruppe = self.req(
            "POST", "/api/auswertungsgruppen", 201,
            {"name": "  Vermietung gesamt  ", "beschreibung": "  Bericht  ",
             "sparte_ids": [sparten[1]["id"], sparten[0]["id"],
                             sparten[0]["id"]]},
        )
        gid = gruppe["id"]
        self.assertEqual("Vermietung gesamt", gruppe["name"])
        self.assertEqual("Bericht", gruppe["beschreibung"])
        self.assertEqual(sorted(s["id"] for s in sparten), gruppe["sparte_ids"])
        self.assertEqual(gruppe, next(
            g for g in self.req("GET", "/api/auswertungsgruppen")
            if g["id"] == gid
        ))

        gruppe = self.req(
            "PUT", f"/api/auswertungsgruppen/{gid}", body={
                "name": "Nur zweite Sparte", "sparte_ids": [sparten[1]["id"]]
            },
        )
        self.assertEqual([sparten[1]["id"]], gruppe["sparte_ids"])
        self.req("PUT", f"/api/auswertungsgruppen/{gid}", 404,
                 {"name": "Fehler", "sparte_ids": [999999]})
        self.req("DELETE", f"/api/auswertungsgruppen/{gid}", 204)
        self.assertFalse(any(g["id"] == gid for g in
                             self.req("GET", "/api/auswertungsgruppen")))
        self.assertGreaterEqual(len(self.req("GET", "/api/sparten")), 2)
        self.req("DELETE", f"/api/auswertungsgruppen/{gid}", 404)

    def test_crud_filter_fehlerfaelle_und_loeschsicherheit(self):
        self.assertIn("Name", self.req("POST", "/api/globalgruppen", 400, {"name":"   "})["detail"])
        sparten = self.req("GET", "/api/sparten")[:2]
        kats = [self.req("POST", "/api/kategorien", 201, {"sparte_id":s["id"],
            "name":f"Versicherung {i}", "richtung":"beides"}) for i,s in enumerate(sparten,1)]
        dritte = self.req("POST", "/api/kategorien", 201, {"sparte_id":sparten[0]["id"],
            "name":"Nicht Gruppe", "richtung":"beides"})
        gruppe = self.req("POST", "/api/globalgruppen", 201,
            {"name":"  Versicherungen gesamt  ", "beschreibung":"  Gesamt  "})
        gid = gruppe["id"]
        self.assertEqual((gruppe["name"], gruppe["beschreibung"], gruppe["kategorie_ids"]),
                         ("Versicherungen gesamt", "Gesamt", []))
        gruppe = self.req("PUT", f"/api/globalgruppen/{gid}", body={"name":" Versicherungen ",
            "kategorie_ids":[kats[1]["id"], kats[0]["id"], kats[0]["id"]]})
        self.assertEqual(gruppe["kategorie_ids"], sorted(k["id"] for k in kats))
        for s,k,t,b in ((sparten[0],kats[0],"einnahme",10000),
                        (sparten[1],kats[1],"ausgabe",2500),
                        (sparten[0],dritte,"ausgabe",9900)):
            self.req("POST", "/api/buchungen", 201, {"sparte_id":s["id"], "datum":"2026-04-15",
                "typ":t, "zeilen":[{"kategorie_id":k["id"], "betrag_cent":b}]})
        query=f"globalgruppe_id={gid}"
        dash=self.req("GET",f"/api/dashboard?{query}")
        self.assertEqual((dash["einnahmen_cent"],dash["ausgaben_cent"],dash["saldo_cent"]),(10000,2500,7500))
        self.assertEqual(self.req("GET",f"/api/verlauf?{query}")["monate"][0]["saldo_cent"],7500)
        self.assertEqual(self.req("GET",f"/api/jahresvergleich?{query}")["gesamt"][0]["saldo_cent"],7500)
        both=self.req("GET",f"/api/dashboard?{query}&sparte_id={sparten[0]['id']}")
        self.assertEqual((both["einnahmen_cent"],both["ausgaben_cent"]),(10000,0))
        for endpoint in ("dashboard","verlauf","jahresvergleich"):
            self.assertIn("Gruppe",self.req("GET",f"/api/{endpoint}?globalgruppe_id=999999",404)["detail"])
        self.req("PUT",f"/api/globalgruppen/{gid}",404,{"name":"X","kategorie_ids":[999999]})
        self.req("DELETE",f"/api/globalgruppen/{gid}",204)
        self.assertEqual(len(self.req("GET","/api/buchungen")),3)
        self.req("DELETE",f"/api/globalgruppen/{gid}",404)

    def test_studio_vertrag(self):
        html=(ROOT/"static-studio"/"index.html").read_text(encoding="utf-8")
        js=(ROOT/"static-studio"/"app.js").read_text(encoding="utf-8")
        for marker in ("form-globalgruppe","gg-name","gg-kategorien","tbl-globalgruppen","dashboard-filter"):
            self.assertIn(f'id="{marker}"',html)
        self.assertIn('/globalgruppen',js); self.assertIn('globalgruppe_id',js)
        for marker in ("form-auswertungsgruppe", "ag-name", "ag-sparten",
                       "tbl-auswertungsgruppen"):
            self.assertIn(f'id="{marker}"', html)
        self.assertIn('/auswertungsgruppen', js)
        self.assertIn('sparte_ids', js)

if __name__ == "__main__": unittest.main(verbosity=2)
