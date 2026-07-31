"""Richtet das Finanzstudio-Startpasswort ohne Klartextspeicherung ein."""
from __future__ import annotations

import getpass
import os
import pathlib
import secrets
import sys

APP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from app.auth import hash_password  # noqa: E402
from app.auth_store import AuthConfig, AuthConfigStore, validate_password  # noqa: E402


def main() -> int:
    ziel = pathlib.Path(
        os.environ.get("FINANZ_AUTH_FILE", APP_DIR / "instance" / "auth.json")
    )
    print("Finanzstudio-Anmeldung einrichten")
    print("Das Passwort wird verdeckt eingegeben und niemals im Klartext gespeichert.")
    erstes = getpass.getpass("Neues Startpasswort (6 bis 128 Zeichen): ")
    zweites = getpass.getpass("Passwort wiederholen: ")
    if erstes != zweites:
        print("Die Passwörter stimmen nicht überein.", file=sys.stderr)
        return 1
    try:
        validate_password(erstes)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    AuthConfigStore(ziel).save(
        AuthConfig(
            password_hash=hash_password(erstes),
            session_secret=secrets.token_urlsafe(48),
            recovery_hash=None,
            must_change_password=True,
            version=1,
        )
    )
    print(f"Startpasswort eingerichtet: {ziel}")
    print("Bitte den Finanzstudio-Dienst jetzt neu starten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
