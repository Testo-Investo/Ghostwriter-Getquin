"""Sonderangebot: Marc postet im Chat, was der Einkauf schickt – Claude legt es hier ab.

Datei `config/sonderangebot.json` (von Claude geschrieben und gepusht):
    {"id": "2026-10-30-dji", "anlass": "Sonderposten vom Einkauf",
     "artikel": [{"artikel": "…", "ean": "…", "menge": 500, "preis": 199.0}]}

Preise in Euro netto; die Dubai-Liste bekommt sie wie immer in Dollar.
Ablauf wie beim normalen Angebot: Freigabe-Mail an Marc → Antwort FREIGABE → Versand
an alle Listen (ohne Kundenfilter, jeder bekommt dieselben Artikel). Jede `id` wird
nur einmal verschickt.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DATEI = Path("config/sonderangebot.json")


@dataclass
class SonderItem:
    """Hat die Felder, die mailer.build_message von einem Artikel braucht."""
    artikel: str
    ean: str
    verfuegbar: int
    angebotspreis: float
    hersteller: str = ""


def load() -> tuple[str, str, list[SonderItem]] | None:
    if not DATEI.exists():
        return None
    data = json.loads(DATEI.read_text())
    items = [
        SonderItem(a["artikel"], str(a.get("ean", "")), int(a["menge"]), float(a["preis"]),
                   a.get("hersteller") or a["artikel"].split()[0])
        for a in data["artikel"]
    ]
    return data["id"], data.get("anlass", "Sonderangebot"), items
