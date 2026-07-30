# Passwort-Selbstverwaltung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das Finanzstudio ermöglicht eine erzwungene Ersteinrichtung, selbstständige Passwortänderung und sichere Wiederherstellung mit einem einmaligen Wiederherstellungscode.

**Architecture:** Ein fokussierter `AuthConfigStore` verwaltet die veränderbare Auth-Datei atomar im schreibbaren Datenbereich. `app/auth.py` bleibt für Sitzungen, Zugriffskontrolle und HTTP-Endpunkte zuständig, verwendet aber den Store als einzige persistente Quelle. Drei kleine statische Seiten bilden Ersteinrichtung, Änderung und Wiederherstellung ab.

**Tech Stack:** Python 3.11, FastAPI, Starlette, scrypt aus der Python-Standardbibliothek, Vanilla JavaScript, HTML/CSS, `unittest`, systemd und Tailscale Serve.

## Global Constraints

- Passwortlänge: mindestens 6, höchstens 128 Zeichen.
- Groß-/Kleinbuchstaben, Zahlen und Sonderzeichen sind erlaubt.
- Steuerzeichen sowie ausschließlich aus Leerzeichen bestehende Passwörter sind unzulässig.
- Wiederherstellungscode: mindestens 128 Bit Zufälligkeit, einmal verwendbar, serverseitig nur als scrypt-Hash.
- Sitzungsdauer bleibt maximal 12 Stunden.
- Nach Passwortänderung oder Wiederherstellung werden alle Sitzungen widerrufen.
- Zugriff bleibt auf `nb-lois`, `s24-ultra-von-lois` und `s24-ultra-von-theresia` begrenzt.
- Produktiver Auth-Pfad: `/var/lib/finanz/auth.json`, Modus `0600`, Benutzer `finanz`.
- Keine Änderung an Buchungen, Belegen oder der SQLite-Finanzdatenbank.
- Jede Produktionsänderung folgt RED → GREEN → vollständige Regressionstests.

---

### Task 1: Passwortvalidierung und atomarer Auth-Speicher

**Files:**
- Create: `app/auth_store.py`
- Create: `tests/test_auth_store.py`
- Modify: `app/auth.py:20-105`

**Interfaces:**
- Produces: `validate_password(password: str) -> None`
- Produces: `generate_recovery_code() -> str`
- Produces: `AuthConfig(password_hash: str, session_secret: str, recovery_hash: str | None, must_change_password: bool, version: int)`
- Produces: `AuthConfigStore(path: pathlib.Path).load() -> AuthConfig`
- Produces: `AuthConfigStore(path: pathlib.Path).save(config: AuthConfig) -> None`

- [ ] **Step 1: Failing tests für flexible Passwörter schreiben**

```python
class PasswordValidationTest(unittest.TestCase):
    def test_genau_sechs_zeichen_und_alle_zeichenarten_sind_erlaubt(self):
        for value in ("123456", "abcdef", "ABCDEF", "Ab3!x?", "äÖ7-xy"):
            validate_password(value)

    def test_ungueltige_passwoerter_werden_abgewiesen(self):
        for value in ("12345", " " * 6, "abc\n12", "x" * 129):
            with self.assertRaises(ValueError):
                validate_password(value)
```

- [ ] **Step 2: RED verifizieren**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_auth_store.PasswordValidationTest -v
```

Expected: Importfehler, weil `app.auth_store` noch nicht existiert.

- [ ] **Step 3: Minimale Validierung implementieren**

```python
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128

def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValueError("Das Passwort ist ungültig.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Das Passwort muss 6 bis 128 Zeichen lang sein.")
    if not password.strip() or any(unicodedata.category(char).startswith("C") for char in password):
        raise ValueError("Das Passwort enthält unzulässige Zeichen.")
```

- [ ] **Step 4: GREEN verifizieren**

Run denselben Unit-Test. Expected: 2 Tests, `OK`.

- [ ] **Step 5: Failing Tests für Store und Wiederherstellungscode schreiben**

```python
def test_store_schreibt_atomar_und_laesst_keine_temporaere_datei(self):
    store = AuthConfigStore(self.path)
    config = AuthConfig("hash", "s" * 64, None, True, 1)
    store.save(config)
    self.assertEqual(store.load(), config)
    self.assertEqual(list(self.path.parent.glob("auth-*.tmp")), [])

