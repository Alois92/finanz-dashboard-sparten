"""Persistenz und Validierung fuer die Authentifizierungskonfiguration."""
from __future__ import annotations

import unicodedata
import json
import os
import pathlib
import secrets
import tempfile
from dataclasses import asdict, dataclass


MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def validate_password(password: str) -> None:
    """Lehnt Passwoerter ausserhalb der erlaubten Grenzen ab."""
    if not isinstance(password, str):
        raise ValueError("Das Passwort ist ungültig.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Das Passwort muss 6 bis 128 Zeichen lang sein.")
    if not password.strip() or any(
        unicodedata.category(char).startswith("C") for char in password
    ):
        raise ValueError("Das Passwort enthält unzulässige Zeichen.")


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
        handle, temp_name = tempfile.mkstemp(
            prefix="auth-", suffix=".tmp", dir=self.path.parent
        )
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
