"""Angebot aus dem Warenbestand zusammenstellen – was der Kunde zu sehen bekommt.

Aufbau: neue Wareneingänge (letzte 7 Tage, Reihenfolge wie im Sheet) oben,
danach der restliche anbietbare Bestand. Der Kunde sieht Artikel, EAN,
verfügbare Menge und Preis – niemals den EK.

Sofort-Angebot: Kommt bei einem Abruf neue Ware herein (neu im Lager oder
aufgestockt) und ist sie frischer Wareneingang, wird direkt ein Angebot nur
mit diesen Artikeln vorbereitet.
"""

from dataclasses import dataclass
from datetime import date

from .stock import StockItem, offerable
from .watch import Event, fresh_arrivals


@dataclass
class OfferLine:
    artikel: str
    ean: str
    menge: int
    preis: float
    neu: bool


def _line(item: StockItem, neu: bool) -> OfferLine:
    return OfferLine(item.artikel, item.ean, item.verfuegbar, item.angebotspreis, neu)


def build_offer(items: list[StockItem], today: date | None = None, max_rest: int | None = None) -> list[OfferLine]:
    fresh = fresh_arrivals(items, today)
    fresh_eans = {i.ean for i in fresh}
    rest = [i for i in offerable(items) if i.ean not in fresh_eans]
    rest.sort(key=lambda i: i.position)
    if max_rest is not None:
        rest = rest[:max_rest]
    return [_line(i, True) for i in fresh] + [_line(i, False) for i in rest]


def instant_offer(items: list[StockItem], events: list[Event], today: date | None = None) -> list[OfferLine]:
    """Nur frische Wareneingänge, die in diesem Abruf neu oder aufgestockt sind."""
    triggered = {e.ean for e in events if e.art in ("NEU_IM_LAGER", "AUFGESTOCKT")}
    return [_line(i, True) for i in fresh_arrivals(items, today) if i.ean in triggered]


def _euro(value: float) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def render_text(lines: list[OfferLine]) -> str:
    """Neutrale Rohfassung – Ton und Anrede kommen später aus Marcs Stilprofil."""
    out = []
    neu = [l for l in lines if l.neu]
    rest = [l for l in lines if not l.neu]
    for title, block in (("Neu reingekommen", neu), ("Weiter verfügbar", rest)):
        if not block:
            continue
        out.append(f"{title}:")
        out += [f"- {l.artikel} | EAN {l.ean} | {l.menge} Stk | {_euro(l.preis)}" for l in block]
        out.append("")
    return "\n".join(out).strip()
