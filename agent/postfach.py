"""Postfach aufräumen (stündlich, vor dem Versand).

- Abwesenheitsnotizen → Ordner „Abwesenheitsnotizen“ (nichts wird gelöscht).
- Rückläufer (Adresse existiert nicht, dauerhafter Fehler 5.x.x) → Adresse sofort aus der
  Google-Tabelle löschen, zusätzlich in data/unzustellbar.txt sperren, Mail in den Ordner
  „Unzustellbar“, und Marc bekommt eine Info-Mail mit den gelöschten Adressen.
  Vorübergehende Fehler (4.x.x, „verzögert“) bleiben unangetastet im Posteingang.

Gelöscht werden nur Adressen, die wirklich in einer der Listen stehen.
"""

import email
import email.header
import imaplib
import os
import re
from datetime import date, timedelta
from email.message import EmailMessage, Message
from email.utils import formataddr, parseaddr
from pathlib import Path

from . import mailer

ORDNER_ABWESEND = "Abwesenheitsnotizen"
ORDNER_RUECKLAEUFER = "Unzustellbar"
UNZUSTELLBAR = mailer.UNZUSTELLBAR
TAGE = 14  # so weit zurück im Posteingang schauen

_ADRESSE = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
_ABWESEND_BETREFF = re.compile(
    r"^\s*(automatische antwort|automatic reply|auto[- ]?reply|autoreply|abwesenheit|abwesend|"
    r"out of (the )?office|ooo\b|réponse automatique|risposta automatica|respuesta automática|"
    r"automatisch antwoord|urlaub|vacation|away from)", re.I)
_ABWESEND_TEXT = re.compile(
    r"nicht erreichbar|abwesend|nicht im büro|außer haus|im urlaub|urlaubsbedingt|"
    r"out of (the )?office|on (annual )?leave|on vacation|on holiday|away from (the |my )?office|"
    r"limited access to (my )?e-?mail|will be back|bin ab dem|wieder erreichbar|zurück im büro", re.I)
_RUECK_ABSENDER = re.compile(r"mailer-daemon|postmaster|mail delivery|maildelivery", re.I)
_RUECK_BETREFF = re.compile(
    r"undeliver|unzustellbar|nicht zustellbar|delivery status notification|delivery failure|"
    r"mail delivery failed|returned mail|failure notice|delivery has failed|zustellung fehlgeschlagen", re.I)
_VERZOEGERT = re.compile(r"delay|verzögert|verzoegert|warning|warnung", re.I)


def _betreff(msg: Message) -> str:
    return str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))


def _text(msg: Message, limit: int = 4000) -> str:
    for p in msg.walk():
        if p.get_content_type() == "text/plain" and not p.get_filename():
            raw = p.get_payload(decode=True) or b""
            return raw.decode(p.get_content_charset() or "utf-8", "replace")[:limit]
    for p in msg.walk():
        if p.get_content_type() == "text/html":
            raw = (p.get_payload(decode=True) or b"").decode(p.get_content_charset() or "utf-8", "replace")
            return re.sub(r"<[^>]+>", " ", raw)[:limit]
    return ""


def ist_abwesend(msg: Message) -> bool:
    auto = msg.get("Auto-Submitted", "").lower()
    if auto.startswith("auto-replied") or msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return True
    if msg.get("Precedence", "").lower() == "auto_reply":
        return True
    betreff = _betreff(msg)
    if _ABWESEND_BETREFF.search(betreff):
        return True
    # „Re: Angebot …“ ohne Kennzeichnung (wie bei Think Med): kurzer Text mit typischer Formulierung
    if re.search(r"angebot|offer", betreff, re.I):
        eigener = _text(msg).split("\n>")[0][:800]
        return bool(_ABWESEND_TEXT.search(eigener))
    return False


