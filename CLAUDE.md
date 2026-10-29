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
  bevorzugt anbieten. **„Neu“ = Wareneingang der letzten 7 Tage** → stehen im
  Angebot immer oben. Kommt neue Ware rein (neu/aufgestockt), wird sofort ein
  Angebot mit diesen Artikeln und Mengen vorbereitet.
  Code: `agent/watch.py` (Snapshots + Änderungen), `agent/offer.py` (Angebot).
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
- **Kunden:** Marcs Bestandskunden mit langem Chatverlauf in Teams. Teams-Datenexport
  (`messages.json`, ~82.000 Nachrichten, 107 Einzelchats) liegt lokal unter
  `data/teams_export/` – nie committen. Stilprofil: `docs/STILPROFIL.md`
  (kurz, „du“, „moin“, Angebot als Blöcke Artikel/EAN/Menge x/Preis).
  **Marcs Hauptziel: jeden Morgen pro Kunde ein frisches, kopierfertiges Angebot.**
  Gleiche Produkte für mehrere Kunden sind ausdrücklich ok. Umsetzung im Dashboard
  („Angebote für heute“): je Kunde bis 8 passende Artikel (neu zuerst), aufgefüllt
  mit neuen Wareneingängen auf 10, volle verfügbare Menge. Identische Angebote
  werden zu einer Karte mit allen Kundennamen zusammengefasst. Kundenprofile kommen
  aus `python -m agent.cli profiles` → `data/kunden.json` (als Datei ins Dashboard
  hochgeladen; nach jedem neuen Teams-Export neu erzeugen und ersetzen).
- **E-Mail-Angebote (nächster Schritt):** Marc verschickt heute Serienbriefe mit
  Outlook + Excel-Liste an Webshop-Kunden; Postfach liegt bei **IONOS**. Ersatz:
  `agent/mailer.py` – eine eigene Mail pro Empfänger (kein BCC), Vorschau zuerst,
  Testversand an Marc, dann Versand mit Pause zwischen den Mails, Abmeldeliste.
  SMTP (smtp.ionos.de:587) ist aus der Claude-Cloud-Umgebung nicht erreichbar →
  Versand vom Server oder Marcs Rechner; Zugangsdaten nur als Secret dort.
  Marcs vier Serienbrief-Listen (deutsch, englisch, englisch Messe, Dubai; 182
  Adressen) liegen als **Google-Tabellen im Drive-Ordner „Ghostwriter
  Mailinglisten“** (ID `1Wb8dHpE8gImBG9gGiCrhrp5EoQKkJ3Vq`, mit dem Dienstkonto
  `ghostwriter-leser@psyched-ray-513112-i7.iam.gserviceaccount.com` geteilt).
  Marc pflegt sie nur noch dort; `fetch-lists` holt sie vor jedem Versand nach
  `data/mailinglisten/` (nie committen). Dubai-Liste am 29.10. bereinigt:
  Namen waren gegenüber den Adressen verrutscht → nur eindeutig zuordenbare Namen
  behalten (Rest „Hi,“), hotmail.conn/gmait.com korrigiert, 4 unlesbare Adressen
  entfernt (pradotechnotogv, cfelativity, iackys, amtaroupinc); alte Fassung liegt
  als „… (ALT, fehlerhaft)“ außerhalb des Ordners. Englisch,
  wenn der Dateiname „engl“ enthält; Spalte „Produkt(e)“ = Marken/Kategorien.
  **Marcs Vorgaben:** Absender **marc@neobution.com**, Signatur folgt (→
  `config/signatur.txt` + `config/signatur_logo.png`). **5–10 Artikel pro Mail.** **Dubai-Liste in US-Dollar**
  zum EZB-Tageskurs (aufgerundet), Lieferbedingung „ex works Germany“ für alle
  englischen Listen. **Versand immer dann, wenn neue Ware reinkommt** →
  `mail-neu`: stündlich prüfen, verschickt nur Artikel, die noch in keiner Mail
  standen (Merkliste `data/mail_state.json`), höchstens eine Mail pro Tag.
  **Freigabe vor jedem Versand (Marcs Wunsch):** `mail-neu` schickt zuerst eine
  Freigabe-Mail an Marc ([GW-…] im Betreff, je Liste eine Beispiel-Mail im Anhang);
  erst wenn Marc mit „FREIGABE“ antwortet (per IMAP imap.ionos.de gelesen), geht
  der Versand raus; „STOPP“ verwirft, ohne Antwort verfällt der Antrag nach 3 Tagen
  (`agent/freigabe.py`). **Marc will Änderungen nur hier im Chat machen, nie per
  Mail-Antwort** (Tippfehler-Risiko); die Antwort bleibt nur FREIGABE/STOPP. Eine
  Freigabe gilt nur für genau den Code-Stand (git HEAD) und Bestand, den Marc gesehen
  hat; nach jedem Push wird ein offener Antrag ungültig und neu verschickt. Der Server
  holt Änderungen selbst (`git pull` am Anfang von `run_hourly.sh`).
  **Sonderangebote (manuell):** Marc postet im Chat, was der Einkauf schickt (z. B.
  WhatsApp). Claude schreibt daraus `config/sonderangebot.json` mit neuer `id`
  (`{"id","anlass","artikel":[{"artikel","ean","menge","preis"}]}`, Preise € netto),
  zeigt Marc die Artikel zur Kontrolle, committet und pusht. Der Server schickt
  beim nächsten Lauf (Mo–Fr 7–18 Uhr) eine Freigabe-Mail [SO-…]; nach FREIGABE geht
  es an alle Listen (alle bekommen dieselben Artikel, Dubai in $). Jede `id` nur
  einmal; zählt nicht gegen „eine Mail pro Tag“ (`agent/sonder.py`, `mail-sonder`).
  **Postfach (stündlich, `postfach`):** Abwesenheitsnotizen → IMAP-Ordner
  „Abwesenheitsnotizen“; Rückläufer (dauerhaft, 5.x.x) → Adresse sofort aus der
  Google-Tabelle löschen (Dienstkonto braucht dafür **Bearbeiter** auf dem Listen-Ordner),
  zusätzlich gesperrt in `data/unzustellbar.txt`, Mail in Ordner „Unzustellbar“,
  Info-Mail an Marc mit den Adressen. Nach jedem Versand **Versand-Bericht** an Marc
  („… verschickt – x von y Mails raus“) – Marc muss nicht ins Server-Log (journalctl).
  **Mengen ab 1.000 Stück als „1.000+“** (Mail, Dashboard,
  Teams-Entwurf). Deutsch: „Preise netto, innerhalb Deutschlands frei Haus“,
  Ausland/Englisch: „Prices net, ex works Germany“.