def test_wiederherstellungscode_hat_mindestens_128_bit(self):
    code = generate_recovery_code()
    self.assertGreaterEqual(len(code.replace("-", "")), 26)
    self.assertNotIn("O", code)
    self.assertNotIn("0", code)
```

- [ ] **Step 6: RED verifizieren**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_auth_store -v
```

Expected: Fehler wegen fehlender `AuthConfigStore`- und Code-Implementierung.

- [ ] **Step 7: Store und Codegenerator implementieren**

```python
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

@dataclass(frozen=True)
class AuthConfig:
    password_hash: str
    session_secret: str
    recovery_hash: str | None = None
    must_change_password: bool = False
    version: int = 1

def generate_recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(28))
    return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))

class AuthConfigStore:
    def __init__(self, path: pathlib.Path):
        self.path = path

    def load(self) -> AuthConfig:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return AuthConfig(**data)

    def save(self, config: AuthConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix="auth-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
```

- [ ] **Step 8: GREEN und bestehende Auth-Unit-Tests verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_auth_store tests.test_auth_unit -v
```

Expected: alle Tests `OK`.

- [ ] **Step 9: Commit**

```powershell
git add app/auth_store.py app/auth.py tests/test_auth_store.py
git commit -m "Fuege sicheren Auth-Konfigurationsspeicher hinzu"
```

---

### Task 2: Ersteinrichtung, Passwortänderung und Wiederherstellung im Backend

**Files:**
- Modify: `app/auth.py`
- Modify: `tests/test_auth.py`
- Create: `tests/test_auth_lifecycle.py`

**Interfaces:**
- Consumes: `AuthConfigStore`, `AuthConfig`, `validate_password`, `generate_recovery_code`
- Produces: `GET /api/auth/state`
- Produces: `POST /api/auth/initial-password`
- Produces: `POST /api/auth/change-password`
- Produces: `POST /api/auth/recover`
- Produces: `AuthManager.replace_config(config: AuthConfig) -> None`
- Produces: `AuthManager.revoke_all_sessions() -> None`

- [ ] **Step 1: Lifecycle-Integrationstest mit eigener temporärer Auth-Datei schreiben**

Der Test startet Uvicorn mit:

```python
env["FINANZ_AUTH_FILE"] = str(Path(cls.tempdir.name) / "auth.json")
```

und legt diese Konfiguration an:

```python
AuthConfigStore(Path(env["FINANZ_AUTH_FILE"])).save(
    AuthConfig(
        password_hash=hash_password(START_PASSWORD),
        session_secret="s" * 64,
        recovery_hash=None,
        must_change_password=True,
        version=1,
    )
)
```

Die Assertions:

```python
def test_startpasswort_erlaubt_nur_ersteinrichtung(self):
    cookie = self.login(START_PASSWORD)
    self.assertEqual(self.get("/api/auth/state", cookie).json(), {"must_change_password": True})
    self.assertEqual(self.get_status("/api/sparten", cookie), 403)

def test_ersteinrichtung_gibt_code_einmal_aus(self):
    cookie = self.login(START_PASSWORD)
    response = self.post(
        "/api/auth/initial-password",
        {"new_password": "Ab3!xy", "repeat_password": "Ab3!xy"},
        cookie,
    )
    self.assertEqual(response.status, 200)
    self.assertRegex(response.json()["recovery_code"], r"^(?:[A-Z2-9]{4}-){6}[A-Z2-9]{4}$")
    config = self.store.load()
    self.assertFalse(config.must_change_password)
    self.assertNotIn(response.json()["recovery_code"], self.auth_path.read_text())
```

- [ ] **Step 2: RED verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_auth_lifecycle -v
```

Expected: 404 für die neuen Endpunkte.

- [ ] **Step 3: Store in `app/auth.py` verdrahten**

