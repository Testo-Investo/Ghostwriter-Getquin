"""Warenbestand direkt aus Google Sheets laden – für den Server.

Zugang über ein Google-Dienstkonto (Warenbestand nur Lesen; in den Mailinglisten löscht es Rückläufer): Schlüsseldatei unter
GOOGLE_SERVICE_ACCOUNT_FILE, die Tabelle ist mit der Dienstkonto-Adresse geteilt.
Exportiert wird nur das erste Blatt „Warenbestand“ (gid=0) – nie FTP-CONFIG.
"""

import os
from pathlib import Path

import requests
from urllib.parse import quote
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SHEET_ID = "12iVxgJ1iw7i8h3mCTMJwocDi2J2DNOtNDaCicUZ_12Y"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/spreadsheets"]  # Schreiben nur für Rückläufer in den Listen


def fetch_stock_csv(out: Path = Path("data/warenbestand.csv")) -> Path:
    resp = requests.get(
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export",
        params={"format": "csv", "gid": "0"},
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=60,
    )
    resp.raise_for_status()
    if not resp.text.startswith("Hersteller,"):
        raise RuntimeError("Unerwartetes Format – ist das Blatt „Warenbestand“ noch das erste?")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(resp.text)
    tmp.replace(out)  # erst ersetzen, wenn der Abruf vollständig ist
    return out


# Ordner „Ghostwriter Mailinglisten“ in Marcs Google Drive (mit dem Dienstkonto geteilt)
LISTEN_ORDNER = "1Wb8dHpE8gImBG9gGiCrhrp5EoQKkJ3Vq"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token


def _list_files(headers: dict) -> list[dict]:
    resp = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        params={
            "q": f"'{LISTEN_ORDNER}' in parents and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            "fields": "files(id,name)",
        },
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("files", [])


def remove_addresses(adressen: set[str]) -> dict[str, list[str]]:
    """Zeilen mit diesen E-Mail-Adressen aus allen Listen im Ordner löschen.

    Braucht Bearbeiten-Rechte des Dienstkontos auf dem Ordner. Gibt {adresse: [Listen]} zurück."""
    headers = {"Authorization": f"Bearer {_token()}"}
    api = "https://sheets.googleapis.com/v4/spreadsheets"
    gefunden: dict[str, list[str]] = {}
    for f in _list_files(headers):
        meta = requests.get(f"{api}/{f['id']}", params={"fields": "sheets.properties"}, headers=headers, timeout=60)
        meta.raise_for_status()
        blatt = meta.json()["sheets"][0]["properties"]  # Empfänger stehen im ersten Blatt
        werte = requests.get(f"{api}/{f['id']}/values/{quote(chr(39) + blatt['title'] + chr(39))}", headers=headers, timeout=60)
        werte.raise_for_status()
        zeilen = []
        for i, zeile in enumerate(werte.json().get("values", [])):
            treffer = {str(c).strip().lower() for c in zeile} & adressen
            if i and treffer:  # Zeile 0 ist die Überschrift
                zeilen.append(i)
                for a in treffer:
                    gefunden.setdefault(a, []).append(f["name"])
        if not zeilen:
            continue
        loeschen = [{"deleteDimension": {"range": {"sheetId": blatt["sheetId"], "dimension": "ROWS",
                                                    "startIndex": i, "endIndex": i + 1}}}
                    for i in sorted(zeilen, reverse=True)]  # von unten, damit die Nummern stimmen
        resp = requests.post(f"{api}/{f['id']}:batchUpdate", json={"requests": loeschen}, headers=headers, timeout=60)
        if resp.status_code == 403:
            raise RuntimeError("Keine Bearbeiten-Rechte auf den Listen – Ordner mit dem Dienstkonto als „Bearbeiter“ teilen.")
        resp.raise_for_status()
    return gefunden


def fetch_mailing_lists(out_dir: Path = Path("data/mailinglisten")) -> list[Path]:
    """Alle Google-Tabellen im Listen-Ordner als .xlsx holen; lokal gelöschte Listen entfernen.

    Marc pflegt die Listen nur noch in Google Drive – jede Tabelle im Ordner ist eine Liste,
    der Name steuert Sprache („engl“) und Währung („Dubai“)."""
    headers = {"Authorization": f"Bearer {_token()}"}
    files = _list_files(headers)
    if not files:
        raise RuntimeError("Keine Listen im Ordner gefunden – ist er mit dem Dienstkonto geteilt?")
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        data = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{f['id']}/export",
            params={"mimeType": XLSX}, headers=headers, timeout=60,
        )
        data.raise_for_status()
        path = out_dir / f"{f['name']}.xlsx"
        path.write_bytes(data.content)
        saved.append(path)
    for old in out_dir.glob("*.xlsx"):
        if old not in saved:
            old.unlink()  # Liste wurde in Drive gelöscht oder umbenannt
    return sorted(saved)
