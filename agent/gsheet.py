"""Warenbestand direkt aus Google Sheets laden – für den Server.

Zugang über ein Google-Dienstkonto (nur Lesen): Schlüsseldatei unter
GOOGLE_SERVICE_ACCOUNT_FILE, die Tabelle ist mit der Dienstkonto-Adresse geteilt.
Exportiert wird nur das erste Blatt „Warenbestand“ (gid=0) – nie FTP-CONFIG.
"""

import os
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SHEET_ID = "12iVxgJ1iw7i8h3mCTMJwocDi2J2DNOtNDaCicUZ_12Y"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


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


def fetch_mailing_lists(out_dir: Path = Path("data/mailinglisten")) -> list[Path]:
    """Alle Google-Tabellen im Listen-Ordner als .xlsx holen; lokal gelöschte Listen entfernen.

    Marc pflegt die Listen nur noch in Google Drive – jede Tabelle im Ordner ist eine Liste,
    der Name steuert Sprache („engl“) und Währung („Dubai“)."""
    headers = {"Authorization": f"Bearer {_token()}"}
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
    files = resp.json().get("files", [])
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
