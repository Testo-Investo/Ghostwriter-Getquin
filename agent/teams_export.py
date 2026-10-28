"""Teams-1:1-Chats exportieren – Grundlage für Stilprofil und Kundenprofile.

Nur lesend. Ergebnis: data/chats/<chat_id>.json pro Kunde.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

from .graph import GraphClient

OUT_DIR = Path("data/chats")


def _plain_text(body: dict) -> str:
    text = body.get("content", "")
    if body.get("contentType") == "html":
        text = re.sub(r"<br\s*/?>|</p>", "\n", text, flags=re.I)
        text = unescape(re.sub(r"<[^>]+>", "", text))
    return text.strip()


def export_chats(graph: GraphClient, months: int = 12) -> list[dict]:
    me = graph.get("/me")
    since = datetime.now(timezone.utc) - timedelta(days=30 * months)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    chats = graph.paged("/me/chats", params={"$filter": "chatType eq 'oneOnOne'", "$expand": "members"})
    for chat in chats:
        members = chat.get("members", [])
        partner = next((m for m in members if m.get("userId") != me["id"]), {})
        own_tenant = next((m.get("tenantId") for m in members if m.get("userId") == me["id"]), None)
        messages = []
        for msg in graph.paged(f"/me/chats/{chat['id']}/messages", params={"$top": 50}):
            created = datetime.fromisoformat(msg["createdDateTime"].replace("Z", "+00:00"))
            if created < since:
                break  # Nachrichten kommen neueste zuerst
            if msg.get("messageType") != "message" or not msg.get("from", {}).get("user"):
                continue
            messages.append({
                "zeit": msg["createdDateTime"],
                "von_marc": msg["from"]["user"]["id"] == me["id"],
                "text": _plain_text(msg.get("body", {})),
            })
        if not messages:
            continue
        messages.reverse()
        record = {
            "chat_id": chat["id"],
            "kunde": partner.get("displayName", "Unbekannt"),
            "kunde_email": partner.get("email"),
            "extern": bool(partner.get("tenantId")) and partner["tenantId"] != own_tenant,
            "nachrichten": messages,
        }
        safe_name = re.sub(r"[^\w-]", "_", chat["id"])[:80]
        (OUT_DIR / f"{safe_name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
        summary.append({
            "kunde": record["kunde"],
            "nachrichten": len(messages),
            "von_marc": sum(m["von_marc"] for m in messages),
            "letzte": messages[-1]["zeit"],
        })
    return summary
