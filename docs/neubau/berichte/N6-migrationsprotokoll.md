# N6: Migrationsprotokoll

Migration 012 legt `migrationsprotokoll` an und stellt die ungeklärten Fälle
aus Migration 004 dauerhaft bereit. Erfasst werden ungeklärte Umbuchungen,
nicht eindeutig zuordenbare Barbuchungen sowie Bank- und Kartenbuchungen ohne
zugehörigen Umsatz. Die Einträge enthalten Migration, Zeitpunkt, Fallart,
Objektkennung und einen verständlichen Hinweistext. Eine eindeutige
Schlüsseldefinition verhindert Doppeleinträge bei wiederholtem Nachzug.

Der angemeldete Lese-Endpunkt `GET /api/betrieb/migrationsprotokoll` verlangt
wie fachliche Endpunkte eine gültige Bereichsdependency. Das Protokoll ist
betriebsweit und wird daher nicht nach Bereich gefiltert; die Dependency stellt
den gültigen Betriebsbereich und die Zugriffsschranke sicher.

Für Datenbanken, auf denen Migration 004 bereits vor 012 erfolgreich gelaufen
ist, wird 004 nicht rückwirkend verändert. Migration 012 rekonstruiert die aus
dem Bestandszustand erkennbaren ungeklärten Fälle und trägt sie einmalig nach.
Falls ein Fall aus dem damaligen Zustand nicht mehr erkennbar ist, kann er
nicht nachträglich rekonstruiert werden. Bei regulären Läufen, in denen die
Protokolltabelle bereits existiert, schreibt 004 neue Fälle zusätzlich zum
bestehenden Log direkt in die Tabelle.
