# Anforderungen

| ID | Anforderung |
|----|-------------|
| REQ-01 | Ein Defekt hat Titel (1 bis 80 Zeichen), Priorität (1 bis 4) und Status. |
| REQ-02 | Statusübergänge nur in Reihenfolge; Rücksprung von „geschlossen“ nur nach „offen“. |
| REQ-03 | Defekte lassen sich nach Status und Priorität filtern. |
| REQ-04 | Ungültige Eingaben liefern HTTP 422 mit verständlicher Meldung. |
| REQ-05 | Löschen eines Defekts entfernt Testdaten-Referenzen nicht stillschweigend. |
| REQ-06 | Testdatensätze mit überlappender Gültigkeit pro Projekt sind unzulässig. |
| REQ-07 | Der XML-Export entspricht dem Schema `results.xsd`. |
| REQ-08 | Die ID-Vergabe ist eindeutig und aufsteigend. |
