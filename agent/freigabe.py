"""Freigabe per Antwort-Mail: Marc schaut jeden Versand vorher an.

Ablauf im stündlichen Lauf (`mail-neu`):
1. Neue Ware, kein offener Antrag → Freigabe-Mail an Marc: Artikel, Empfängerzahl je
   Liste und je Liste eine Beispiel-Mail im Anhang. Betreff enthält eine Kennung [GW-…].
2. Marc antwortet mit „FREIGABE“ (oder „ok“/„ja“) → beim nächsten Lauf geht der
   Versand an alle raus. Mit „STOPP“ wird der Antrag verworfen.
3. Ohne Antwort verfällt der Antrag nach 3 Tagen; neue Ware erzeugt dann einen neuen.

Die Antwort wird per IMAP aus Marcs IONOS-Postfach gelesen (gleiche Zugangsdaten).
"""

import email
import imaplib
import os
import secrets
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from . import mailer

IMAP_HOST = "imap.ionos.de"
GUELTIG_TAGE = 3
JA = ("freigabe", "freigeben", "ok", "okay", "ja", "go", "senden")
NEIN = ("stopp", "stop", "nein", "abbrechen", "verwerfen")


def new_request(state: dict, eans: set[str], mails_by_list: dict[str, list]) -> str:
    """Freigabe-Mail an Marc schicken und den Antrag im State merken."""
    kennung = f"GW-{date.today():%m%d}-{secrets.token_hex(2).upper()}"
    gesamt = sum(len(m) for m in mails_by_list.values())
    beispiel = next(iter(mails_by_list.values()))[0][1]
    zeilen = "\n".join(f"  {name}: {len(m)} Mails" for name, m in mails_by_list.items())
    msg = EmailMessage()
    msg["Subject"] = f"Freigabe nötig: Angebot mit {len(eans)} neuen Artikeln an {gesamt} Kontakte [{kennung}]"
    msg["From"] = formataddr(("Ghostwriter", os.environ["MAIL_FROM"]))
    msg["To"] = os.getenv("FREIGABE_AN", os.environ["MAIL_FROM"])
    msg.set_content(
        f"Moin Marc,\n\nneue Ware ist da. Bereit zum Versand:\n\n{zeilen}\n  Gesamt: {gesamt} Mails\n\n"
        "Antworte einfach auf diese Mail:\n"
        "  FREIGABE  → wird spätestens in einer Stunde verschickt\n"
        "  STOPP     → wird verworfen\n\n"
        f"Ohne Antwort verfällt der Antrag nach {GUELTIG_TAGE} Tagen.\n"
        "Im Anhang je Liste eine Beispiel-Mail, genau so wie der Kunde sie sieht.\n\n"
        "--- Beispiel (Text) ---\n\n" + beispiel.get_body(("plain",)).get_content()
    )
    for name, mails in mails_by_list.items():
        # als Datei (base64) anhängen – eingebettet als message/rfc822 hätte sie Zeilen
        # über 998 Zeichen, die IONOS mit „501 line too long“ ablehnt
        msg.add_attachment(bytes(mails[0][1]), maintype="application", subtype="octet-stream",
                           filename=f"Beispiel {name}.eml")
    mailer.send_raw(msg)
    state["antrag"] = {"kennung": kennung, "eans": sorted(eans), "erstellt": datetime.now().isoformat(timespec="minutes")}
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


def check_answer(kennung: str) -> str | None:
    """'ja', 'nein' oder None (noch keine Antwort)."""
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
            if any(line.startswith(w) for w in NEIN):
                return "nein"
            if any(line.startswith(w) for w in JA):
                return "ja"
    return None


def expired(antrag: dict) -> bool:
    return datetime.fromisoformat(antrag["erstellt"]) < datetime.now() - timedelta(days=GUELTIG_TAGE)
