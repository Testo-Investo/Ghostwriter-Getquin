"""Angebots-Serienmail über IONOS (ersetzt Outlook-Serienbrief mit Excel-Liste).

Jeder Empfänger bekommt eine eigene Mail (kein CC/BCC-Verteiler) mit einem
Angebot aus dem aktuellen Warenbestand: passende Marken zuerst, dann neue
Wareneingänge. Ablauf: `mail-preview` erzeugt alle Mails als Dateien zum Prüfen,
`mail-send --test` schickt sie an Marc selbst, `mail-send` an die Kunden.

Empfängerliste (CSV/Excel, erste Zeile = Überschriften), wie Marcs Serienbrief-Listen:
    Vorname, Nachname, E-Mail, Produkt(e) (Marken oder Kategorien, mit Komma), Land
Sprache: Deutsch, oder Englisch wenn der Dateiname „engl“ enthält (oder sprache="en").
Abmeldungen: eine E-Mail-Adresse pro Zeile in data/abmeldungen.txt.
Zugang: IONOS_SMTP_USER / IONOS_SMTP_PASSWORD als Secret auf dem Server –
niemals im Chat oder im Repo.
"""

import csv
import html
import io
import os
import re
import smtplib
import ssl
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from openpyxl import load_workbook

from .stock import StockItem, offerable
from .watch import fresh_arrivals

SMTP_HOST = "smtp.ionos.de"
SMTP_PORT = 587
PAUSE_SEKUNDEN = 4          # Abstand zwischen zwei Mails, schont Reputation und IONOS-Limits
MIN_ARTIKEL = 5             # Marc: „immer so 5 bis 10 Artikel“
MAX_ARTIKEL = 10
EZB_KURSE = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
STATE = Path("data/mail_state.json")    # welche EANs schon per Mail angekündigt wurden
SIGNATUR = Path("config/signatur.txt")
STOCK_CSV = Path(os.getenv("STOCK_CSV", "data/warenbestand.csv"))
LOGO = Path("config/signatur_logo.png")  # Banner über der Signatur (optional)
ABMELDUNGEN = Path("data/abmeldungen.txt")
UNZUSTELLBAR = Path("data/unzustellbar.txt")  # Rückläufer, von postfach.py gepflegt
OUTBOX = Path("data/outbox")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


# Kategorien aus der Spalte „Produkt(e)“ → Hersteller im Warenbestand
KATEGORIEN = {
    "handy": {"samsung", "google", "apple"}, "smartphone": {"samsung", "google", "apple"},
    "phone": {"samsung", "google", "apple"}, "mobile": {"samsung", "google", "apple"},
    "kamera": {"canon", "sony", "dji"}, "camera": {"canon", "sony", "dji"},
    "drohne": {"dji"}, "drone": {"dji"}, "monitor": {"dell", "lenovo"},
    "saugroboter": {"dreame", "ecovacs"}, "vacuum": {"dreame", "ecovacs"},
    "lautsprecher": {"jbl", "marshall", "amazon"}, "speaker": {"jbl", "marshall", "amazon"},
    "smartwatch": {"garmin", "fitbit", "samsung"}, "konsole": {"nintendo", "sony"},
    "console": {"nintendo", "sony"}, "gaming": {"nintendo", "sony", "razer", "meta"},
    "kameras": {"canon", "sony", "dji", "fujifilm"}, "cameras": {"canon", "sony", "dji", "fujifilm"},
    "drucker": {"canon", "hp", "zebra"}, "printer": {"canon", "hp", "zebra"}, "printers": {"canon", "hp", "zebra"},
    "monitore": {"dell", "lenovo"}, "monitors": {"dell", "lenovo"}, "montors": {"dell", "lenovo"},
    "headphones": {"marshall", "sony", "jbl", "epos"}, "kopfhörer": {"marshall", "sony", "jbl", "epos"},
    "kaffeemaschinen": {"delonghi"}, "kaffe maschinen": {"delonghi"}, "delongi": {"delonghi"},
    "mashall": {"marshall"}, "plantronics": {"poly"}, "western digital": {"wd", "western"},
    "phones": {"samsung", "google", "apple"},
}
# „alle A-Marken“ o. ä. heißt: keine Einschränkung, nur neue Ware
ALLE = {"a marken", "a brands", "all a marken", "all brands", "alles"}

