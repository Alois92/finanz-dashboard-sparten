"""Passwort-Authentifizierung und sichere Sitzungen fuer das Finanzstudio."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, replace

from fastapi import APIRouter, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.auth_store import (
    AuthConfig,
    AuthConfigStore,
    generate_recovery_code,
    validate_password,
)


BASE = pathlib.Path(__file__).resolve().parent.parent
CONFIG_FILE = pathlib.Path(
    os.environ.get("FINANZ_AUTH_FILE", BASE / "instance" / "auth.json")
)
AUTH_STORE = AuthConfigStore(CONFIG_FILE)
COOKIE_NAME = "__Host-finanz_session"
SESSION_SECONDS = 12 * 60 * 60
DEFAULT_ALLOWED_CLIENT_IPS = (
    "127.0.0.1,::1,"
    "100.96.17.87,fd7a:115c:a1e0::f901:1195,"
    "100.105.4.18,fd7a:115c:a1e0::5232:414,"
    "100.126.171.58,fd7a:115c:a1e0::4932:ab3b"
)
OEFFENTLICHE_PFADE = frozenset({
    "/api/health",
    "/api/auth/login",
    "/api/auth/recover",
    "/login.html",
    "/login.js",
})
INITIAL_SETUP_PATHS = frozenset({
    "/api/auth/state",
    "/api/auth/initial-password",
    "/api/auth/logout",
    "/password-setup.html",
    "/password-setup.js",
})


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Erzeugt einen gesalzenen scrypt-Hash ohne Klartextpasswort."""
    validate_password(password)
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt$16384$8$1${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """Prueft einen scrypt-Hash robust und in konstanter Vergleichszeit."""
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_b64_decode(expected)),
        )
        return hmac.compare_digest(digest, _b64_decode(expected))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class AuthSettings:
    password_hash: str | None
    session_secret: bytes | None

    @property
    def configured(self) -> bool:
        return bool(self.password_hash and self.session_secret)

    @classmethod
    def load(cls) -> "AuthSettings":
        password_hash = os.environ.get("FINANZ_AUTH_PASSWORD_HASH")
        session_secret = os.environ.get("FINANZ_SESSION_SECRET")
        if password_hash and session_secret and len(session_secret) >= 32:
            return cls(password_hash, session_secret.encode("utf-8"))
        try:
            config = AUTH_STORE.load()
            password_hash = str(config.password_hash)
            session_secret = str(config.session_secret)
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return cls(None, None)
        if len(session_secret) < 32:
            return cls(None, None)
        return cls(password_hash, session_secret.encode("utf-8"))

    @classmethod
    def from_config(cls, config: AuthConfig) -> "AuthSettings":
        return cls(config.password_hash, config.session_secret.encode("utf-8"))


