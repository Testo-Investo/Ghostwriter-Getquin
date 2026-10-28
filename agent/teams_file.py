"""Teams-Datenexport (privates Teams, messages.json) einlesen.

Marcs Teams ist ein privates Microsoft-Konto, daher gibt es keine API –
der Chatverlauf kommt aus dem Datenexport. Ergebnis pro 1:1-Chat: Kunde,
Nachrichten (von Marc / vom Kunden) als Klartext.
"""

import json
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

TEXT_TYPES = {"RichText", "RichText/Html", "Text"}


@dataclass
class Message:
    zeit: str
    von_marc: bool
    text: str


@dataclass
class Chat:
    id: str
    kunde: str
    kunde_id: str
    nachrichten: list[Message] = field(default_factory=list)

    @property
    def von_marc(self) -> list[Message]:
        return [m for m in self.nachrichten if m.von_marc]

    @property
    def vom_kunden(self) -> list[Message]:
        return [m for m in self.nachrichten if not m.von_marc]


def plain_text(html: str) -> str:
    # Zitierte Antworten (blockquote) gehören zur Vorgängernachricht
    html = re.sub(r"<blockquote.*?</blockquote>", "", html or "", flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", html, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "", html))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_QUOTED_NAME = re.compile(r'itemprop="mri" itemid="([^"]+)">([^<]+)</strong>')


def _known_names(export: dict) -> dict[str, str]:
    """Namen zu IDs – aus Absendernamen und aus zitierten Antworten (blockquote)."""
    names = {}
    for conv in export["conversations"]:
        for m in conv.get("MessageList", []):
            if m.get("displayName") and m.get("from"):
                names.setdefault(m["from"], m["displayName"])
            for mri, name in _QUOTED_NAME.findall(m.get("content") or ""):
                names.setdefault(mri, unescape(name).strip())
    return names


def _partner(conv: dict, owner: str, names: dict[str, str]) -> tuple[str, str | None]:
    """(ID, Name) des Chatpartners. Im Export steht unter "members" mal eine ID
    ("orgid:…", "live:…"), mal direkt der Anzeigename."""
    try:
        members = json.loads((conv.get("threadProperties") or {}).get("members") or "[]")
    except ValueError:
        members = []
    others = [m for m in members if m not in ("Export Owner", owner, owner.removeprefix("8:"))]
    sender = next((m["from"] for m in conv.get("MessageList", []) if m.get("from") and m["from"] != owner), "")
    if others and ":" not in others[0] and others[0] != "Unknown User":
        return sender or others[0], others[0]
    pid = (others[0] if others[0].startswith("8:") else f"8:{others[0]}") if others else sender
    return pid, names.get(pid) or names.get(sender)


def load_chats(path: str | Path) -> tuple[str, list[Chat]]:
    """Nur 1:1-Chats (2 Mitglieder) mit Textnachrichten, älteste Nachricht zuerst."""
    export = json.loads(Path(path).read_text())
    owner = export["userId"]
    names = _known_names(export)
    chats = []
    for conv in export["conversations"]:
        props = conv.get("threadProperties") or {}
        if props.get("membercount") != 2:
            continue
        kunde_id, kunde = _partner(conv, owner, names)
        msgs = []
        for m in conv.get("MessageList", []):
            if m.get("messagetype") not in TEXT_TYPES:
                continue
            text = plain_text(m.get("content", ""))
            if not text:
                continue
            von_marc = m.get("from") == owner
            msgs.append(Message(m["originalarrivaltime"], von_marc, text))
        if not msgs:
            continue
        msgs.sort(key=lambda x: x.zeit)
        chats.append(Chat(conv["id"], kunde or "Unbekannt", kunde_id or "", msgs))
    return owner, chats
