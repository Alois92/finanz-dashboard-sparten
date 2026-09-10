"""Fachlogik fuer Fixzins-Kredite ohne Datenbankzugriff."""


def verteile_zins(zins_cent: int, anzahl: int) -> list[int]:
    if zins_cent < 0:
        raise ValueError("Zins darf nicht negativ sein")
    if anzahl < 1:
        raise ValueError("Mindestens eine Rate erforderlich")
    grundbetrag, rest = divmod(zins_cent, anzahl)
    return [grundbetrag + (1 if index < rest else 0) for index in range(anzahl)]