```python
CONFIG_FILE = pathlib.Path(
    os.environ.get("FINANZ_AUTH_FILE", BASE / "instance" / "auth.json")
)
AUTH_STORE = AuthConfigStore(CONFIG_FILE)

class AuthManager:
    def replace_config(self, config: AuthConfig) -> None:
        AUTH_STORE.save(config)
        self.settings = AuthSettings.from_config(config)
        self.config = config
        self.revoke_all_sessions()

    def revoke_all_sessions(self) -> None:
        with self._session_lock:
            self._sessions.clear()
```

- [ ] **Step 4: State- und Ersteinrichtungsendpunkt implementieren**

```python
@router.get("/api/auth/state")
async def auth_state(request: Request):
    return {"must_change_password": AUTH.config.must_change_password}

@router.post("/api/auth/initial-password")
async def initial_password(request: Request):
    if not AUTH.config.must_change_password:
        return JSONResponse({"detail": "Ersteinrichtung ist bereits abgeschlossen."}, status_code=409)
    body = await request.json()
    new_password = body.get("new_password", "")
    repeat = body.get("repeat_password", "")
    if new_password != repeat:
        return JSONResponse({"detail": "Die Passwörter stimmen nicht überein."}, status_code=422)
    try:
        validate_password(new_password)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    recovery_code = generate_recovery_code()
    AUTH.replace_config(AuthConfig(
        password_hash=hash_password(new_password),
        session_secret=secrets.token_urlsafe(48),
        recovery_hash=hash_password(recovery_code),
        must_change_password=False,
        version=1,
    ))
    return {"recovery_code": recovery_code}
```

- [ ] **Step 5: Middleware auf erzwungene Ersteinrichtung begrenzen**

Erlaubte Pfade für eine gültige Sitzung mit `must_change_password`:

```python
INITIAL_SETUP_PATHS = frozenset({
    "/api/auth/state",
    "/api/auth/initial-password",
    "/api/auth/logout",
    "/password-setup.html",
    "/password-setup.js",
})
```

Alle anderen Browserpfade leiten auf `/password-setup.html`; alle anderen APIs
antworten mit 403.

- [ ] **Step 6: GREEN für Ersteinrichtung verifizieren**

Run Lifecycle-Test. Expected: Ersteinrichtungsfälle `OK`.

- [ ] **Step 7: Failing Tests für Änderung und Wiederherstellung schreiben**

```python
def test_passwortaenderung_widerruft_alte_sitzung(self):
    cookie = self.login("Ab3!xy")
    response = self.post("/api/auth/change-password", {
        "current_password": "Ab3!xy",
        "new_password": "Neu#77",
        "repeat_password": "Neu#77",
    }, cookie)
    self.assertEqual(response.status, 204)
    self.assertEqual(self.get_status("/api/sparten", cookie), 401)

def test_recovery_rotiert_code_und_lehnt_wiederverwendung_ab(self):
    first_code = self.recovery_code
    response = self.post_public("/api/auth/recover", {
        "recovery_code": first_code,
        "new_password": "Reset!8",
        "repeat_password": "Reset!8",
    })
    new_code = response.json()["recovery_code"]
    self.assertNotEqual(new_code, first_code)
    self.assertEqual(self.recover_status(first_code, "NochNeu9!"), 401)
```

- [ ] **Step 8: RED verifizieren**

Run Lifecycle-Test. Expected: 404 für Änderung und Wiederherstellung.

- [ ] **Step 9: Endpunkte minimal implementieren**