def unzustellbar(msg: Message) -> tuple[bool, list[tuple[str, str]]]:
    """(ist Rückläufer, [(adresse, grund)] nur dauerhaft fehlgeschlagene Empfänger)."""
    absender = str(msg.get("From", ""))
    betreff = _betreff(msg)
    report = msg.get_content_type() == "multipart/report" and "delivery-status" in msg.get("Content-Type", "").lower()
    if not (report or _RUECK_ABSENDER.search(absender) or _RUECK_BETREFF.search(betreff)):
        return False, []
    out = []
    for p in msg.walk():
        if p.get_content_type() != "message/delivery-status":
            continue
        # Teile: erster Block = Mailserver, danach je Empfänger ein Block
        for block in p.get_payload():
            felder = {k.lower(): str(v) for k, v in block.items()}
            ziel = felder.get("final-recipient") or felder.get("original-recipient") or ""
            status = felder.get("status", "")
            aktion = felder.get("action", "").lower()
            if not ziel or aktion in ("delayed", "relayed", "delivered", "expanded"):
                continue
            if status.startswith("5") or aktion == "failed":
                adresse = ziel.split(";")[-1].strip().strip("<>").lower()
                grund = felder.get("diagnostic-code", status).split(";")[-1].strip()[:160]
                out.append((adresse, grund))
    if out or report:
        return True, out
    if _VERZOEGERT.search(betreff):
        return True, []  # nur Verzögerung, kommt evtl. noch an
    adressen = [a.lower() for a in msg.get_all("X-Failed-Recipients", [])]
    adressen += [a.lower() for a in _ADRESSE.findall(_text(msg))]
    return True, [(a, "unzustellbar") for a in dict.fromkeys(adressen)]


def _ordner(imap: imaplib.IMAP4, name: str) -> str:
    _, liste = imap.list()
    namen = []
    for zeile in liste or []:
        z = zeile.decode(errors="replace")
        m = re.search(r'"([^"]*)"\s*$|(\S+)\s*$', z)
        namen.append((m.group(1) or m.group(2)) if m else z)
    for n in namen:
        if n == name or n.endswith("." + name) or n.endswith("/" + name):
            return n
    for kandidat in (name, f"INBOX.{name}", f"INBOX/{name}"):
        if imap.create(f'"{kandidat}"')[0] == "OK":
            imap.subscribe(f'"{kandidat}"')
            return kandidat
    raise RuntimeError(f"Ordner {name} lässt sich nicht anlegen")


def _verschieben(imap: imaplib.IMAP4, uids: list[bytes], ordner: str) -> None:
    if not uids:
        return
    menge = b",".join(uids).decode()
    if imap.uid("MOVE", menge, f'"{ordner}"')[0] == "OK":
        return
    imap.uid("COPY", menge, f'"{ordner}"')
    imap.uid("STORE", menge, "+FLAGS", r"(\Deleted)")
    imap.expunge()


def aufraeumen(listen: list[Path]) -> dict:
    """Posteingang prüfen. Gibt {'abwesend': n, 'geloescht': [(adresse, liste, grund)], 'fehler', 'gesperrt'} zurück."""
    eigene = {os.environ["MAIL_FROM"].lower(), os.environ["IONOS_SMTP_USER"].lower()}
    in_listen = listen_adressen(listen)
    abwesend, rueck, kaputt = [], [], {}
    with imaplib.IMAP4_SSL("imap.ionos.de") as imap:
        imap.login(os.environ["IONOS_SMTP_USER"], os.environ["IONOS_SMTP_PASSWORD"])
        imap.select("INBOX")
        seit = (date.today() - timedelta(days=TAGE)).strftime("%d-%b-%Y")
        _, data = imap.uid("SEARCH", None, "SINCE", seit)
        for uid in data[0].split():
            _, raw = imap.uid("FETCH", uid, "(BODY.PEEK[])")  # PEEK: bleibt ungelesen
            if not raw or not isinstance(raw[0], tuple):
                continue
            msg = email.message_from_bytes(raw[0][1])
            if parseaddr(str(msg.get("From", "")))[1].lower() in eigene:
                continue  # Freigabe-Mails, Berichte usw.
            ist_rueck, ziele = unzustellbar(msg)
            if ist_rueck:
                treffer = [(a, g) for a, g in ziele if a in in_listen and a not in eigene]
                if treffer:
                    rueck.append(uid)
                    for a, g in treffer:
                        kaputt.setdefault(a, g)
                elif ziele or msg.get_content_type() == "multipart/report":
                    if not _VERZOEGERT.search(_betreff(msg)):
                        rueck.append(uid)  # Rückläufer zu Adressen außerhalb der Listen: nur wegräumen
                continue
            if ist_abwesend(msg):
                abwesend.append(uid)
        kaputt |= {a: g for a, g in mailer.permanent_failures().items() if a in in_listen}  # beim Versand abgelehnt (550)
        geloescht, fehler = entfernen(kaputt, in_listen)
        if fehler:
            rueck = []  # Rückläufer bleiben liegen, nächster Lauf versucht es erneut
        _verschieben(imap, abwesend, _ordner(imap, ORDNER_ABWESEND) if abwesend else "")
        _verschieben(imap, rueck, _ordner(imap, ORDNER_RUECKLAEUFER) if rueck else "")
    return {"geprueft": len(data[0].split()), "abwesend": len(abwesend), "rueck": len(rueck),
            "geloescht": geloescht, "fehler": fehler, "gesperrt": sorted(kaputt) if fehler else []}


