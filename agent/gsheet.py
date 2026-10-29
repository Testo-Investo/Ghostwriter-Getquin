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
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], scopes=SCOPES
    )
    creds.refresh(Request())
    resp = requests.get(
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export",
        params={"format": "csv", "gid": "0"},
        headers={"Authorization": f"Bearer {creds.token}"},
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