```python
@router.post("/api/auth/change-password", status_code=204)
async def change_password(request: Request):
    body = await request.json()
    current = body.get("current_password", "")
    new = body.get("new_password", "")
    repeat = body.get("repeat_password", "")
    if not verify_password(current, AUTH.config.password_hash):
        return JSONResponse({"detail": "Anmeldedaten sind nicht korrekt."}, status_code=401)
    if new != repeat:
        return JSONResponse({"detail": "Die Passwörter stimmen nicht überein."}, status_code=422)
    try:
        validate_password(new)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    AUTH.replace_config(replace(
        AUTH.config,
        password_hash=hash_password(new),
        session_secret=secrets.token_urlsafe(48),
        must_change_password=False,
    ))
    return Response(status_code=204)

@router.post("/api/auth/recover")
async def recover(request: Request):
    key = _client_key(request)
    if RECOVERY_LIMITER.is_blocked(key):
        return JSONResponse({"detail": "Zu viele Fehlversuche."}, status_code=429)
    body = await request.json()
    supplied = "".join(str(body.get("recovery_code", "")).upper().split())
    new = body.get("new_password", "")
    repeat = body.get("repeat_password", "")
    if not AUTH.config.recovery_hash or not verify_password(supplied, AUTH.config.recovery_hash):
        RECOVERY_LIMITER.record_failure(key)
        return JSONResponse({"detail": "Anmeldedaten sind nicht korrekt."}, status_code=401)
    if new != repeat:
        return JSONResponse({"detail": "Die Passwörter stimmen nicht überein."}, status_code=422)
    try:
        validate_password(new)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    next_code = generate_recovery_code()
    AUTH.replace_config(AuthConfig(
        password_hash=hash_password(new),
        session_secret=secrets.token_urlsafe(48),
        recovery_hash=hash_password(next_code),
        must_change_password=False,
        version=1,
    ))
    RECOVERY_LIMITER.clear(key)
    return {"recovery_code": next_code}
```

- [ ] **Step 10: GREEN und Auth-Regressionssuite verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_auth_lifecycle tests.test_auth tests.test_auth_unit -v
```

Expected: alle Tests `OK`.

- [ ] **Step 11: Commit**

```powershell
git add app/auth.py tests/test_auth.py tests/test_auth_lifecycle.py
git commit -m "Ermoegliche Passwortwechsel und Wiederherstellung"
```

---

### Task 3: Bedienoberfläche für Setup, Änderung und Wiederherstellung

**Files:**
- Modify: `static-studio/login.html`
- Modify: `static-studio/login.js`
- Modify: `static-studio/index.html`
- Modify: `static-studio/app.js`
- Create: `static-studio/password-common.css`
- Create: `static-studio/password-setup.html`
- Create: `static-studio/password-setup.js`
- Create: `static-studio/password-change.html`
- Create: `static-studio/password-change.js`
- Create: `static-studio/password-recover.html`
- Create: `static-studio/password-recover.js`
- Create: `tests/test_password_frontend.py`

**Interfaces:**
- Consumes: die vier Auth-API-Endpunkte aus Task 2
- Produces: wiederverwendete Form- und Recovery-Code-Darstellung

- [ ] **Step 1: Failing Frontend-Vertragstests schreiben**

```python
def test_login_verlinkt_passwort_vergessen(self):
    self.assertIn('href="/password-recover.html"', self.login_html)

def test_setup_hat_zwei_passwortfelder_und_recovery_aktionen(self):
    self.assertIn('id="new-password"', self.setup_html)
    self.assertIn('id="repeat-password"', self.setup_html)
    self.assertIn('id="download-code"', self.setup_js)
    self.assertIn("window.print()", self.setup_js)

def test_mehr_menue_verlinkt_passwortaenderung(self):
    self.assertIn('href="/password-change.html"', self.index_html)
```

- [ ] **Step 2: RED verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_password_frontend -v
```

Expected: fehlende Dateien/Elemente.

- [ ] **Step 3: Gemeinsames Layout und Seiten erstellen**

Alle Passwortfelder verwenden:

```html
<input type="password" minlength="6" maxlength="128"
       autocomplete="new-password" required>
```

Die Login-Seite erhält:

```html
<a class="secondary-link" href="/password-recover.html">Passwort vergessen?</a>
```

Das Menü erhält:

```html
<a class="sheet-item" href="/password-change.html">Passwort ändern</a>
```

- [ ] **Step 4: JavaScript für Formulare implementieren**

Gemeinsames POST-Muster:

```javascript
const response = await fetch(endpoint, {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  credentials: "same-origin",
  body: JSON.stringify(payload),
});
const body = await response.json().catch(() => ({}));
if (!response.ok) throw new Error(body.detail || "Vorgang fehlgeschlagen.");
```

Recovery-Download:

