"""Angebots-Serienmail über IONOS (ersetzt Outlook-Serienbrief mit Excel-Liste).

Jeder Empfänger bekommt eine eigene Mail (kein CC/BCC-Verteiler) mit einem
Angebot aus dem aktuellen Warenbestand: passende Marken zuerst, dann neue
Wareneingänge. Ablauf: `mail-preview` erzeugt alle Mails als Dateien zum Prüfen,
`mail-send --test` schickt sie an Marc selbst, `mail-send` an die Kunden.

Empfängerliste (CSV/Excel, erste Zeile = Überschriften):
    Firma, Vorname, E-Mail, Marken (optional, mit Komma getrennt)
Abmeldungen: eine E-Mail-Adresse pro Zeile in data/abmeldungen.txt.
Zugang: IONOS_SMTP_USER / IONOS_SMTP_PASSWORD als Secret auf dem Server –
niemals im Chat oder im Repo.
"""

import csv
import html
import io
import os
import smtplib
import ssl
import time
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
MAX_ARTIKEL = 15
ABMELDUNGEN = Path("data/abmeldungen.txt")
OUTBOX = Path("data/outbox")


@dataclass
class Recipient:
    firma: str
    vorname: str
    email: str
    marken: set[str]


def load_recipients(path: str | Path) -> list[Recipient]:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        ws = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        rows = [[("" if c is None else str(c)).strip() for c in r] for r in ws.iter_rows(values_only=True)]
    else:
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig")), delimiter=";" if ";" in path.read_text()[:500] else ",")]
    head = [h.lower() for h in rows[0]]
    col = lambda *names: next((head.index(n) for n in names if n in head), None)
    i_firma, i_vor, i_mail, i_mark = col("firma", "kunde"), col("vorname", "ansprechpartner", "name"), col("e-mail", "email", "mail"), col("marken", "marke")
    if i_mail is None:
        raise ValueError("Spalte „E-Mail“ fehlt in der Empfängerliste")
    blocked = {l.strip().lower() for l in ABMELDUNGEN.read_text().splitlines()} if ABMELDUNGEN.exists() else set()
    out, seen = [], set()
    for r in rows[1:]:
        get = lambda i: r[i] if i is not None and i < len(r) else ""
        email = get(i_mail).lower()
        if "@" not in email or email in blocked or email in seen:
            continue
        seen.add(email)
        marken = {m.strip().lower() for m in get(i_mark).split(",") if m.strip()}
        out.append(Recipient(get(i_firma), get(i_vor), email, marken))
    return out


def pick_items(recipient: Recipient, items: list[StockItem]) -> list[StockItem]:
    """Neue Wareneingänge seiner Marken, dann übrige seiner Marken, dann übrige neue Ware."""
    fresh = {i.ean for i in fresh_arrivals(items)}
    pool = sorted(offerable(items), key=lambda i: i.position)
    mine = [i for i in pool if i.hersteller.lower() in recipient.marken]
    ordered = [i for i in mine if i.ean in fresh] + [i for i in mine if i.ean not in fresh]
    ordered += [i for i in pool if i.ean in fresh and i not in ordered]
    return ordered[:MAX_ARTIKEL]


def _euro(v: float) -> str:
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def build_message(r: Recipient, items: list[StockItem], absender: str, absender_name: str) -> EmailMessage:
    gruss = f"Moin {r.vorname}," if r.vorname else "Moin,"
    heute = date.today().strftime("%d.%m.%Y")
    lines = "\n\n".join(f"{i.artikel}\n{i.ean}\n{i.verfuegbar}x\n{_euro(i.angebotspreis)}" for i in items)
    abmelden = "Keine Angebote mehr? Kurz mit „Abmelden“ antworten."
    text = f"{gruss}\n\nhier die aktuelle Ware, sofort verfügbar:\n\n{lines}\n\nPreise netto, solange Vorrat reicht.\nMeld dich einfach.\n\n{absender_name}\n\n{abmelden}\n"
    rows = "".join(
        f"<tr><td>{html.escape(i.artikel)}</td><td>{i.ean}</td><td style='text-align:right'>{i.verfuegbar}x</td>"
        f"<td style='text-align:right;white-space:nowrap'>{_euro(i.angebotspreis)}</td></tr>" for i in items
    )
    body = (
        f"<p>{html.escape(gruss)}</p><p>hier die aktuelle Ware, sofort verfügbar:</p>"
        "<table cellpadding='6' style='border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px'>"
        "<tr style='background:#eee'><th align='left'>Artikel</th><th align='left'>EAN</th><th>Menge</th><th>Preis</th></tr>"
        f"{rows}</table><p>Preise netto, solange Vorrat reicht.<br>Meld dich einfach.</p>"
        f"<p>{html.escape(absender_name)}</p><p style='color:#888;font-size:12px'>{html.escape(abmelden)}</p>"
    )
    msg = EmailMessage()
    msg["Subject"] = f"Angebot {heute} – {items[0].hersteller} {('& mehr' if len(items) > 1 else '')}".strip()
    msg["From"] = formataddr((absender_name, absender))
    msg["To"] = formataddr((r.vorname or r.firma, r.email))
    msg["Message-ID"] = make_msgid(domain=absender.split("@")[-1])
    msg["List-Unsubscribe"] = f"<mailto:{absender}?subject=Abmelden>"
    msg.set_content(text)
    msg.add_alternative(body, subtype="html")
    return msg


Mail = tuple[Recipient, EmailMessage, int]  # Empfänger, Mail, Anzahl Artikel


def build_all(recipients: list[Recipient], items: list[StockItem], absender: str, absender_name: str) -> list[Mail]:
    out = []
    for r in recipients:
        chosen = pick_items(r, items)
        if chosen:
            out.append((r, build_message(r, chosen, absender, absender_name), len(chosen)))
    return out


def write_preview(mails: list[Mail]) -> Path:
    """Alle Mails als .eml (in Outlook öffnen) plus eine Übersicht zum Durchblättern."""
    folder = OUTBOX / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    cards = []
    for n, (r, msg, _) in enumerate(mails, 1):
        (folder / f"{n:03d}_{r.email.replace('@', '_at_')}.eml").write_bytes(bytes(msg))
        html_part = msg.get_body(("html",)).get_content()
        cards.append(f"<section style='border:1px solid #ccc;margin:16px 0;padding:12px'><b>An:</b> {html.escape(msg['To'])}<br>"
                     f"<b>Betreff:</b> {html.escape(msg['Subject'])}<hr>{html_part}</section>")
    (folder / "vorschau.html").write_text(f"<meta charset='utf-8'><h1>{len(mails)} Angebots-Mails</h1>{''.join(cards)}")
    return folder


def send_all(mails: list[Mail], test_to: str | None = None) -> Path:
    """Verschickt einzeln über IONOS. Mit test_to geht alles an diese Adresse statt an die Kunden."""
    user, password = os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"]
    log = OUTBOX / f"versand_{date.today().isoformat()}.csv"
    log.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log.exists()
    with log.open("a", newline="") as f, smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        w = csv.writer(f)
        if new_log:
            w.writerow(["zeit", "firma", "email", "betreff", "artikel", "status"])
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(user, password)
        for r, msg, n in mails:
            if test_to:
                del msg["To"]
                msg["To"] = test_to
            try:
                smtp.send_message(msg)
                status = "test" if test_to else "gesendet"
            except smtplib.SMTPException as e:
                status = f"fehler: {e}"
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), r.firma, r.email, msg["Subject"], n, status])
            f.flush()
            time.sleep(PAUSE_SEKUNDEN)
    return log