TEXTE = {
    "de": {
        "gruss": "Moin {vorname},", "gruss_ohne": "Moin,",
        "intro": "hier die aktuelle Ware, sofort verfügbar:",
        "outro": "Preise netto, innerhalb Deutschlands frei Haus, solange Vorrat reicht.\nMeld dich einfach.",
        "abmelden": "Keine Angebote mehr? Kurz mit „Abmelden“ antworten.",
        "betreff": "Angebot {datum} – {marke} & mehr",
        "kopf": ("Artikel", "EAN", "Menge", "Preis"),
    },
    "en": {
        "gruss": "Hi {vorname},", "gruss_ohne": "Hi,",
        "intro": "please find our current stock below, available immediately:",
        "outro": "Prices net, ex works Germany, subject to prior sale.\nJust reply if you are interested.",
        "abmelden": "No more offers? Simply reply with “Unsubscribe”.",
        "betreff": "Stock offer {datum} – {marke} & more",
        "kopf": ("Item", "EAN", "Qty", "Price"),
    },
}


@dataclass
class Recipient:
    firma: str
    vorname: str
    email: str
    marken: set[str]
    sprache: str = "de"
    waehrung: str = "EUR"


def load_recipients(path: str | Path, sprache: str | None = None, keine_sperre: bool = False) -> list[Recipient]:
    """Empfänger einer Liste; abgemeldete und unzustellbare Adressen fallen raus (außer keine_sperre)."""
    path = Path(path)
    sprache = sprache or ("en" if "engl" in path.name.lower() else "de")
    waehrung = "USD" if "dubai" in path.name.lower() else "EUR"  # Dubai: Dollar zum Tageskurs
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        ws = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        rows = [[("" if c is None else str(c)).strip() for c in r] for r in ws.iter_rows(values_only=True)]
    else:
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig")), delimiter=";" if ";" in path.read_text()[:500] else ",")]
    head = [h.lower() for h in rows[0]]
    col = lambda *names: next((head.index(n) for n in names if n in head), None)
    i_firma, i_vor, i_mail, i_mark = (col("firma", "kunde"), col("vorname", "ansprechpartner", "name"),
                                      col("e-mail", "email", "mail"), col("marken", "marke", "produkte", "produkt"))
    if i_mail is None:
        raise ValueError("Spalte „E-Mail“ fehlt in der Empfängerliste")
    blocked = set()
    for sperre in () if keine_sperre else (ABMELDUNGEN, UNZUSTELLBAR):
        if sperre.exists():
            blocked |= {l.strip().lower() for l in sperre.read_text().splitlines()}
    out, seen = [], set()
    for r in rows[1:]:
        get = lambda i: r[i] if i is not None and i < len(r) else ""
        email = get(i_mail).strip().strip("'\"<>;,").lower()  # z. B. „…@bueromarkt-ag.de'“ (Tippfehler in der Liste)
        if not _EMAIL.match(email) or email in blocked or email in seen:
            continue
        seen.add(email)
        marken = set()
        for m in re.split(r"[,;/]|\bund\b|\band\b", get(i_mark).lower()):
            m = m.strip()
            if m and m not in ALLE:
                marken |= KATEGORIEN.get(m) or {w for word in m.split() for w in KATEGORIEN.get(word, {word})}
        vorname = get(i_vor)
        if vorname.lower() in ("team", "sales", "info", "sir", "guys", "zusammen", "einkauf"):
            vorname = ""
        out.append(Recipient(get(i_firma) or email.split("@")[1], vorname, email, marken, sprache, waehrung))
    return out