```javascript
const blob = new Blob(
  [`Hohenegg Finanzstudio – Wiederherstellungscode\n\n${code}\n`],
  {type: "text/plain;charset=utf-8"},
);
const link = document.createElement("a");
link.href = URL.createObjectURL(blob);
link.download = "Hohenegg-Finanzstudio-Wiederherstellungscode.txt";
link.click();
URL.revokeObjectURL(link.href);
```

- [ ] **Step 5: GREEN und JavaScript-Syntax verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_password_frontend -v
node --check static-studio\login.js
node --check static-studio\password-setup.js
node --check static-studio\password-change.js
node --check static-studio\password-recover.js
```

Expected: alle Tests und Syntaxprüfungen erfolgreich.

- [ ] **Step 6: Commit**

```powershell
git add static-studio tests/test_password_frontend.py
git commit -m "Fuege Passwort-Selbstverwaltung im Studio hinzu"
```

---

### Task 4: Administratives Setup und Produktionsmigration

**Files:**
- Modify: `scripts/set_auth_password.py`
- Create: `tests/test_set_auth_password.py`
- Modify: `docs/SICHERHEIT.md`

**Interfaces:**
- Consumes: `AuthConfigStore`, `AuthConfig`, `validate_password`
- Produces: CLI-Fallback, der ein Passwort setzt und `must_change_password=True` aktivieren kann

- [ ] **Step 1: Failing CLI-Test schreiben**

```python
def test_cli_akzeptiert_sechs_zeichen_und_schreibt_neues_format(self):
    with mock.patch("getpass.getpass", side_effect=["123456", "123456"]):
        self.assertEqual(set_auth_password.main(), 0)
    config = AuthConfigStore(self.auth_path).load()
    self.assertTrue(config.must_change_password)
    self.assertIsNone(config.recovery_hash)
```

- [ ] **Step 2: RED verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_set_auth_password -v
```

Expected: altes Dateiformat bzw. alter 12-Zeichen-Text lässt den Test fehlschlagen.

- [ ] **Step 3: CLI auf Store umstellen**

```python
ziel = pathlib.Path(
    os.environ.get("FINANZ_AUTH_FILE", APP_DIR / "instance" / "auth.json")
)
validate_password(erstes)
AuthConfigStore(ziel).save(AuthConfig(
    password_hash=hash_password(erstes),
    session_secret=secrets.token_urlsafe(48),
    recovery_hash=None,
    must_change_password=True,
    version=1,
))
```

Prompt:

```python
erstes = getpass.getpass("Neues Startpasswort (6 bis 128 Zeichen): ")
```

- [ ] **Step 4: GREEN und Dokumentation verifizieren**

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_set_auth_password -v
rg -n "6 bis 128|Wiederherstellungscode|/var/lib/finanz/auth.json" docs\SICHERHEIT.md
```

Expected: Test `OK`, alle drei Dokumentationsbegriffe vorhanden.

- [ ] **Step 5: Commit**

```powershell
git add scripts/set_auth_password.py tests/test_set_auth_password.py docs/SICHERHEIT.md
git commit -m "Aktualisiere Passwort-Setup und Betriebsanleitung"
```

---

### Task 5: Vollständige Verifikation und sichere Live-Schaltung

**Files:**
- Create in workspace outputs: `outputs/security-finanz-app/deploy-password-self-service.sh`
- Create in workspace outputs: `outputs/security-finanz-app/verify-password-self-service.sh`

**Interfaces:**
- Consumes: fertigen Git-Commit, vorhandenen Proxmox-Zugang, CT 101
- Produces: getrennte Release-Kopie, migrierte Auth-Datei, geprüften Produktivdienst

- [ ] **Step 1: Vollständige lokale Regression ausführen**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\test_gruppen_integration.py
.\.venv\Scripts\python.exe scripts\test_drilldown_api.py
.\.venv\Scripts\python.exe scripts\test_export_integration.py
node --check static-studio\app.js
node --check static-studio\login.js
node --check static-studio\password-setup.js
node --check static-studio\password-change.js
node --check static-studio\password-recover.js
.\.venv\Scripts\python.exe -m py_compile app\auth.py app\auth_store.py scripts\set_auth_password.py
git diff --check
```

Expected: Exit 0, keine fehlgeschlagenen Tests.

