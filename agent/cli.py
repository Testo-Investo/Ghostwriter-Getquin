"""Einstieg: python -m agent.cli <stock|whoami|catalog|export-chats>"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .catalog import download_public_excel, load_catalog, parse_products
from .graph import GraphClient
from .stock import available, parse_stock_csv
from .teams_export import export_chats


def _save_catalog(products: list[dict]) -> None:
    Path("data").mkdir(exist_ok=True)
    Path("data/catalog.json").write_text(json.dumps(products, ensure_ascii=False, indent=2, default=str))
    print(f"{len(products)} Produkte geladen → data/catalog.json")
    if products:
        print("Spalten:", ", ".join(products[0].keys()))


def main() -> None:
    load_dotenv()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd not in {"stock", "whoami", "catalog", "export-chats"}:
        print(__doc__)
        return
    if cmd == "stock":
        items = available(parse_stock_csv(Path(os.getenv("STOCK_CSV", "data/warenbestand.csv")).read_text()))
        items.sort(key=lambda i: i.verfuegbar * (i.ek_avg or 0), reverse=True)
        print(f"{len(items)} Artikel verfügbar")
        for i in items:
            marge = f"{i.marge_letzter_vk * 100:5.1f} %" if i.marge_letzter_vk is not None else "    –  "
            vk = f"{i.vk_last:>9.2f} €" if i.vk_last else "        – "
            print(f"  {i.artikel[:55]:<55} {i.verfuegbar:>6} Stk  EK {i.ek_avg or 0:>9.2f} €  letzter VK {vk}  {marge}")
        return
    sheet = os.getenv("PRODUCT_EXCEL_SHEET") or None
    if cmd == "catalog" and os.getenv("PRODUCT_EXCEL_FILE"):
        _save_catalog(parse_products(Path(os.environ["PRODUCT_EXCEL_FILE"]).read_bytes(), sheet))
        return
    if cmd == "catalog" and os.getenv("PRODUCT_EXCEL_PUBLIC_URL"):
        _save_catalog(parse_products(download_public_excel(os.environ["PRODUCT_EXCEL_PUBLIC_URL"]), sheet))
        return
    graph = GraphClient()

    if cmd == "whoami":
        me = graph.get("/me")
        print(f"Angemeldet als {me['displayName']} <{me.get('mail') or me['userPrincipalName']}>")

    elif cmd == "catalog":
        products = load_catalog(graph, os.environ["PRODUCT_EXCEL_SHARE_URL"], sheet)
        _save_catalog(products)

    elif cmd == "export-chats":
        summary = export_chats(graph, int(os.getenv("CHAT_HISTORY_MONTHS", "12")))
        summary.sort(key=lambda s: s["letzte"], reverse=True)
        print(f"{len(summary)} Kundenchats exportiert → data/chats/")
        for s in summary:
            print(f"  {s['kunde']:<35} {s['nachrichten']:>5} Nachrichten  (letzte: {s['letzte'][:10]})")


if __name__ == "__main__":
    main()