def pick_items(recipient: Recipient, items: list[StockItem], neu_eans: set[str] | None = None) -> list[StockItem]:
    """5–10 Artikel: zuerst Neues (seine Marken vor anderen), aufgefüllt mit übrigen
    frischen Wareneingängen (seine Marken zuerst).

    neu_eans: nur diese gelten als „neu“ (Versand bei neuem Wareneingang);
    ohne Angabe gelten alle Wareneingänge der letzten 7 Tage als neu."""
    pool = sorted(offerable(items), key=lambda i: i.position)
    fresh_eans = {f.ean for f in fresh_arrivals(items)}
    fresh = [i for i in pool if i.ean in fresh_eans]
    neu = [i for i in fresh if neu_eans is None or i.ean in neu_eans]
    mine = lambda i: i.hersteller.lower() in recipient.marken or i.hersteller.lower().replace("!", "") in recipient.marken
    ordered = [i for i in neu if mine(i)] + [i for i in neu if not mine(i)]
    if len(ordered) < MIN_ARTIKEL:
        rest = [i for i in fresh if i not in ordered]
        ordered += [i for i in rest if mine(i)] + [i for i in rest if not mine(i)]
    return ordered[:MAX_ARTIKEL]


def mix_items(recipient: Recipient, items: list[StockItem], seed: str) -> list[StockItem]:
    """„Mix“ (Marcs Antwort MIX): bunt gemischt aus dem ganzen anbietbaren Bestand, auch ältere
    Artikel. Bis zur Hälfte aus seinen Marken, Rest aus allem anderen; neueste oben.

    Der Zufall hängt nur an seed + Adresse – Freigabe-Beispiel und Versand sind identisch."""
    import random
    rnd = random.Random(f"{seed}:{recipient.email}")
    pool = sorted(offerable(items), key=lambda i: i.position)
    mine = [i for i in pool if i.hersteller.lower() in recipient.marken
            or i.hersteller.lower().replace("!", "") in recipient.marken]
    chosen = rnd.sample(mine, min(len(mine), MAX_ARTIKEL // 2))
    rest = [i for i in pool if i not in chosen]
    chosen += rnd.sample(rest, min(len(rest), MAX_ARTIKEL - len(chosen)))
    return sorted(chosen, key=lambda i: i.position)


def usd_rate() -> float:
    """EUR→USD-Referenzkurs der EZB vom Tag (gecacht); USD_KURS in .env überschreibt."""
    if os.getenv("USD_KURS"):
        return float(os.environ["USD_KURS"])
    cache = Path(f"data/kurs_usd_{date.today().isoformat()}.txt")
    if cache.exists():
        return float(cache.read_text())
    with urllib.request.urlopen(EZB_KURSE, timeout=20) as resp:
        xml = resp.read().decode()
    rate = float(re.search(r"currency='USD' rate='([\d.]+)'", xml).group(1))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(str(rate))
    return rate


def _price(r: "Recipient", eur: float, rate: float | None) -> str:
    if r.waehrung == "USD":
        return f"${math.ceil(eur * rate * 100) / 100:,.2f}"  # aufrunden, Marge nicht verschenken
    return _euro(eur, r.sprache)


def _euro(v: float, sprache: str = "de") -> str:
    if sprache == "en":
        return f"€{v:,.2f}"
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _menge(n: int, sprache: str) -> str:
    """Marc: ab 1.000 Stück nur „1.000+“ statt der genauen Menge."""
    if n >= 1000:
        return "1,000+" if sprache == "en" else "1.000+"
    return f"{n}x"


def build_message(r: Recipient, items: list[StockItem], absender: str, absender_name: str,
                  signatur: str = "", rate: float | None = None) -> EmailMessage:
    t = TEXTE[r.sprache]
    gruss = t["gruss"].format(vorname=r.vorname) if r.vorname else t["gruss_ohne"]
    heute = date.today().strftime("%d.%m.%Y")
    eur = lambda v: _price(r, v, rate)
    menge = lambda n: _menge(n, r.sprache)
    lines = "\n\n".join(f"{i.artikel}\n{i.ean}\n{menge(i.verfuegbar)}\n{eur(i.angebotspreis)}" for i in items)
    sig = signatur.strip() or absender_name
    logo_cid = make_msgid(domain="neobution.com")
    text = f"{gruss}\n\n{t['intro']}\n\n{lines}\n\n{t['outro']}\n\n{sig}\n\n{t['abmelden']}\n"
    rows = "".join(
        f"<tr><td>{html.escape(i.artikel)}</td><td>{i.ean}</td><td style='text-align:right'>{menge(i.verfuegbar)}</td>"
        f"<td style='text-align:right;white-space:nowrap'>{eur(i.angebotspreis)}</td></tr>" for i in items
    )
    kopf = "".join(f"<th align='left'>{h}</th>" for h in t["kopf"])
    body = (
        f"<p>{html.escape(gruss)}</p><p>{html.escape(t['intro'])}</p>"
        "<table cellpadding='6' style='border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px'>"
        f"<tr style='background:#eee'>{kopf}</tr>{rows}</table>"
        f"<p>{html.escape(t['outro']).replace(chr(10), '<br>')}</p>"
        + (f"<p><img src='cid:{logo_cid[1:-1]}' alt='Neobution' width='583' style='max-width:100%'></p>" if LOGO.exists() else "")
        + f"<p style='font-size:13px'>{_signature_html(sig)}</p><p style='color:#888;font-size:12px'>{html.escape(t['abmelden'])}</p>"
    )
    msg = EmailMessage()
    msg["Subject"] = t["betreff"].format(datum=heute, marke=items[0].hersteller)
    msg["From"] = formataddr((absender_name, absender))
    msg["To"] = formataddr((r.vorname or r.firma, r.email))
    msg["Message-ID"] = make_msgid(domain=absender.split("@")[-1])
    msg["List-Unsubscribe"] = f"<mailto:{absender}?subject=Abmelden>"
    msg.set_content(text)
    msg.add_alternative(body, subtype="html")
    if LOGO.exists():
        msg.get_payload()[1].add_related(LOGO.read_bytes(), "image", "png", cid=logo_cid)
    return msg


Mail = tuple[Recipient, EmailMessage, int]  # Empfänger, Mail, Anzahl Artikel


def _signature_html(sig: str) -> str:
    """Erste Zeile (Name) fett, Website verlinkt, Rechtliches klein und grau."""
    out = []
    for n, line in enumerate(sig.splitlines()):
        esc = html.escape(line)
        if n == 0:
            esc = f"<b>{esc}</b>"
        elif line.startswith("www."):
            esc = f"<a href='https://{esc}'>{esc}</a>"
        elif "|" in line or line.startswith("Diese E-Mail"):
            esc = f"<span style='color:#888;font-size:11px'>{esc}</span>"
        out.append(esc)
    return "<br>".join(out)


def build_all(recipients: list[Recipient], items: list[StockItem], absender: str, absender_name: str,
              neu_eans: set[str] | None = None, signatur: str = "", feste_artikel: list | None = None,
              mix: str | None = None, gewaehlt: set[str] | None = None) -> list[Mail]:
    """feste_artikel: Sonderangebot – alle bekommen genau diese Artikel, ohne Auswahl.
    mix: Zufalls-Schlüssel für ein gemischtes Angebot (siehe mix_items).
    gewaehlt: wird mit den EANs aller verwendeten Artikel gefüllt."""
    rate = usd_rate() if any(r.waehrung == "USD" for r in recipients) else None
    out = []
    for r in recipients:
        if feste_artikel is not None:
            chosen = feste_artikel
        elif mix:
            chosen = mix_items(r, items, mix)
        else:
            chosen = pick_items(r, items, neu_eans)
        if gewaehlt is not None:
            gewaehlt |= {i.ean for i in chosen}
        if chosen:
            out.append((r, build_message(r, chosen, absender, absender_name, signatur, rate), len(chosen)))
    return out


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"angekuendigt": [], "zuletzt": ""}


def new_arrivals_to_announce(items: list[StockItem], state: dict) -> set[str]:
    """Frische, anbietbare Wareneingänge, die noch in keiner Mail standen."""
    return {i.ean for i in fresh_arrivals(items)} - set(state["angekuendigt"])


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1))


