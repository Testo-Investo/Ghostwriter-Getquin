# Azure-App-Registrierung (ca. 10 Minuten)

Damit der Agent ohne dein Passwort auf Teams und die Excel-Liste zugreifen kann,
legst du einmalig eine App in deinem Microsoft-365-Tenant an.

## 1. App anlegen

1. <https://entra.microsoft.com> öffnen → **Anwendungen → App-Registrierungen → Neue Registrierung**
2. Name: `Ghostwriter Vertriebsagent`
3. Kontotypen: **Nur Konten in diesem Organisationsverzeichnis**
4. Umleitungs-URI: leer lassen → **Registrieren**

Auf der Übersichtsseite notieren:
- **Anwendungs-ID (Client)** → `AZURE_CLIENT_ID`
- **Verzeichnis-ID (Mandant)** → `AZURE_TENANT_ID`

## 2. Device-Code-Login erlauben

**Authentifizierung → Erweiterte Einstellungen → Öffentliche Clientflows zulassen: Ja** → Speichern

## 3. Berechtigungen

**API-Berechtigungen → Berechtigung hinzufügen → Microsoft Graph → Delegierte Berechtigungen:**

| Berechtigung | Wofür |
|---|---|
| `User.Read` | Wer bin ich (Marc) |
| `Chat.ReadWrite` | Teams-Chats lesen (Phase 1) und später senden (Phase 2) |
| `Files.Read.All` | Produkt-Excel vom geteilten Laufwerk lesen |
| `Sites.Read.All` | Zugriff auf SharePoint-Bibliotheken |
| `offline_access` | Login bleibt gespeichert |

Danach **Administratorzustimmung für <Tenant> erteilen** klicken (du bist Admin).

> Delegiert heißt: Der Agent sieht nur, was du selbst siehst, und handelt als du.
> Kein Client-Secret nötig.

## 4. Excel-Link

Excel-Datei auf dem geteilten Laufwerk → **Teilen → Link kopieren** → in
`.env` als `PRODUCT_EXCEL_SHARE_URL` eintragen.

## 5. Erster Test

```bash
cp .env.example .env        # Werte eintragen
pip install -r requirements.txt
python -m agent.cli whoami   # zeigt einen Code → auf microsoft.com/devicelogin eingeben
python -m agent.cli catalog  # liest die Produktliste
python -m agent.cli export-chats
```
