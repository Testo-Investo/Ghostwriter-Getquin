"""Freigabe per Antwort-Mail: Marc schaut jeden Versand vorher an.

Ablauf im stündlichen Lauf (`mail-neu`):
1. Neue Ware, kein offener Antrag → Freigabe-Mail an Marc: Artikel, Empfängerzahl je
   Liste und je Liste eine Beispiel-Mail im Anhang. Betreff enthält eine Kennung [GW-…].
2. Marc antwortet mit „FREIGABE“ (oder „ok“/„ja“) → beim nächsten Lauf geht genau der
   angesehene Stand raus (Bestand von damals, nur ausverkaufte Artikel fallen weg und
   Mengen werden auf den heutigen Bestand gekappt). Mit „STOPP“ wird verworfen.
   Änderungen macht Marc nicht per Mail, sondern im Chat mit Claude; jede Code-Änderung
   macht einen offenen Antrag ungültig und erzeugt eine neue Freigabe-Mail.
3. Ohne Antwort verfällt der Antrag nach 3 Tagen; neue Ware erzeugt dann einen neuen.

Die Antwort wird per IMAP aus Marcs IONOS-Postfach gelesen (gleiche Zugangsdaten).
"""

import email
import email.utils
import html
import imaplib
import os
import secrets
import shutil
import subprocess
from dataclasses import replace
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from . import mailer
from .stock import StockItem, parse_stock_csv

BESTAND_ANTRAG = mailer.STATE.parent / "antrag_warenbestand.csv"  # Stand, den Marc gesehen hat