def mark_announced(state: dict, eans: set[str]) -> None:
    state["angekuendigt"] = sorted(set(state["angekuendigt"]) | eans)
    state["zuletzt"] = date.today().isoformat()
    state.pop("antrag", None)
    save_state(state)


def write_preview(mails: list[Mail], name: str = "") -> Path:
    """Alle Mails als .eml (in Outlook öffnen) plus eine Übersicht zum Durchblättern."""
    folder = OUTBOX / date.today().isoformat() / name
    folder.mkdir(parents=True, exist_ok=True)
    cards = []
    for n, (r, msg, _) in enumerate(mails, 1):
        (folder / f"{n:03d}_{r.email.replace('@', '_at_')}.eml").write_bytes(bytes(msg))
        html_part = msg.get_body(("html",)).get_content()
        if LOGO.exists():  # in der Vorschau das eingebettete Logo direkt anzeigen
            import base64
            html_part = re.sub(r"cid:[^']+", "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode(), html_part)
        cards.append(f"<section style='border:1px solid #ccc;margin:16px 0;padding:12px'><b>An:</b> {html.escape(msg['To'])}<br>"
                     f"<b>Betreff:</b> {html.escape(msg['Subject'])}<hr>{html_part}</section>")
    (folder / "vorschau.html").write_text(f"<meta charset='utf-8'><h1>{len(mails)} Angebots-Mails</h1>{''.join(cards)}")
    return folder


def send_raw(msg: EmailMessage) -> None:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"])
        smtp.send_message(msg)


def smtp_test(to: str) -> None:
    """Eine kurze Testmail – prüft Zugangsdaten und ob der Server IONOS erreicht."""
    msg = EmailMessage()
    msg["Subject"] = "Ghostwriter: Testmail vom Server"
    msg["From"] = formataddr((os.getenv("MAIL_NAME", "Marc Knieb"), os.environ["MAIL_FROM"]))
    msg["To"] = to
    msg.set_content("Wenn du das liest, kann der Server über IONOS Mails verschicken.")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"])
        smtp.send_message(msg)


SESSION_MAX = 15  # IONOS nimmt pro Verbindung nur 20 Mails an („Mails per session limit exceeded“)
_DAUERHAFT = re.compile(r"\(5\d\d,")  # 5xx = Adresse/Domain gibt es nicht


def dauerhaft(status: str) -> bool:
    """Fehler, bei dem ein neuer Versuch nichts bringt (z. B. 550 Domain existiert nicht)."""
    return bool(_DAUERHAFT.search(status))


def _verbinden() -> smtplib.SMTP:
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    smtp.starttls(context=ssl.create_default_context())
    smtp.login(os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"])
    return smtp


def _trennen(smtp: smtplib.SMTP) -> None:
    try:
        smtp.quit()
    except smtplib.SMTPException:
        smtp.close()


def send_all(mails: list[Mail], test_to: str | None = None) -> tuple[Path, int, list[tuple[str, str]]]:
    """Verschickt einzeln über IONOS. Mit test_to geht alles an diese Adresse statt an die Kunden.

    Nach SESSION_MAX Mails wird neu verbunden; wird eine Mail wegen des Limits pro
    Verbindung abgelehnt, wird neu verbunden und noch einmal versucht.
    Gibt (Protokoll, Anzahl gesendet, [(adresse, fehler)]) zurück."""
    ok, fehler = 0, []
    log = OUTBOX / f"versand_{date.today().isoformat()}.csv"
    log.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log.exists()
    smtp, in_sitzung = _verbinden(), 0
    try:
        with log.open("a", newline="") as f:
            w = csv.writer(f)
            if new_log:
                w.writerow(["zeit", "firma", "email", "betreff", "artikel", "status"])
            for r, msg, n in mails:
                if test_to:
                    del msg["To"]
                    msg["To"] = test_to
                for versuch in range(2):
                    if in_sitzung >= SESSION_MAX or versuch:
                        _trennen(smtp)
                        smtp, in_sitzung = _verbinden(), 0
                    try:
                        in_sitzung += 1
                        smtp.send_message(msg)
                        status = "test" if test_to else "gesendet"
                        ok += 1
                        break
                    except smtplib.SMTPException as e:
                        status = f"fehler: {e}"
                        if not (re.search(r"\(4[25]\d", status) or isinstance(e, smtplib.SMTPServerDisconnected)):
                            break  # nur vorübergehende Fehler (Limit, Verbindung weg) lohnen einen 2. Versuch
                if not status.startswith(("gesendet", "test")):
                    fehler.append((r.email, status[8:168]))
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), r.firma, r.email, msg["Subject"], n, status])
                f.flush()
                time.sleep(PAUSE_SEKUNDEN)
    finally:
        _trennen(smtp)
    return log, ok, fehler


