"""Warenbestand aus dem Google Sheet „Warenbestand (automated)“ – Marcs Regeln.

- Für den Kunden:      Artikel, EAN
- Interne Kalkulation: ⌀ EK (Untergrenze), Letzter VK (Orientierung für den VK)
- Nur Artikel mit „Verfügbar“ > 0 sind anbietbar.
- Preis: Letzter VK; ohne letzten VK ⌀ EK + 10 %.
- Weggelassen: Letzter VK unter ⌀ EK, oder kein ⌀ EK vorhanden.

Gelesen wird ausschließlich das erste Blatt „Warenbestand“ (CSV-Export).
"""

import csv
import io
import math
import re
from dataclasses import dataclass

MARKUP_WITHOUT_LAST_VK = 0.10


@dataclass
class StockItem:
    hersteller: str
    artikel: str
    ean: str
    ek_avg: float | None       # ⌀ EK – intern, nie an Kunden
    vk_last: float | None      # Letzter VK – Orientierung
    verfuegbar: int
    lager: dict[str, int]      # Bestand je Standort (nur > 0)
    letzter_we: str

    @property
    def angebotspreis(self) -> float | None:
        """None = nicht anbieten."""
        if not self.ek_avg:
            return None
        if self.vk_last:
            return self.vk_last if self.vk_last >= self.ek_avg else None
        return math.ceil(self.ek_avg * (1 + MARKUP_WITHOUT_LAST_VK) * 100) / 100

    @property
    def marge_letzter_vk(self) -> float | None:
        if self.ek_avg and self.vk_last:
            return (self.vk_last - self.ek_avg) / self.vk_last
        return None


def parse_euro(value: str) -> float | None:
    """'1.711,77 €' → 1711.77; leere Zellen → None."""
    cleaned = re.sub(r"[^\d,.-]", "", value or "")
    if not cleaned:
        return None
    return float(cleaned.replace(".", "").replace(",", "."))


def parse_int(value: str) -> int:
    cleaned = re.sub(r"[^\d-]", "", value or "")
    return int(cleaned) if cleaned not in ("", "-") else 0


def parse_stock_csv(text: str) -> list[StockItem]:
    rows = csv.DictReader(io.StringIO(text))
    lager_cols = [c for c in rows.fieldnames or [] if c.endswith("- Verfügbar")]
    items = []
    for row in rows:
        if not row.get("Artikel"):
            continue
        items.append(StockItem(
            hersteller=row.get("Hersteller", "").strip(),
            artikel=row["Artikel"].strip(),
            ean=row.get("EAN", "").strip(),
            ek_avg=parse_euro(row.get("⌀ EK", "")),
            vk_last=parse_euro(row.get("Letzter VK", "")),
            verfuegbar=parse_int(row.get("Verfügbar", "")),
            lager={
                c.replace("- Verfügbar", "").strip(): n
                for c in lager_cols
                if (n := parse_int(row.get(c, ""))) > 0
            },
            letzter_we=row.get("Letzter WE", "").strip(),
        ))
    return items


def available(items: list[StockItem]) -> list[StockItem]:
    """Nur was tatsächlich im Lager verfügbar ist."""
    return [i for i in items if i.verfuegbar > 0]


def offerable(items: list[StockItem]) -> list[StockItem]:
    """Verfügbar und mit gültigem Angebotspreis."""
    return [i for i in available(items) if i.angebotspreis is not None]
