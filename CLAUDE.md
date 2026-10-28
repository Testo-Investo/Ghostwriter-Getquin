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
- **Hauptquelle Produkte: Google Sheet „Warenbestand (automated)“**
  (ID `12iVxgJ1iw7i8h3mCTMJwocDi2J2DNOtNDaCicUZ_12Y`, Eigentümer Florian Robrecht,
  wird automatisch aktualisiert). Blatt „Warenbestand“ (~300 Artikel): Hersteller,
  Artikel, EAN, Idealo EK, ⌀ EK, Letzter/⌀ VK, Lager, Verfügbar, Bestandswert,
  Bestand pro Lager (Bergkamen, Bochum, Dortmund, Dropshipping, Hongkong,
  Langenbach, Unna), MPN, idealo_id – danach **eine Preisspalte pro Kunde**
  (~70 B2B-Händler, z. B. Bechtle, Galaxus, notebooksbilliger, AXRO).
  Weitere Blätter: Transportschaeden, Alte Artikel, Self-Order-Log (bestehendes
  Bestellportal, legt bereits Aufträge in weclapp an).
  **Marcs Regeln:** Kunde sieht Artikel + EAN (+ Angebotspreis). Intern: ⌀ EK als
  Untergrenze, „Letzter VK“ als Orientierung für den Preis. Nur „Verfügbar“ > 0
  anbieten, alles mit 0 ignorieren. Andere Spalten vorerst nicht relevant.
  **Der Kunde sieht niemals den EK.** Preis = Letzter VK; ohne letzten VK
  ⌀ EK + 10 %. Artikel mit letztem VK unter ⌀ EK werden weggelassen.
  **Alle Microsoft-Surface-Produkte werden nie angeboten.**
  **Stündlich aktualisiert, auch die Mengen.** Sortierung: oben stehen die neuesten
  Wareneingänge (Spalte „Letzter WE“). Diese Artikel immer genau beobachten und
  bevorzugt anbieten. Code: `agent/watch.py` (Snapshots + Änderungen je Abruf).
  Code: `agent/stock.py`.
  **Blatt „FTP-CONFIG“ enthält Zugangsdaten im Klartext – niemals auslesen,
  speichern, loggen oder ins Repo übernehmen.** Der Agent liest nur „Warenbestand“.
- **Zweite Tabelle „Angebote“**: Kein OneDrive, sondern ein Google Sheet
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

- Welche der ~70 Händler im Warenbestand sind Marcs Kunden in Teams?
- Rolle der Tabelle „Angebote“ neben dem Warenbestand?
- Bestellportal/Self-Order von Florian für Aufträge mitnutzen statt eigener weclapp-Anbindung?
- Dauerzugriff aufs Google Sheet für den Server: Google-Dienstkonto (nur Lesen)
- Kanal für das automatische Senden: Firmen-Teams (über IT), E-Mail oder WhatsApp Business?
- Hat die Firma Microsoft 365 mit IT-Admin?
- Verhandlungsregeln: max. Rabatt beim Verhandeln, Freigabegrenze in €
- Angebotsfrequenz pro Kunde
- KI-Hinweis in Nachrichten vs. Freigabe jeder Nachricht (EU AI Act Art. 50)

## Struktur

- `agent/graph.py` – Microsoft-Graph-Client (MSAL, Token-Cache)
- `agent/catalog.py` – Produktliste laden (lokale Datei oder Freigabelink; Google Sheet folgt)
- `agent/teams_export.py` – Teams-Chatverläufe lokal nach `data/` exportieren
- `agent/stock.py` – Warenbestand parsen und filtern (Verfügbar > 0)
- `agent/watch.py` – stündliche Snapshots, Änderungen (neu, aufgestockt, geht weg, Preis), neue Wareneingänge
- `agent/cli.py` – Einstieg: `python -m agent.cli <befehl>`
- `data/` – lokale Exporte, nie committen (enthält Kundendaten)
