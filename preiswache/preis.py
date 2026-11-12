"""Preiswache: meldet Marc per Mail, wenn ein Produktpreis unter eine Grenze fällt.

Läuft auf dem Ghostwriter-Server alle 2 Stunden von 9 bis 17 Uhr, Montag bis Sonntag
(deploy/preiswache.timer). Ruft die Seite dabei nur einmal ab – wie ein normaler Besucher.
Mail über das IONOS-Postfach des Ghostwriters (/opt/ghostwriter/.env).

  python preiswache/preis.py          prüfen, bei Unterschreitung Mail
  python preiswache/preis.py --test   nur den gefundenen Preis anzeigen, keine Mail

Gemeldet wird einmal, wenn der Preis unter die Grenze fällt, und erneut erst, wenn er
zwischendurch wieder darüber lag oder noch weiter gefallen ist.
"""

import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import requests
from dotenv import load_dotenv

BASIS = Path(__file__).resolve().parent.parent
PRODUKTE = [
    {"name": "HSN Evowhey Protein 2kg Schokolade mit Stevia", "grenze": 60.00,
     "url": "https://www.hsnstore.de/marken/sport-series/evowhey-protein-2kg-schokolade-mit-stevia"},
]
STATE = BASIS / "data" / "preiswache.json"
FEHLER_MELDEN_AB = 3  # so viele Abrufe hintereinander ohne Preis → einmal Bescheid sagen
KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9"}


def _zahl(text) -> float | None:
    text = str(text).strip().replace("€", "").replace("\xa0", "").replace(" ", "")
    if "," in text:  # 1.234,56
        text = text.replace(".", "").replace(",", ".")
    try:
        wert = float(text)
    except ValueError:
        return None
    return wert if 0 < wert < 100000 else None


def _aus_jsonld(daten) -> list[float]:
    """Preise aus JSON-LD (schema.org Product/Offer), auch verschachtelt."""
    out = []
    if isinstance(daten, list):
        for d in daten:
            out += _aus_jsonld(d)
    elif isinstance(daten, dict):
        for schluessel in ("price", "lowPrice"):
            if schluessel in daten and (p := _zahl(daten[schluessel])) is not None:
                out.append(p)
        for wert in daten.values():
            if isinstance(wert, (dict, list)):
                out += _aus_jsonld(wert)
    return out


def preis_aus_html(html: str) -> float | None:
    """Aktueller Verkaufspreis der Seite. Reihenfolge: strukturierte Daten vor sichtbarem Text."""
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            preise = _aus_jsonld(json.loads(block.strip()))
        except ValueError:
            continue
        if preise:
            return min(preise)
    for muster in (r'<meta[^>]+(?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([\d.,]+)',
                   r'<meta[^>]+itemprop=["\']price["\'][^>]+content=["\']([\d.,]+)',
                   r'data-price-type=["\']finalPrice["\'][^>]*data-price-amount=["\']([\d.,]+)',
                   r'data-price-amount=["\']([\d.,]+)["\'][^>]*data-price-type=["\']finalPrice',
                   r'"final_price"\s*:\s*"?([\d.]+)'):
        if (m := re.search(muster, html, re.I)) and (p := _zahl(m.group(1))) is not None:
            return p
    return None


def hole_preis(url: str) -> float | None:
    resp = requests.get(url, headers=KOPF, timeout=30)
    resp.raise_for_status()
    return preis_aus_html(resp.text)


def mail(betreff: str, text: str) -> None:
    load_dotenv(BASIS / ".env")
    msg = EmailMessage()
    msg["Subject"] = betreff
    msg["From"] = msg["To"] = os.environ["MAIL_FROM"]
    msg.set_content(text)
    with smtplib.SMTP("smtp.ionos.de", 587, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"])
        smtp.send_message(msg)


def euro(v: float) -> str:
    return f"{v:.2f} €".replace(".", ",")


def pruefe(produkt: dict, stand: dict, test: bool = False) -> None:
    jetzt = f"{datetime.now():%d.%m.%Y %H:%M}"
    try:
        preis = hole_preis(produkt["url"])
        fehler = "" if preis is not None else "kein Preis auf der Seite gefunden"
    except requests.RequestException as e:
        preis, fehler = None, str(e)[:200]
    if test:
        print(f"{produkt['name']}: " + (f"{euro(preis)} (Grenze {euro(produkt['grenze'])})" if preis is not None else f"FEHLER – {fehler}"))
        return
    if preis is None:
        stand["fehler"] = stand.get("fehler", 0) + 1
        print(f"{jetzt} {produkt['name']}: Abruf fehlgeschlagen ({fehler})")
        if stand["fehler"] == FEHLER_MELDEN_AB:
            mail(f"Preiswache: {produkt['name']} lässt sich nicht prüfen",
                 f"Moin Marc,\n\nder Preis konnte {FEHLER_MELDEN_AB}-mal hintereinander nicht gelesen werden:\n{fehler}\n\n"
                 f"{produkt['url']}\n\nSag Claude im Chat Bescheid, dann wird das Skript angepasst.\n")
        return
    stand["fehler"] = 0
    gemeldet = stand.get("gemeldet")  # Preis der letzten Meldung, None = zuletzt über der Grenze
    print(f"{jetzt} {produkt['name']}: {euro(preis)}")
    if preis < produkt["grenze"] and (gemeldet is None or preis < gemeldet):
        mail(f"Preisalarm: {produkt['name']} jetzt {euro(preis)}",
             f"Moin Marc,\n\nder Preis ist unter {euro(produkt['grenze'])} gefallen:\n\n"
             f"  {produkt['name']}\n  Jetzt: {euro(preis)}  (geprüft {jetzt} Uhr)\n\n{produkt['url']}\n")
        stand["gemeldet"] = preis
        print("  → Mail an Marc geschickt")
    elif preis >= produkt["grenze"]:
        stand["gemeldet"] = None
    stand["letzter_preis"], stand["geprueft"] = preis, jetzt


def main() -> None:
    test = "--test" in sys.argv
    alles = json.loads(STATE.read_text()) if STATE.exists() else {}
    for produkt in PRODUKTE:
        pruefe(produkt, alles.setdefault(produkt["url"], {}), test)
    if not test:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(alles, indent=1))


if __name__ == "__main__":
    main()