class LoginRateLimiter:
    """Begrenzt Passwortversuche pro Quelladresse im laufenden Prozess."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 15 * 60):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        return [
            entry for entry in self._failures.get(key, [])
            if now - entry < self.window_seconds
        ]

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, now)
            self._failures[key] = recent
            return len(recent) >= self.max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = self._recent(key, now)
            recent.append(now)
            self._failures[key] = recent

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class AuthManager:
    def __init__(self, settings: AuthSettings | AuthConfig | None = None):
        self.config: AuthConfig | None = None
        if isinstance(settings, AuthConfig):
            self.config = settings
            self.settings = AuthSettings.from_config(settings)
        elif isinstance(settings, AuthSettings):
            self.settings = settings
        else:
            try:
                self.config = AUTH_STORE.load()
                self.settings = AuthSettings.from_config(self.config)
            except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.settings = AuthSettings.load()
        self.rate_limiter = LoginRateLimiter()
        self._sessions: dict[str, int] = {}
        self._session_lock = threading.Lock()

    def replace_config(self, config: AuthConfig) -> None:
        AUTH_STORE.save(config)
        self.settings = AuthSettings.from_config(config)
        self.config = config
        self.revoke_all_sessions()

    def revoke_all_sessions(self) -> None:
        with self._session_lock:
            self._sessions.clear()

    def create_session(self, now: int | None = None) -> str:
        if not self.settings.session_secret:
            raise RuntimeError("Authentifizierung ist nicht konfiguriert.")
        now = int(time.time() if now is None else now)
        nonce = secrets.token_urlsafe(16)
        expires = now + SESSION_SECONDS
        payload = json.dumps(
            {
                "iat": now,
                "exp": expires,
                "nonce": nonce,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded = _b64_encode(payload)
        signature = hmac.new(
            self.settings.session_secret,
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        token = f"{encoded}.{_b64_encode(signature)}"
        with self._session_lock:
            self._sessions = {
                session_id: expiry
                for session_id, expiry in self._sessions.items()
                if expiry >= now
            }
            self._sessions[nonce] = expires
        return token

    def verify_session(self, token: str | None, now: int | None = None) -> bool:
        if not token or not self.settings.session_secret:
            return False
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = hmac.new(
                self.settings.session_secret,
                encoded.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(
                expected_signature, _b64_decode(supplied_signature)
            ):
                return False
            payload = json.loads(_b64_decode(encoded))
            current = int(time.time() if now is None else now)
            issued = int(payload["iat"])
            expires = int(payload["exp"])
            nonce = str(payload["nonce"])
            with self._session_lock:
                active = self._sessions.get(nonce) == expires
            return (
                active
                and issued <= current <= expires
                and expires - issued <= SESSION_SECONDS
            )
        except (
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):
            return False

    def revoke_session(self, token: str | None) -> None:
        if not token or not self.verify_session(token):
            return
        try:
            encoded, _signature = token.split(".", 1)
            nonce = str(json.loads(_b64_decode(encoded))["nonce"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return
        with self._session_lock:
            self._sessions.pop(nonce, None)


AUTH = AuthManager()
RECOVERY_LIMITER = LoginRateLimiter()
router = APIRouter()


def _test_bypass_enabled() -> bool:
    """Erlaubt bestehende Integrationstests nur mit einer Wegwerf-DB."""
    if os.environ.get("FINANZ_TEST_AUTH_BYPASS") != "1":
        return False
    db_path = os.environ.get("FINANZ_DB")
    if not db_path:
        return False
    try:
        resolved_db = pathlib.Path(db_path).resolve()
        temp_root = pathlib.Path(tempfile.gettempdir()).resolve()
        return resolved_db.is_relative_to(temp_root)
    except (OSError, ValueError):
        return False


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unbekannt"


def _client_is_allowed(request: Request) -> bool:
    allowed = {
        address.strip()
        for address in os.environ.get(
            "FINANZ_ALLOWED_CLIENT_IPS",
            DEFAULT_ALLOWED_CLIENT_IPS,
        ).split(",")
        if address.strip()
    }
    return _client_key(request) in allowed


@router.post("/api/auth/login", status_code=204)
async def login(request: Request):
    if not AUTH.settings.configured:
        return JSONResponse(
            {"detail": "Anmeldung ist noch nicht eingerichtet."},
            status_code=503,
        )
    key = _client_key(request)
    if AUTH.rate_limiter.is_blocked(key):
        return JSONResponse(
            {"detail": "Zu viele Fehlversuche. Bitte spaeter erneut versuchen."},
            status_code=429,
        )
    try:
        body = await request.json()
        password = body.get("password", "")
    except (json.JSONDecodeError, AttributeError):
        password = ""
    if not isinstance(password, str) or not verify_password(
        password, AUTH.settings.password_hash or ""
    ):
        AUTH.rate_limiter.record_failure(key)
        return JSONResponse(
            {"detail": "Passwort ist nicht korrekt."},
            status_code=401,
        )
    AUTH.rate_limiter.clear(key)
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE_NAME,
        AUTH.create_session(),
        max_age=SESSION_SECONDS,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/api/auth/logout", status_code=204)
async def logout(request: Request):
    AUTH.revoke_session(request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/api/auth/state")
async def auth_state(request: Request):
    return {"must_change_password": bool(AUTH.config and AUTH.config.must_change_password)}


@router.post("/api/auth/initial-password")
async def initial_password(request: Request):
    if not AUTH.config:
        return JSONResponse(
            {"detail": "Anmeldung ist noch nicht eingerichtet."}, status_code=503
        )
    if not AUTH.config.must_change_password:
        return JSONResponse(
            {"detail": "Ersteinrichtung ist bereits abgeschlossen."}, status_code=409
        )
    body = await request.json()
    new_password = body.get("new_password", "")
    repeat = body.get("repeat_password", "")
    if new_password != repeat:
        return JSONResponse(
            {"detail": "Die Passwoerter stimmen nicht ueberein."}, status_code=422
        )
    try:
        validate_password(new_password)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    recovery_code = generate_recovery_code()
    AUTH.replace_config(
        AuthConfig(
            password_hash=hash_password(new_password),
            session_secret=secrets.token_urlsafe(48),
            recovery_hash=hash_password(recovery_code),
            must_change_password=False,
            version=1,
        )
    )
    return {"recovery_code": recovery_code}


@router.post("/api/auth/change-password", status_code=204)
async def change_password(request: Request):
    if not AUTH.config:
        return JSONResponse(
            {"detail": "Anmeldung ist noch nicht eingerichtet."}, status_code=503
        )
    body = await request.json()
    current = body.get("current_password", "")
    new = body.get("new_password", "")
    repeat = body.get("repeat_password", "")
    if not verify_password(current, AUTH.config.password_hash):
        return JSONResponse(
            {"detail": "Anmeldedaten sind nicht korrekt."}, status_code=401
        )
    if new != repeat:
        return JSONResponse(
            {"detail": "Die Passwoerter stimmen nicht ueberein."}, status_code=422
        )
    try:
        validate_password(new)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    AUTH.replace_config(
        replace(
            AUTH.config,
            password_hash=hash_password(new),
            session_secret=secrets.token_urlsafe(48),
            must_change_password=False,
        )
    )
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
    if not AUTH.config or (
        not AUTH.config.recovery_hash
        or not verify_password(supplied, AUTH.config.recovery_hash)
    ):
        RECOVERY_LIMITER.record_failure(key)
        return JSONResponse(
            {"detail": "Anmeldedaten sind nicht korrekt."}, status_code=401
        )
    if new != repeat:
        return JSONResponse(
            {"detail": "Die Passwoerter stimmen nicht ueberein."}, status_code=422
        )
    try:
        validate_password(new)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    next_code = generate_recovery_code()
    AUTH.replace_config(
        AuthConfig(
            password_hash=hash_password(new),
            session_secret=secrets.token_urlsafe(48),
            recovery_hash=hash_password(next_code),
            must_change_password=False,
            version=1,
        )
    )
    RECOVERY_LIMITER.clear(key)
    return {"recovery_code": next_code}


class AuthMiddleware(BaseHTTPMiddleware):
    """Schuetzt die komplette Oberflaeche und alle Finanz-APIs."""

    async def dispatch(self, request: Request, call_next):
        if not _client_is_allowed(request):
            response = JSONResponse(
                {"detail": "Dieses Gerät ist für das Finanzstudio nicht freigegeben."},
                status_code=403,
            )
            return self._secure_headers(response)
        path = request.url.path
        if _test_bypass_enabled():
            response = await call_next(request)
            return self._secure_headers(response)
        if path not in OEFFENTLICHE_PFADE:
            token = request.cookies.get(COOKIE_NAME)
            if not AUTH.verify_session(token):
                if path.startswith("/api/"):
                    response = JSONResponse(
                        {"detail": "Anmeldung erforderlich."},
                        status_code=401,
                    )
                else:
                    response = RedirectResponse("/login.html", status_code=303)
                return self._secure_headers(response)
            if AUTH.config and AUTH.config.must_change_password and path not in INITIAL_SETUP_PATHS:
                if path.startswith("/api/"):
                    response = JSONResponse(
                        {"detail": "Ersteinrichtung erforderlich."}, status_code=403
                    )
                else:
                    response = RedirectResponse("/password-setup.html", status_code=303)
                return self._secure_headers(response)
        response = await call_next(request)
        return self._secure_headers(response)

    @staticmethod
    def _secure_headers(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
