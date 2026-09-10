### POST /api/kategorien

HTTP 201

```json
{"id": 1, "sparte_id": 1, "parent_id": null, "name": "Testkategorie", "richtung": "ausgabe"}
```

### POST /api/konten

HTTP 201

```json
{"id": 1, "name": "Testbank", "art": "bank", "waehrung": "EUR", "sparte_id": 1, "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0}
```

### GET /api/konten

HTTP 200

```json
[{"id": 1, "name": "Testbank", "art": "bank", "waehrung": "EUR", "sparte_id": 1, "iban": null, "bank": null, "kartenendnummer": null, "aktiv": 1, "sortierung": 0, "stand_cent": null, "datenstand": "unbekannt", "letzter_import": null}]
```

### POST /api/import/csv

HTTP 200

```json
{"batch_id": 1, "neu": 2, "dubletten": 0, "gesamt": 2, "saldo_ok": null, "saldo_hinweis": "Keine Saldospalte vorhanden.", "erkannt": {"kodierung": "utf-8", "trennzeichen": ";", "spalten": {"datum": 0, "betrag": 1, "text": 2, "gegenpartei": 3, "iban": null, "waehrung": null, "saldo": null}, "zeilen_gesamt": 2, "zeilen_ungueltig": []}}
```

### POST /api/import/csv

HTTP 200

```json
{"batch_id": 2, "neu": 0, "dubletten": 2, "gesamt": 2, "saldo_ok": null, "saldo_hinweis": "Keine Saldospalte vorhanden.", "erkannt": {"kodierung": "utf-8", "trennzeichen": ";", "spalten": {"datum": 0, "betrag": 1, "text": 2, "gegenpartei": 3, "iban": null, "waehrung": null, "saldo": null}, "zeilen_gesamt": 2, "zeilen_ungueltig": []}}
```

### GET /api/bankumsaetze?bankkonto_id=1

HTTP 200

```json
[{"id": 2, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-02", "valuta": null, "betrag_cent": 25000, "saldo_nachher_cent": null, "text": "Gehalt Maerz", "gegenpartei": "Arbeitgeber GmbH", "iban_gegenpartei": null, "importstatus": "offen", "vorschlag": null}, {"id": 1, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-01", "valuta": null, "betrag_cent": -12345, "saldo_nachher_cent": null, "text": "Einkauf Supermarkt", "gegenpartei": "Handelskette AG", "iban_gegenpartei": null, "importstatus": "offen", "vorschlag": null}]
```

### POST /api/bankumsaetze/1/verbuchen

HTTP 201

```json
{"buchung_id": 1, "typ": "ausgabe", "betrag_cent": 12345, "regel_angelegt": true}
```

### PATCH /api/bankumsaetze/2

HTTP 200

```json
{"id": 2, "importstatus": "ignoriert"}
```

### POST /api/buchungen

HTTP 201

```json
{"id": 2, "sparte_id": 1, "sparte_name": "Privatvermietung", "datum": "2026-04-02", "typ": "ausgabe", "version": 1, "betrag_cent": 500, "zahlungsart": "bank", "belegstatus": "beleg_fehlt", "buchungsstatus": "offen", "text": "Manuell erfasst", "notiz": null, "zahlungsstatus": "verknuepft", "bezahlt_von_sparte_id": null, "zeilen": [{"id": 2, "kategorie_id": 1, "kategorie_name": "Testkategorie", "betrag_cent": 500, "notiz": null, "neutral": 0}], "neutral_cent": 0}
```

### POST /api/import/csv

HTTP 200

```json
{"batch_id": 3, "neu": 1, "dubletten": 0, "gesamt": 1, "saldo_ok": null, "saldo_hinweis": "Keine Saldospalte vorhanden.", "erkannt": {"kodierung": "utf-8", "trennzeichen": ";", "spalten": {"datum": 0, "betrag": 1, "text": 2, "gegenpartei": null, "iban": null, "waehrung": null, "saldo": null}, "zeilen_gesamt": 1, "zeilen_ungueltig": []}}
```

### GET /api/bankumsaetze?bankkonto_id=1

HTTP 200

```json
[{"id": 3, "bankkonto_id": 1, "import_batch_id": 3, "datum": "2026-04-03", "valuta": null, "betrag_cent": -500, "saldo_nachher_cent": null, "text": "Bereits erfasste Zahlung", "gegenpartei": null, "iban_gegenpartei": null, "importstatus": "offen", "vorschlag": null}, {"id": 2, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-02", "valuta": null, "betrag_cent": 25000, "saldo_nachher_cent": null, "text": "Gehalt Maerz", "gegenpartei": "Arbeitgeber GmbH", "iban_gegenpartei": null, "importstatus": "ignoriert"}, {"id": 1, "bankkonto_id": 1, "import_batch_id": 1, "datum": "2026-03-01", "valuta": null, "betrag_cent": -12345, "saldo_nachher_cent": null, "text": "Einkauf Supermarkt", "gegenpartei": "Handelskette AG", "iban_gegenpartei": null, "importstatus": "verbucht"}]
```

### GET /api/bankumsaetze/3/kandidaten

HTTP 200

```json
{"kandidaten": [{"buchung_id": 2, "datum": "2026-04-02", "betrag_cent": -500, "text": "Manuell erfasst", "abstand_tage": 1}]}
```

### GET /api/konten/1/offene-abgleiche

HTTP 200

```json
{"konto_id": 1, "manuelle_anzahl": 1, "manuelle_bewegungen": [{"bewegung_id": 3, "datum": "2026-04-02", "betrag_cent": -500, "text": "Manuell erfasst"}], "umsaetze_anzahl": 1, "offene_umsaetze": [{"bankumsatz_id": 3, "datum": "2026-04-03", "betrag_cent": -500, "text": "Bereits erfasste Zahlung", "kandidaten_anzahl": 1}]}
```

### POST /api/bankumsaetze/3/zuordnen

HTTP 200

```json
{"bankumsatz_id": 3, "buchung_id": 2, "importstatus": "verbucht"}
```

### POST /api/bankumsaetze/3/zuordnung-loesen

HTTP 200

```json
{"bankumsatz_id": 3, "buchung_id": null, "importstatus": "offen"}
```
