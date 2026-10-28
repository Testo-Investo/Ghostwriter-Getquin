# Ghostwriter – Vertriebsagent für Marc Knieb

Ziel: Ein Agent, der im Namen von Marc Knieb (Vertrieb) Kunden passende Produkte
anbietet, antwortet, verhandelt und Aufträge in weclapp anlegt – plus ein
Dashboard, das jede Aktion des Agenten nachvollziehbar macht.

## Festgehaltene Entscheidungen (vom Nutzer bestätigt)

- **Datenschutz: geklärt.** Nicht erneut nachfragen.
- **Korrektur:** Marc ist **kein** Microsoft-Admin. Für die Kunden nutzt er
  **Teams mit seinem privaten Microsoft-Konto** (Teams kostenlos). Graph-Chat-APIs
  gibt es dafür nicht → Chatverlauf per Teams-Datenexport (Datei) statt API.
  Für das automatische Senden ist noch zu klären, über welchen Kanal das läuft.
- **Produktliste (Korrektur):** Kein OneDrive, sondern das **Google Sheet „Angebote“**
  (ID `1wlUxlXhqmIwCJMDHvqwRws-Hh1p2oruKoFRokIckLXU`, Eigentümer Robert Grüner,
  mit Marc geteilt). Ändert sich stündlich → automatischer Abruf, kein Upload.
  Viele Tabellenblätter (u. a. Robert ~17.000 Zeilen, Joel, Andy, Moe, Alex,
  Richard, Leifheit, Samsung, NeobutionLLC). Typische Spalten: Marke, Produkt,
  Artikelnr., EAN, EK, Menge, Order, Lieferzeit, Datum, Idealo-Preise, Differenz %,
  Amazon, sowie Spalten pro Vertriebler (Rafa, Mogge, Marc, Alex).
  Der Agent liest nur, schreibt nie in diese Tabelle.
- **Kunden:** Marcs Bestandskunden mit langem Chatverlauf in Teams.
- **Auftragssoftware:** weclapp (REST-API mit API-Token).
- **Betrieb:** Keine VM auf Marcs PC. Agent läuft später auf einem Cloud-Server
  (EU-Region) und spricht ausschließlich über APIs mit den Systemen.
- **Zugangsdaten:** Niemals Passwörter im Chat oder im Repo. Azure-App +
  OAuth (Device-Code-Login) für Graph, API-Token für weclapp, alles in `.env`.

## Phasen

0. Fundament: Azure-App-Registrierung, Repo, Server
1. **Lesen & Lernen (aktuell):** Produktkatalog laden, Teams-Chats exportieren,
   Stilprofil und Kundenprofile ableiten – es wird nichts gesendet.
2. Senden mit Freigabe über das Dashboard
3. Teilautonomie innerhalb fester Regeln (Rabattgrenzen, Auftragswert)
4. Weitere Kanäle: Outlook-E-Mail, WhatsApp Business API

## Offene Punkte an Marc

- Welche Tabellenblätter/Zeilen sind „Marcs“ Angebote? Bedeutung der Spalte „Marc“?
- Dauerzugriff aufs Google Sheet für den Server: Google-Dienstkonto (nur Lesen)
- Kanal für das automatische Senden: Firmen-Teams (über IT), E-Mail oder WhatsApp Business?
- Hat die Firma Microsoft 365 mit IT-Admin?
- Verhandlungsregeln: max. Rabatt, Mindestmarge, Freigabegrenze in €
- Angebotsfrequenz pro Kunde
- KI-Hinweis in Nachrichten vs. Freigabe jeder Nachricht (EU AI Act Art. 50)

## Struktur

- `agent/graph.py` – Microsoft-Graph-Client (MSAL, Token-Cache)
- `agent/catalog.py` – Produktliste laden (lokale Datei oder Freigabelink; Google Sheet folgt)
- `agent/teams_export.py` – Teams-Chatverläufe lokal nach `data/` exportieren
- `agent/cli.py` – Einstieg: `python -m agent.cli <befehl>`
- `data/` – lokale Exporte, nie committen (enthält Kundendaten)
