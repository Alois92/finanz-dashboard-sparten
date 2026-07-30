"""Richtet das Finanzstudio-Passwort ein, ohne es im Klartext zu speichern."""
from __future__ import annotations

import getpass
import json
import os
import pathlib
import secrets
import sys
import tempfile

APP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from app.auth import hash_password  # noqa: E402


def main() -> int:
    ziel = APP_DIR / "instance" / "auth.json"
    print("Finanzstudio-Anmeldung einrichten")
    print("Das Passwort wird verdeckt eingegeben und niemals im Klartext gespeichert.")
    erstes = getpass.getpass("Neues Passwort (mindestens 12 Zeichen): ")
    zweites = getpass.getpass("Passwort wiederholen: ")
    if erstes != zweites:
        print("Die Passwörter stimmen nicht überein.", file=sys.stderr)
        return 1
    try:
        password_hash = hash_password(erstes)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    ziel.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "password_hash": password_hash,
        "session_secret": secrets.token_urlsafe(48),
    }
    handle, temp_name = tempfile.mkstemp(
        prefix="auth-", suffix=".tmp", dir=ziel.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, ziel)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    print(f"Anmeldung eingerichtet: {ziel}")
    print("Bitte den Finanzstudio-Dienst jetzt neu starten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