- [ ] **Step 2: Finalen Implementierungscommit erstellen**

```powershell
git status --short
git log -1 --oneline
```

Expected: sauberer Working Tree und dokumentierter finaler Commit.

- [ ] **Step 3: Prüfsummenverifiziertes Git-Bundle und getrenntes Release erstellen**

Bundle enthält den vollständigen Branch `studio`. Im CT wird es unter
`/opt/finanz-app-next-<commit>` geklont. Alle Tests aus Schritt 1 laufen mit
`/opt/finanz-app/.venv/bin/python` in dieser getrennten Kopie.

- [ ] **Step 4: Daten und Auth-Konfiguration sichern**

Vor der Umschaltung:

```bash
sqlite3 /var/lib/finanz/finanz.db ".backup '/var/lib/finanz/backup/pre-password-self-service.db'"
cp --preserve=mode,ownership /opt/finanz-app-next-9c45fc2/instance/auth.json \
  /var/lib/finanz/auth-before-self-service.json
```

Beide Dateien mit `PRAGMA integrity_check` beziehungsweise SHA-256 prüfen.

- [ ] **Step 5: Auth-Datei migrieren und Ersteinrichtung markieren**

`deploy-password-self-service.sh` führt vor dem Umschalten diese Migration mit
dem Python der bestehenden virtuellen Umgebung aus:

```python
import json
import os
from pathlib import Path

source = Path("/opt/finanz-app-next-9c45fc2/instance/auth.json")
target = Path("/var/lib/finanz/auth.json")
data = json.loads(source.read_text(encoding="utf-8"))
data.update({
    "recovery_hash": None,
    "must_change_password": True,
    "version": 1,
})
temporary = target.with_suffix(".json.tmp")
temporary.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.chmod(temporary, 0o600)
os.replace(temporary, target)
```

Der Deployment-Wrapper führt die Migration mit `runuser -u finanz` aus; dadurch
gehört `/var/lib/finanz/auth.json` dem Benutzer und der Gruppe `finanz`.
Die systemd-Drop-In-Datei setzt:

```ini
[Service]
Environment=FINANZ_AUTH_FILE=/var/lib/finanz/auth.json
WorkingDirectory=/opt/finanz-app-next-<commit>
```

- [ ] **Step 6: Umschalten mit automatischem Rollback**

Dienst neu starten und prüfen:

```bash
systemctl is-active --quiet finanz.service
test "$(curl -s -o /dev/null -w '%{http_code}' \
  -H 'Host: finanz.tailb1b087.ts.net' \
  http://127.0.0.1:8000/login.html)" = 200
```

Bei jedem Fehler wird die bisherige Drop-In-Datei wieder installiert und
`finanz.service` neu gestartet.

- [ ] **Step 7: End-to-End über Tailscale und Neustart testen**

- Login mit Startpasswort leitet zur Ersteinrichtung.
- Finanz-API ist davor 403.
- Neues Testpasswort mit 6 Zeichen wird angenommen.
- Recovery-Code erscheint einmal und steht nicht in der Serverdatei.
- Passwortänderung widerruft die Sitzung.
- Recovery mit Code funktioniert und der alte Code wird abgewiesen.
- Nicht freigegebene Geräteadresse erhält 403.
- Produktive Buchungsanzahl bleibt 9.
- Vollständiger CT-Neustart; danach dieselben Dienst-, Serve-, Auth- und
  Integritätsprüfungen.

- [ ] **Step 8: Temporäre Klartext-Testwerte und Transferdateien löschen**

Nur exakt während des Deployments erzeugte Test-Passwörter, Test-Codes und
temporäre Auth-Kopien löschen. Produktive Auth-Datei, verschlüsselte
Startpasswortdatei und Backups bleiben erhalten.

- [ ] **Step 9: Abschlussbericht aktualisieren**

Dokumentieren:

- produktiver Commit
- Testergebnisse
- Backup-Pfade und Prüfsummen
- Status `tailnet only`
- Workflow für Ersteinrichtung, Änderung und Wiederherstellung
- weiterhin ausstehende separate Genehmigungen für GitHub-Push und Entfernung
  von `finanzdeploy`