def code_version() -> str:
    """Aktueller Code-Stand (git). Ändert sich, sobald Claude etwas an Texten/Regeln ändert."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unbekannt"


def approved_stock(current: list[StockItem]) -> list[StockItem]:
    """Genau der Bestand, den Marc freigegeben hat – Preise und Artikel wie angesehen.

    Nur zur Sicherheit gegen Überverkauf: was inzwischen ausverkauft ist, fällt raus,
    und die Menge wird auf den heutigen Bestand gekappt."""
    jetzt = {i.ean: i for i in current}
    out = []
    for item in parse_stock_csv(BESTAND_ANTRAG.read_text()):
        neu = jetzt.get(item.ean)
        if neu is None or neu.verfuegbar <= 0:
            continue
        out.append(replace(item, verfuegbar=min(item.verfuegbar, neu.verfuegbar)))
    return out

IMAP_HOST = "imap.ionos.de"
GUELTIG_TAGE = 3
JA = ("freigabe", "freigeben", "ok", "okay", "ja", "go", "senden")
NEIN = ("stopp", "stop", "nein", "abbrechen", "verwerfen")
MIX = ("mix", "mischen", "durchmischen")  # neu mischen, auch ältere Artikel (nur normales Angebot)


def new_request(state: dict, eans: set[str], mails_by_list: dict[str, list],
                key: str = "antrag", anlass: str = "neue Ware ist da", prefix: str = "GW",
                titel: str | None = None) -> str:
    """Freigabe-Mail an Marc schicken und den Antrag im State unter `key` merken."""
    kennung = f"{prefix}-{date.today():%m%d}-{secrets.token_hex(2).upper()}"
    gesamt = sum(len(m) for m in mails_by_list.values())
    beispiel = next(iter(mails_by_list.values()))[0][1]
    zeilen = "\n".join(f"  {name}: {len(m)} Mails" for name, m in mails_by_list.items())
    msg = EmailMessage()
    art = "Sonderangebot" if key != "antrag" else "Angebot"
    titel = titel or f"{art} mit {len(eans)} Artikeln"
    msg["Subject"] = f"Freigabe nötig: {titel} an {gesamt} Kontakte [{kennung}]"
    msg["From"] = formataddr(("Ghostwriter", os.environ["MAIL_FROM"]))
    msg["To"] = os.getenv("FREIGABE_AN", os.environ["MAIL_FROM"])
    kopf = (
        f"Moin Marc,\n\n{anlass}. Bereit zum Versand:\n\n{zeilen}\n  Gesamt: {gesamt} Mails\n\n"
        "Antworte einfach auf diese Mail:\n"
        "  FREIGABE  → wird spätestens in einer Stunde verschickt\n"
        "  STOPP     → wird verworfen\n"
        + ("  MIX       → neu gemischt, auch ältere Artikel – danach kommt eine neue Freigabe-Mail\n"
           if key == "antrag" else "") + "\n"
        "Etwas ändern? Nicht hier antworten, sondern Claude im Chat sagen. Danach kommt\n"
        "automatisch eine neue Freigabe-Mail mit der geänderten Fassung – diese hier gilt dann nicht mehr.\n\n"
        f"Ohne Antwort verfällt der Antrag nach {GUELTIG_TAGE} Tagen.\n"
        "Im Anhang je Liste eine Beispiel-Mail. Darunter das erste Beispiel so, wie der Kunde es sieht.\n"
    )
    msg.set_content(kopf + "\n--- Beispiel ---\n\n" + beispiel.get_body(("plain",)).get_content())
    # Beispiel im Original-Aussehen (Tabelle, Banner, Signatur) unter die Zusammenfassung setzen
    html_teil = beispiel.get_body(("html",))
    kopf_html = "<div style='font-family:Arial,sans-serif;font-size:14px'>" + html.escape(kopf).replace("\n", "<br>") + "</div>"
    trenner = (f"<hr><p style='font-family:Arial,sans-serif;color:#888;font-size:12px'>"
               f"Beispiel an {html.escape(beispiel['To'])} – Betreff: {html.escape(beispiel['Subject'])}</p>")
    msg.add_alternative(kopf_html + trenner + html_teil.get_content(), subtype="html")
    for bild in beispiel.walk():
        if bild.get_content_maintype() == "image":
            msg.get_payload()[1].add_related(bild.get_payload(decode=True), "image", bild.get_content_subtype(),
                                             cid=bild["Content-ID"])
    for name, mails in mails_by_list.items():
        # als Datei (base64) anhängen – eingebettet als message/rfc822 hätte sie Zeilen
        # über 998 Zeichen, die IONOS mit „501 line too long“ ablehnt
        msg.add_attachment(bytes(mails[0][1]), maintype="application", subtype="octet-stream",
                           filename=f"Beispiel {name}.eml")
    mailer.send_raw(msg)
    shutil.copyfile(mailer.STOCK_CSV, BESTAND_ANTRAG)
    state[key] = {"kennung": kennung, "eans": sorted(eans), "version": code_version(),
                       "erstellt": datetime.now().isoformat(timespec="minutes")}
    mailer.save_state(state)
    return kennung


def _first_line(msg: email.message.Message) -> str:
    """Erste eigene Zeile der Antwort (ohne Zitat)."""
    part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None)
    if part is None:
        return ""
    text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(">"):
            return line.lower()
    return ""


VERZOEGERUNG = timedelta(minutes=5)  # Marc: Versand genau 5 Minuten nach seiner FREIGABE


def check_answer(kennung: str) -> str | None:
    """'ja', 'nein', 'mix' oder None (noch keine Antwort)."""
    return check_answer_at(kennung)[0]


def check_answer_at(kennung: str) -> tuple[str | None, datetime | None]:
    """Wie check_answer, dazu der Zeitpunkt der Antwort (Date-Kopf der Mail, mit Zeitzone)."""
    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"])
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, "SUBJECT", f'"{kennung}"')
        for num in reversed(data[0].split()):
            _, raw = imap.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
            if subject.startswith("Freigabe nötig"):
                continue  # die Anfrage selbst, keine Antwort
            line = _first_line(msg)
            try:
                zeit = email.utils.parsedate_to_datetime(msg["Date"])
            except (TypeError, ValueError):
                zeit = None
            for antwort, woerter in (("nein", NEIN), ("mix", MIX), ("ja", JA)):
                if any(line.startswith(w) for w in woerter):
                    return antwort, zeit
    return None, None


def versand_ab(zeit: datetime | None) -> datetime:
    """Frühester Versand nach einer FREIGABE (lokale Zeit)."""
    if zeit is None:
        return datetime.now()
    return (zeit + VERZOEGERUNG).astimezone().replace(tzinfo=None)


def expired(antrag: dict) -> bool:
    return datetime.fromisoformat(antrag["erstellt"]) < datetime.now() - timedelta(days=GUELTIG_TAGE)