def heute_verschickt(mails: list[Mail]) -> bool:
    """Ging heute schon mindestens eine dieser Mails (gleicher Betreff) raus?"""
    log = OUTBOX / f"versand_{date.today().isoformat()}.csv"
    if not log.exists():
        return False
    betreffe = {m[1]["Subject"] for m in mails}
    return any(r["status"] == "gesendet" and r["betreff"] in betreffe for r in csv.DictReader(log.open(newline="")))


def noch_offen(mails: list[Mail]) -> list[Mail]:
    """Nur die Mails, die laut Protokoll noch nicht mit genau diesem Betreff angekommen sind
    und deren Adresse nicht dauerhaft unzustellbar war (zum Nachholen nach Abbrüchen)."""
    erledigt = set()
    for log in OUTBOX.glob("versand_*.csv"):
        for row in csv.DictReader(log.open(newline="")):
            if row["status"] == "gesendet" or dauerhaft(row["status"]):
                erledigt.add((row["email"], row["betreff"]))
    return [m for m in mails if (m[0].email, m[1]["Subject"]) not in erledigt]


def permanent_failures() -> dict[str, str]:
    """Adressen, die beim Versand dauerhaft abgelehnt wurden (5xx), mit Grund."""
    out = {}
    for log in OUTBOX.glob("versand_*.csv"):
        for row in csv.DictReader(log.open(newline="")):
            if dauerhaft(row["status"]):
                out[row["email"]] = re.sub(r"\s+", " ", row["status"][8:])[:160]
    return out