- **Auftragssoftware:** weclapp (REST-API mit API-Token).
- **Betrieb:** Keine VM auf Marcs PC. **Server: Hetzner Cloud CPX02, Nürnberg,
  Ubuntu 26.04, IPv4 2.31.88.120, Name „ghostwriter“** (Marc loggt sich per
  PowerShell `ssh root@2.31.88.120` ein; die Browser-Konsole kann nicht einfügen).
  Code unter `/opt/ghostwriter` (Clone dieses Repos), Einrichtung mit
  `deploy/install.sh` (fragt IONOS-Passwort unsichtbar ab → `.env`, chmod 600),
  stündlicher Lauf per systemd-Timer `ghostwriter.timer` (Mo–Fr 7–18 Uhr,
  `deploy/run_hourly.sh`: `fetch-stock` + `mail-neu`). Google-Zugang auf dem
  Server über Dienstkonto, Schlüssel in `config/secrets/google.json` (nie committen).
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
- `agent/offer.py` – Angebot bauen (neue Wareneingänge oben) und Sofort-Angebot bei neuer Ware
- `dashboard/cockpit.html` – Seite des Dashboards „Ghostwriter Vertriebs-Cockpit“
  (https://claude.ai/artifact/8RveMqVctyypA3NCDRyHdQ, liest den Warenbestand live über
  Google Drive; die Regeln stehen dort als Berechnung). Bei Regeländerungen beide anpassen.
- `agent/teams_file.py` – Teams-Datenexport (privates Teams) einlesen, Namen auflösen
- `agent/profiles.py` – Kundenprofile (Marken, EANs) und passende Artikel, Angebotsentwurf in Marcs Format
- `agent/mailer.py` – Angebots-Serienmail über IONOS (Vorschau, Test, Versand, Protokoll)
- `agent/freigabe.py` – Freigabe per Antwort-Mail (Antrag an Marc, IMAP-Prüfung der Antwort)
- `agent/sonder.py` – Sonderangebot aus `config/sonderangebot.json` (aus dem Chat)
- `agent/postfach.py` – Abwesenheitsnotizen wegsortieren, Rückläufer aus den Listen löschen
- `agent/cli.py` – Einstieg: `python -m agent.cli <befehl>`
- `data/` – lokale Exporte, nie committen (enthält Kundendaten)
