"""Richtet das Finanzstudio-Startpasswort ohne Klartextspeicherung ein."""
from __future__ import annotations

import argparse
import dataclasses
import getpass
import os
import pathlib
import secrets
import sys

APP_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from app.auth import hash_password  # noqa: E402
from app.auth_store import (  # noqa: E402
    AuthConfig,
    AuthConfigStore,
    generate_recovery_code,
    validate_password,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Richtet das Finanzstudio-Startpasswort ein oder erneuert nur den Recovery-Code."
    )
    parser.add_argument(
        "--nur-recovery-code",
        action="store_true",
        help=(
            "Passwort und Sitzungsgeheimnis unveraendert lassen, nur einen neuen "
            "Wiederherstellungscode erzeugen und speichern."
        ),
    )
    return parser.parse_args(argv)


def _nur_recovery_code(ziel: pathlib.Path) -> int:
    store = AuthConfigStore(ziel)
    try:
        bestehend = store.load()
    except FileNotFoundError:
        print(
            f"Keine bestehende Auth-Datei unter {ziel} gefunden. "
            "Ohne bestehendes Passwort kann kein Recovery-Code erzeugt werden.",
            file=sys.stderr,
        )
        return 1

    if bestehend.recovery_hash is not None:
        print(
            "Achtung: Es existiert bereits ein Wiederherstellungscode. "
            "Dieser wird durch den neuen Code ungueltig gemacht."
        )
    else:
        print("Es ist noch kein Wiederherstellungscode hinterlegt.")

    recovery_code = generate_recovery_code()
    neue_config = dataclasses.replace(
        bestehend,
        recovery_hash=hash_password(recovery_code),
    )
    store.save(neue_config)

    print(f"Wiederherstellungscode fuer {ziel} erneuert.")
    print("Passwort und must_change_password bleiben unveraendert.")
    _recovery_code_ausgeben(recovery_code)
    print("Bitte den Finanzstudio-Dienst jetzt neu starten.")
    return 0


def _recovery_code_ausgeben(recovery_code: str) -> None:
    print()
    print("=" * 60)
    print("WIEDERHERSTELLUNGSCODE - JETZT SOFORT SICHER NOTIEREN")
    print("=" * 60)
    print(recovery_code)
    print("=" * 60)
    print(
        "Dieser Code wird nur dieses eine Mal angezeigt und kann spaeter "
        "nicht aus der Auth-Datei zurueckgelesen werden. Ohne diesen Code "
        "ist die 'Passwort vergessen'-Funktion wirkungslos."
    )
    print()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ziel = pathlib.Path(
        os.environ.get("FINANZ_AUTH_FILE", APP_DIR / "instance" / "auth.json")
    )

    if args.nur_recovery_code:
        return _nur_recovery_code(ziel)

    if ziel.exists():
        print(
            f"Achtung: {ziel} existiert bereits und wird ueberschrieben. "
            "Ein eventuell vorhandener alter Wiederherstellungscode wird dadurch ungueltig."
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

    recovery_code = generate_recovery_code()
    AuthConfigStore(ziel).save(
        AuthConfig(
            password_hash=hash_password(erstes),
            session_secret=secrets.token_urlsafe(48),
            recovery_hash=hash_password(recovery_code),
            must_change_password=True,
            version=1,
        )
    )
    print(f"Startpasswort eingerichtet: {ziel}")
    _recovery_code_ausgeben(recovery_code)
    print("Bitte den Finanzstudio-Dienst jetzt neu starten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
