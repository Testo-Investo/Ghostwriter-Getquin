# Ghostwriter – Vertriebsagent für Marc Knieb

Ziel: Ein Agent, der im Namen von Marc Knieb (Vertrieb) Kunden passende Produkte
anbietet, antwortet, verhandelt und Aufträge in weclapp anlegt – plus ein
Dashboard, das jede Aktion des Agenten nachvollziehbar macht.

## Festgehaltene Entscheidungen (vom Nutzer bestätigt)

- **Datenschutz / Freigaben: geklärt.** Marc ist Admin im Microsoft-365-Tenant
  und hat vollen Zugriff auf alle beteiligten Programme. Nicht erneut nachfragen.
- **Produktliste:** Excel-Datei auf einem geteilten Microsoft-Laufwerk
  (SharePoint/OneDrive) → Zugriff über Microsoft Graph.
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

- Kunden in Teams extern (andere Firmen) oder im eigenen Tenant?
- Verhandlungsregeln: max. Rabatt, Mindestmarge, Freigabegrenze in €
- Angebotsfrequenz pro Kunde
- KI-Hinweis in Nachrichten vs. Freigabe jeder Nachricht (EU AI Act Art. 50)

## Struktur

- `agent/graph.py` – Microsoft-Graph-Client (MSAL, Token-Cache)
- `agent/catalog.py` – Produkt-Excel vom geteilten Laufwerk laden
- `agent/teams_export.py` – Teams-Chatverläufe lokal nach `data/` exportieren
- `agent/cli.py` – Einstieg: `python -m agent.cli <befehl>`
- `data/` – lokale Exporte, nie committen (enthält Kundendaten)
