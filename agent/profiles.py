"""Kundenprofile aus dem Teams-Verlauf und passende Artikel aus dem Warenbestand.

Pro Kunde: zuletzt aktiv, wie viel geschrieben wird, welche Marken und EANs im
Chat vorkommen. Passend ist ein anbietbarer Artikel, wenn der Kunde seine EAN
selbst geschrieben hat (stark), seine Marke im Chat oft vorkommt (mittel) oder
Marc ihn schon einmal angeboten hat (schwach – Marc schickt Listen an viele).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .stock import StockItem, offerable
from .teams_file import Chat

_EAN = re.compile(r"(?<!\d)\d{12,13}(?!\d)")
# Herstellernamen, die im Chat meist etwas anderes bedeuten
_NOISE_BRANDS = {"blue", "usb-c", "accessory"}


@dataclass
class Profile:
    kunde: str
    chat_id: str
    letzte_nachricht: str
    nachrichten_90t: int
    marken: Counter = field(default_factory=Counter)   # Schlüssel klein geschrieben
    eans_kunde: set[str] = field(default_factory=set)  # vom Kunden geschrieben
    eans_marc: set[str] = field(default_factory=set)   # von Marc angeboten


def _norm_ean(e: str) -> str:
    return e.lstrip("0")


def build_profile(chat: Chat, brands: set[str], months: int = 12) -> Profile:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=30 * months)).isoformat()
    since_90 = (now - timedelta(days=90)).isoformat()
    recent = [m for m in chat.nachrichten if m.zeit >= since]
    marken = Counter()
    eans_kunde, eans_marc = set(), set()
    keys = {b.lower() for b in brands} - _NOISE_BRANDS
    brand_re = {b: re.compile(rf"\b{re.escape(b)}\b", re.I) for b in keys}
    for m in recent:
        (eans_marc if m.von_marc else eans_kunde).update(_norm_ean(e) for e in _EAN.findall(m.text))
        for b, rx in brand_re.items():
            if rx.search(m.text):
                marken[b] += 1
    return Profile(
        kunde=chat.kunde,
        chat_id=chat.id,
        letzte_nachricht=chat.nachrichten[-1].zeit,
        nachrichten_90t=sum(1 for m in chat.nachrichten if m.zeit >= since_90),
        marken=marken,
        eans_kunde=eans_kunde,
        eans_marc=eans_marc,
    )


def brands_from_stock(items: list[StockItem]) -> set[str]:
    return {i.hersteller for i in items if len(i.hersteller) >= 3}


def brand_key(hersteller: str) -> str:
    return hersteller.lower()


def matching_items(profile: Profile, items: list[StockItem], limit: int = 8) -> list[tuple[StockItem, str]]:
    """Passende anbietbare Artikel mit Grund; neue Wareneingänge zuerst (Sheet-Reihenfolge)."""
    scored = []
    for item in offerable(items):
        ean = _norm_ean(item.ean)
        if ean in profile.eans_kunde:
            scored.append((0, item.position, item, "Kunde hat danach gefragt"))
        elif profile.marken.get(brand_key(item.hersteller), 0) >= 3:
            scored.append((1, item.position, item, f"oft {item.hersteller} im Chat"))
        elif ean in profile.eans_marc:
            scored.append((2, item.position, item, "schon mal angeboten"))
    scored.sort(key=lambda s: (s[0], s[1]))
    return [(s[2], s[3]) for s in scored[:limit]]


def _euro(value: float) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def draft_offer(items: list[StockItem]) -> str:
    """Angebot in Marcs Format: Artikel / EAN / Menge x / Preis – Blöcke mit Leerzeile."""
    blocks = [f"{i.artikel}\n{i.ean}\n{i.verfuegbar}x\n{_euro(i.angebotspreis)}" for i in items]
    return "moin\n\n" + "\n\n".join(blocks)
