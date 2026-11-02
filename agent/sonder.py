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
    artikel_en: str = ""   # englischer Name für die englischen Listen (sonst wie artikel)
    gruppe: str = ""       # Rubrik-Überschrift, z. B. „IT & Notebooks“
    gruppe_en: str = ""


def load() -> tuple[str, str, list[SonderItem]] | None:
    if not DATEI.exists():
        return None
    data = json.loads(DATEI.read_text())
    items = [
        SonderItem(a["artikel"], str(a.get("ean", "")), int(a["menge"]), float(a["preis"]),
                   a.get("hersteller") or a["artikel"].split()[0], a.get("artikel_en", ""),
                   a.get("gruppe", ""), a.get("gruppe_en", ""))
        for a in data["artikel"]
    ]
    return data["id"], data.get("anlass", "Sonderangebot"), items


def _daten() -> dict:
    return json.loads(DATEI.read_text()) if DATEI.exists() else {}


def versand_ab() -> str:
    """Frühester Versand, z. B. „2026-11-03T09:00“ (leer = sofort nach Freigabe)."""
    return _daten().get("versand_ab", "")


def ersetzt_tagesangebot(tag: str) -> bool:
    """Marc: an diesem Tag nur das Sonderangebot, kein normales Tagesangebot."""
    d = _daten()
    return bool(d.get("ersetzt_tagesangebot")) and d.get("versand_ab", "")[:10] == tag


def texte() -> dict | None:
    """Eigene Texte des Sonderangebots je Sprache: betreff, intro, outro, zusatz (optional)."""
    if not DATEI.exists():
        return None
    return json.loads(DATEI.read_text()).get("texte")


# Pflichtartikel: Marc sagt im Chat „am Montag auf jeden Fall X rein“ – steht dann im
# Tagesangebot (mail-neu) an diesem Datum bei jedem Kunden ganz oben, mit Marcs Menge/Preis.
PFLICHT = Path("config/pflichtartikel.json")


def _item(a: dict) -> SonderItem:
    return SonderItem(a["artikel"], str(a.get("ean", "")), int(a["menge"]), float(a["preis"]),
                      a.get("hersteller") or a["artikel"].split()[0])


def pflicht_fuer(tag: str) -> list[dict]:
    """Pflichtartikel für ein Datum (JJJJ-MM-TT) als einfache Dicts (so kommen sie in den Antrag)."""
    if not PFLICHT.exists():
        return []
    return [a for a in json.loads(PFLICHT.read_text()).get("artikel", []) if a.get("datum") == tag]


def als_items(eintraege: list[dict]) -> list[SonderItem]:
    return [_item(a) for a in eintraege]
