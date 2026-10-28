"""Stündliche Beobachtung des Warenbestands: Snapshots speichern und vergleichen.

Erkennt pro Lauf, was sich seit dem letzten Abruf geändert hat – vor allem neue
Wareneingänge, die oben in der Liste auftauchen und zuerst angeboten werden sollen.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .stock import StockItem, offerable

SNAPSHOT_DIR = Path("data/snapshots")
NEU_TAGE = 7  # Wareneingang der letzten 7 Tage gilt als „neu“ (Marc)


@dataclass
class Event:
    art: str          # NEU_IM_LAGER, AUFGESTOCKT, VERKAUFT_SICH, AUSVERKAUFT, PREIS
    ean: str
    artikel: str
    vorher: float | int | None
    jetzt: float | int | None

    def text(self) -> str:
        if self.art == "NEU_IM_LAGER":
            return f"🆕 Neu im Lager: {self.artikel} – {self.jetzt} Stk"
        if self.art == "AUFGESTOCKT":
            return f"📦 Aufgestockt: {self.artikel} {self.vorher} → {self.jetzt} Stk"
        if self.art == "VERKAUFT_SICH":
            return f"🔥 Geht weg: {self.artikel} {self.vorher} → {self.jetzt} Stk"
        if self.art == "AUSVERKAUFT":
            return f"⛔ Nicht mehr anbietbar: {self.artikel}"
        return f"💶 Preis geändert: {self.artikel} {self.vorher:.2f} € → {self.jetzt:.2f} €"


def save_snapshot(items: list[StockItem], at: datetime | None = None) -> Path:
    at = at or datetime.now()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{at:%Y-%m-%d_%H%M}.json"
    path.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False))
    return path


def load_latest_snapshot(before: Path | None = None) -> list[StockItem] | None:
    files = sorted(SNAPSHOT_DIR.glob("*.json")) if SNAPSHOT_DIR.exists() else []
    if before is not None:
        files = [f for f in files if f.name < before.name]
    if not files:
        return None
    return [StockItem(**d) for d in json.loads(files[-1].read_text())]


def diff(previous: list[StockItem], current: list[StockItem]) -> list[Event]:
    """Vergleicht nur anbietbare Artikel (Marcs Regeln), Schlüssel ist die EAN."""
    before = {i.ean: i for i in offerable(previous)}
    now = {i.ean: i for i in offerable(current)}
    events = []
    for item in sorted(now.values(), key=lambda i: i.position):
        old = before.get(item.ean)
        if old is None:
            events.append(Event("NEU_IM_LAGER", item.ean, item.artikel, None, item.verfuegbar))
            continue
        if item.verfuegbar > old.verfuegbar:
            events.append(Event("AUFGESTOCKT", item.ean, item.artikel, old.verfuegbar, item.verfuegbar))
        elif item.verfuegbar < old.verfuegbar:
            events.append(Event("VERKAUFT_SICH", item.ean, item.artikel, old.verfuegbar, item.verfuegbar))
        if old.angebotspreis != item.angebotspreis:
            events.append(Event("PREIS", item.ean, item.artikel, old.angebotspreis, item.angebotspreis))
    for ean, old in before.items():
        if ean not in now:
            events.append(Event("AUSVERKAUFT", ean, old.artikel, old.verfuegbar, 0))
    return events


def fresh_arrivals(items: list[StockItem], today: date | None = None, days: int = NEU_TAGE) -> list[StockItem]:
    """Anbietbare Artikel mit Wareneingang in den letzten `days` Tagen, in Sheet-Reihenfolge."""
    today = today or date.today()
    cutoff = today - timedelta(days=days)
    return sorted(
        (i for i in offerable(items) if i.wareneingang and i.wareneingang >= cutoff),
        key=lambda i: i.position,
    )