def versand_bericht(was: str, ergebnis: dict[str, tuple[int, int, list]]) -> None:
    """Info an Marc, sobald alles raus ist: je Liste gesendet / gesamt, dazu Fehler."""
    gesendet = sum(e[0] for e in ergebnis.values())
    gesamt = sum(e[1] for e in ergebnis.values())
    msg = EmailMessage()
    msg["Subject"] = f"Ghostwriter: {was} verschickt – {gesendet} von {gesamt} Mails raus"
    msg["From"] = formataddr(("Ghostwriter", os.environ["MAIL_FROM"]))
    msg["To"] = os.getenv("FREIGABE_AN", os.environ["MAIL_FROM"])
    zeilen = "\n".join(f"  {name}: {ok} von {n}" for name, (ok, n, _) in ergebnis.items())
    fehler = [f"  {a}: {f}" for _, _, fl in ergebnis.values() for a, f in fl]
    text = f"Moin Marc,\n\n{was} ist fertig verschickt ({time.strftime('%d.%m.%Y %H:%M')} Uhr):\n\n{zeilen}\n  Gesamt: {gesendet} von {gesamt}\n"
    if fehler:
        text += "\nNicht angenommen vom Mailserver:\n" + "\n".join(fehler) + "\n"
    text += ("\nAbwesenheitsnotizen sortiert der Server in den Ordner „Abwesenheitsnotizen“.\n"
             "Unzustellbare Adressen löscht er aus den Listen – dazu kommt eine eigene Info-Mail.\n")
    msg.set_content(text)
    send_raw(msg)