def entfernen(kaputt: dict[str, str], in_listen: dict[str, str]) -> tuple[list, str]:
    """Adressen sperren, aus den Google-Tabellen löschen und Marc informieren.

    Gibt ([(adresse, liste, grund)], Fehlertext) zurück. Schon gelöschte Adressen
    (stehen in keiner Liste mehr) werden übersprungen."""
    kaputt = {a: g for a, g in kaputt.items() if a in in_listen}
    if not kaputt:
        return [], ""
    from .gsheet import remove_addresses
    _sperren(kaputt)  # ab sofort nicht mehr anschreiben, auch wenn das Löschen scheitert
    try:
        entfernt = remove_addresses(set(kaputt))  # {adresse: [Listenname, …]}
    except Exception as e:  # z. B. fehlende Rechte
        return [], str(e)[:300]
    geloescht = [(a, ", ".join(entfernt.get(a) or [in_listen[a]]), g) for a, g in kaputt.items()]
    _info_mail(geloescht)
    return geloescht, ""


def listen_adressen(listen: list[Path]) -> dict[str, str]:
    in_listen = {}
    for pfad in listen:
        for r in mailer.load_recipients(pfad, keine_sperre=True):
            in_listen.setdefault(r.email, pfad.stem)
    return in_listen


def _sperren(adressen: dict) -> None:
    UNZUSTELLBAR.parent.mkdir(parents=True, exist_ok=True)
    alt = set(UNZUSTELLBAR.read_text().split()) if UNZUSTELLBAR.exists() else set()
    UNZUSTELLBAR.write_text("\n".join(sorted(alt | set(adressen))) + "\n")


def _info_mail(geloescht: list[tuple[str, str, str]]) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"Ghostwriter: {len(geloescht)} unzustellbare Adressen aus den Listen gelöscht"
    msg["From"] = formataddr(("Ghostwriter", os.environ["MAIL_FROM"]))
    msg["To"] = os.getenv("FREIGABE_AN", os.environ["MAIL_FROM"])
    zeilen = "\n".join(f"  {a}  ({liste})\n      Grund: {g}" for a, liste, g in sorted(geloescht, key=lambda x: (x[1], x[0])))
    msg.set_content(
        "Moin Marc,\n\ndiese Adressen gibt es nicht mehr – die Mails kamen als unzustellbar zurück.\n"
        "Ich habe sie aus den Google-Tabellen im Ordner „Ghostwriter Mailinglisten“ gelöscht:\n\n"
        f"{zeilen}\n\n"
        "Die Rückläufer-Mails liegen im Ordner „Unzustellbar“. Soll eine Adresse doch wieder rein,\n"
        "sag Claude im Chat Bescheid – sie ist zusätzlich gesperrt, damit sie nicht versehentlich\n"
        "wieder angeschrieben wird.\n"
    )
    mailer.send_raw(msg)
