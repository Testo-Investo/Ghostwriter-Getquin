"""Einstieg: python -m agent.cli <befehl>

  stock | watch | offer | profiles
  fetch-stock   Warenbestand aus Google Sheets laden (Server, Dienstkonto)
  fetch-lists   Mailinglisten aus dem Google-Drive-Ordner holen
  smtp-test     eine Testmail an MAIL_FROM schicken (prüft IONOS-Zugang)
  mail-preview <liste.xlsx> [weitere Listen …]
  mail-send <liste.xlsx> [weitere Listen …] [--test deine@adresse.de]
  mail-neu <liste.xlsx> [weitere Listen …] [--vorschau] [--force] [--ohne-freigabe]
      im Lauf um 9:30 (ANGEBOT_UM): bei neuer Ware (noch in keiner Mail) Freigabe-Mail an Marc;
      stündlich: nach Antwort „FREIGABE“ Versand an alle, höchstens einmal pro Tag
  mail-sonder <liste.xlsx> [weitere Listen …]
      Sonderangebot aus config/sonderangebot.json: Freigabe-Mail, nach FREIGABE an alle
      --nachholen: freigegebenes Sonderangebot an alle, die es laut Protokoll noch nicht bekommen haben
  --nur-antworten (mail-neu, mail-sonder): nur Antworten auf offene Freigaben bearbeiten (Minuten-Lauf)
  postfach <liste.xlsx> [weitere Listen …]
      Abwesenheitsnotizen wegsortieren, Rückläufer-Adressen aus den Listen löschen
  versand-status [JJJJ-MM-TT]   Protokoll eines Tages auswerten (Betreff × Status)
  whoami | catalog | export-chats
"""

import json
import os
import secrets
from datetime import date, datetime
import sys
from pathlib import Path

from dotenv import load_dotenv

from .catalog import download_public_excel, load_catalog, parse_products
from .graph import GraphClient
from . import freigabe, mailer, sonder
from .profiles import brands_from_stock, build_profile, export_rows
from .teams_file import load_chats
from .offer import build_offer, instant_offer, render_text
from .stock import offerable, parse_stock_csv
from .teams_export import export_chats
from .watch import diff, fresh_arrivals, load_latest_snapshot, save_snapshot


def _save_catalog(products: list[dict]) -> None:
    Path("data").mkdir(exist_ok=True)
    Path("data/catalog.json").write_text(json.dumps(products, ensure_ascii=False, indent=2, default=str))
    print(f"{len(products)} Produkte geladen → data/catalog.json")
    if products:
        print("Spalten:", ", ".join(products[0].keys()))


_SPERRE = []
NACHHOL_VERSUCHE = 3  # abgebrochenen Versand so oft im Stundenlauf fortsetzen, dann aufgeben


def _versand_sperre() -> None:
    """Wartet, bis kein anderer Versand mehr läuft (hält die Sperre bis Prozessende)."""
    import fcntl
    if _SPERRE:
        return  # dieser Prozess hat sie schon
    for ordner in (Path("/run"), Path("data")):
        try:
            f = (ordner / "ghostwriter-versand.lock").open("w")
            break
        except OSError:
            continue
    else:
        return
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Ein anderer Versand läuft gerade – warte, bis er fertig ist …")
        fcntl.flock(f, fcntl.LOCK_EX)
    _SPERRE.append(f)


def main() -> None:
    load_dotenv()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd not in {"fetch-stock", "fetch-lists", "smtp-test", "stock", "watch", "offer", "profiles", "mail-preview", "mail-send", "mail-neu", "mail-sonder", "postfach", "versand-status", "whoami", "catalog", "export-chats"}:
        print(__doc__)
        return
    if cmd == "fetch-stock":
        from .gsheet import fetch_stock_csv
        print(f"Warenbestand geladen → {fetch_stock_csv()}")
        return
    if cmd == "fetch-lists":
        from .gsheet import fetch_mailing_lists
        for path in fetch_mailing_lists():
            print(f"  {path}")
        return
    if cmd == "versand-status":
        import csv
        from collections import Counter
        tag = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()
        log = mailer.OUTBOX / f"versand_{tag}.csv"
        if not log.exists():
            print(f"Kein Protokoll für {tag}.")
            return
        rows = list(csv.DictReader(log.open(newline="")))
        zaehler = Counter((r["betreff"], r["status"].split(":")[0]) for r in rows)
        print(f"{len(rows)} Einträge am {tag}, {len({r['email'] for r in rows})} verschiedene Adressen:")
        for (betreff, status), n in sorted(zaehler.items()):
            print(f"  {n:4}  {status:9} {betreff}")
        for r in rows:
            if r["status"].startswith("fehler"):
                print(f"  Fehler {r['email']}: {r['status'][:150]}")
        return
    if cmd == "postfach":
        from . import postfach
        ergebnis = postfach.aufraeumen([Path(a) for a in sys.argv[2:]])
        print(f"Postfach: {ergebnis['geprueft']} Mails geprüft, {ergebnis['abwesend']} Abwesenheitsnotizen und "
              f"{ergebnis['rueck']} Rückläufer weggeräumt, {len(ergebnis['geloescht'])} unzustellbare Adressen gelöscht.")
        for adresse, liste, grund in ergebnis["geloescht"]:
            print(f"  {adresse} ({liste}): {grund}")
        if ergebnis["fehler"]:
            print(f"Löschen in den Listen fehlgeschlagen ({ergebnis['fehler']}) – gesperrt sind trotzdem: "
                  + ", ".join(ergebnis["gesperrt"]))
        return
    if cmd == "smtp-test":
        mailer.smtp_test(os.environ["MAIL_FROM"])
        print(f"Testmail an {os.environ['MAIL_FROM']} verschickt – bitte Posteingang prüfen.")
        return
    if cmd == "stock":
        items = offerable(parse_stock_csv(Path(os.getenv("STOCK_CSV", "data/warenbestand.csv")).read_text()))
        items.sort(key=lambda i: i.verfuegbar * i.ek_avg, reverse=True)
        print(f"{len(items)} Artikel anbietbar")
        for i in items:
            quelle = "letzter VK" if i.vk_last else "EK + 10 %"
            print(f"  {i.artikel[:55]:<55} {i.ean:<14} {i.verfuegbar:>6} Stk  {i.angebotspreis:>9.2f} €  ({quelle})")
        return
    if cmd == "watch":
        current = parse_stock_csv(Path(os.getenv("STOCK_CSV", "data/warenbestand.csv")).read_text())
        path = save_snapshot(current)
        previous = load_latest_snapshot(before=path)
        print(f"Snapshot gespeichert: {path}")
        fresh = fresh_arrivals(current)
        print(f"\n{len(fresh)} neue Wareneingänge (letzte 7 Tage), zuerst anbieten:")
        for i in fresh:
            print(f"  {i.letzter_we}  {i.artikel[:55]:<55} {i.verfuegbar:>6} Stk  {i.angebotspreis:>9.2f} €")
        if previous is None:
            print("\nErster Lauf – noch kein Vergleich möglich.")
            return
        events = diff(previous, current)
        print(f"\n{len(events)} Änderungen seit dem letzten Abruf:")
        for e in events:
            print("  " + e.text())
        instant = instant_offer(current, events)
        if instant:
            print(f"\n⚡ Sofort-Angebot vorbereitet ({len(instant)} Artikel):\n")
            print(render_text(instant))
        return
    if cmd == "offer":
        current = parse_stock_csv(Path(os.getenv("STOCK_CSV", "data/warenbestand.csv")).read_text())
        print(render_text(build_offer(current, max_rest=int(os.getenv("OFFER_MAX_REST", "20")))))
        return
    if cmd == "profiles":
        # Kundenprofile aus dem Teams-Export fürs Dashboard (nur abgeleitete Felder)
        current = parse_stock_csv(Path(os.getenv("STOCK_CSV", "data/warenbestand.csv")).read_text())
        _, chats = load_chats(os.getenv("TEAMS_EXPORT", "data/teams_export/messages.json"))
        since = os.getenv("KUNDEN_AKTIV_SEIT", "2026-05-01")
        active = [c for c in chats if c.nachrichten[-1].zeit >= since]
        profiles = sorted((build_profile(c, brands_from_stock(current)) for c in active),
                          key=lambda p: p.letzte_nachricht, reverse=True)
        rows = export_rows(profiles)
        Path("data/kunden.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"{len(rows)} Kundenprofile (aktiv seit {since}) → data/kunden.json")
        return
    if cmd in ("mail-preview", "mail-send", "mail-neu", "mail-sonder"):
        if "--vorschau" not in sys.argv:
            _versand_sperre()  # nie zwei Versände gleichzeitig (Timer + Befehl von Hand)
        current = parse_stock_csv(Path(os.getenv("STOCK_CSV", "data/warenbestand.csv")).read_text())
        args = sys.argv[2:]
        flags = {a for a in args if a in ("--vorschau", "--force", "--ohne-freigabe", "--nachholen", "--nur-antworten")}
        test_to = None
        if "--test" in args:
            test_to = args[args.index("--test") + 1]
            args = args[:args.index("--test")] + args[args.index("--test") + 2:]
        args = [a for a in args if a not in flags]
        absender = os.getenv("MAIL_FROM", "marc@neobution.com")
        name = os.getenv("MAIL_NAME", "Marc Knieb")
        signatur = mailer.SIGNATUR.read_text() if mailer.SIGNATUR.exists() else ""

        listen_frisch = []

        def build(neu_eans, stock=None, feste=None, mix=None, gewaehlt=None):
            if not listen_frisch and os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") and "--vorschau" not in flags:
                from .gsheet import fetch_mailing_lists
                fetch_mailing_lists()  # immer der neueste Stand der Listen, auch beim Befehl von Hand
                listen_frisch.append(True)
            stock = current if stock is None else stock
            seen: set[str] = set()  # wer in mehreren Listen steht, bekommt nur eine Mail
            out = {}
            for liste in args:
                recipients = [r for r in mailer.load_recipients(liste) if r.email not in seen]
                seen |= {r.email for r in recipients}
                out[Path(liste).stem] = mailer.build_all(recipients, stock, absender, name, neu_eans, signatur, feste,
                                                         mix, gewaehlt)
            return out

        def faellig(antrag, zeit) -> bool:
            """FREIGABE erst 5 Minuten nach Marcs Antwort ausführen (Zeit zum Zurückziehen per STOPP)."""
            ab = freigabe.versand_ab(zeit)
            if datetime.now() < ab:
                print(f"Freigabe {antrag['kennung']} erhalten – Versand um {ab:%H:%M} Uhr.")
                return False
            return True

        def mix_request(state, anlass):
            """Gemischtes Angebot (auch ältere Artikel) zur Freigabe schicken."""
            seed, gewaehlt = secrets.token_hex(4), set()
            by_list = build(None, mix=seed, gewaehlt=gewaehlt)
            kennung = freigabe.new_request(state, gewaehlt, by_list, anlass=anlass,
                                           titel=f"Mix-Angebot (je Kunde bis {mailer.MAX_ARTIKEL} Artikel)")
            state["antrag"]["mix"] = seed; mailer.save_state(state)
            print(f"Freigabe-Mail {kennung} (Mix) an {os.getenv('FREIGABE_AN', absender)} geschickt – warte auf Antwort.")

        def send(by_list, was="Das Angebot", bericht_nur_bei_erfolg=False):
            ergebnis = {}
            if "--nachholen" in flags:  # nur wer laut Protokoll noch nichts bekommen hat
                by_list = {stem: offen for stem, mails in by_list.items() if (offen := mailer.noch_offen(mails))}
                was += " (nachgeholt)"
            if not by_list:
                print("Alle haben es schon bekommen – nichts nachzuholen.")
                return {}
            for stem, mails in by_list.items():
                folder = mailer.write_preview(mails, stem)
                print(f"{stem}: {len(mails)} Mails → {folder}/vorschau.html")
                if not ("--vorschau" in flags):
                    log, ok, fehler = mailer.send_all(mails, test_to)
                    ergebnis[stem] = (ok, len(mails), fehler)
                    print(("  Testversand an " + test_to if test_to else "  an Kunden versendet") + f" → {log}")
            if ergebnis and not test_to:
                if not (bericht_nur_bei_erfolg and not any(e[0] for e in ergebnis.values())):
                    mailer.versand_bericht(was, ergebnis)  # Info an Marc, dass alles raus ist
                from . import postfach  # beim Versand abgelehnte Adressen (550) gleich aus den Listen löschen
                _, fehler = postfach.entfernen(mailer.permanent_failures(), postfach.listen_adressen([Path(a) for a in args]))
                if fehler:
                    print(f"Unzustellbare Adressen nicht gelöscht: {fehler}")
            return ergebnis

        def ohne_bereits_gesendete(by_list, seit):
            """Wer seit Versandbeginn schon „gesendet“ hat, bekommt nichts mehr (nie doppelt)."""
            schon = mailer.gesendet_seit(seit)
            return {stem: offen for stem, mails in by_list.items()
                    if (offen := [m for m in mails if m[0].email not in schon])}

        def vollstaendig(ergebnis) -> bool:
            """Keine vorübergehenden Fehler mehr offen (dauerhafte 5xx zählen als erledigt)."""
            return not any(not mailer.dauerhaft(f) for _, _, fl in ergebnis.values() for _, f in fl)

        if cmd == "mail-sonder":
            angebot = sonder.load()
            state = mailer.load_state()
            erledigt = state.setdefault("sonder_erledigt", [])
            if angebot and "--nachholen" in flags:
                if angebot[0] not in erledigt:
                    print("Dieses Sonderangebot wurde noch nicht freigegeben – nichts nachzuholen.")
                    return
                send(build(None, feste=angebot[2]), was="Das Sonderangebot")  # schon freigegeben, nur Lücken füllen
                return
            if angebot and angebot[0] in erledigt and "--nur-antworten" not in flags:
                # Heute freigegeben und verschickt? Dann bekommen neu eingetragene Kontakte es noch nach.
                by_list = build(None, feste=angebot[2])
                if mailer.heute_verschickt([m for mails in by_list.values() for m in mails]):
                    flags.add("--nachholen")
                    send(by_list, was="Das Sonderangebot")
                    return
            if angebot is None or angebot[0] in erledigt:
                print("Kein offenes Sonderangebot.")
                return
            sid, anlass, artikel = angebot
            antrag = state.get("sonder_antrag")
            if antrag and (antrag.get("id") != sid or antrag.get("version") != freigabe.code_version()):
                state.pop("sonder_antrag"); mailer.save_state(state)
                print(f"Sonder-Freigabe {antrag['kennung']} ist veraltet – neue Freigabe-Mail folgt.")
                antrag = None
            if antrag:
                antwort, zeit = freigabe.check_answer_at(antrag["kennung"])
                if antwort == "ja" and not faellig(antrag, zeit):
                    return
                if antwort == "ja":
                    send(build(None, feste=artikel), was="Das Sonderangebot")
                if antwort in ("ja", "nein"):
                    erledigt.append(sid); state.pop("sonder_antrag"); mailer.save_state(state)
                    print(f"Sonderangebot {sid}: {'verschickt' if antwort == 'ja' else 'verworfen'}.")
                elif freigabe.expired(antrag):
                    erledigt.append(sid); state.pop("sonder_antrag"); mailer.save_state(state)
                    print(f"Sonder-Freigabe {antrag['kennung']} ohne Antwort verfallen.")
                else:
                    print(f"Warte auf Sonder-Freigabe {antrag['kennung']}.")
                return
            if "--nur-antworten" in flags:
                return  # Minuten-Lauf: nur Antworten prüfen, keine neuen Freigabe-Mails
            kennung = freigabe.new_request(state, {a.ean for a in artikel}, build(None, feste=artikel),
                                           key="sonder_antrag", anlass=anlass, prefix="SO")
            state["sonder_antrag"]["id"] = sid; mailer.save_state(state)
            print(f"Sonder-Freigabe {kennung} an {os.getenv('FREIGABE_AN', absender)} geschickt.")
            return

        if cmd != "mail-neu":
            if cmd == "mail-preview":
                flags.add("--vorschau")
            send(build(None))
            return

        state = mailer.load_state()
        antrag = state.get("antrag")
        if antrag and not antrag.get("versand_gestartet") and "--vorschau" not in flags:
            # ältere Anträge: Versand lief schon an, wenn seit Antrag Mails rausgingen (Abbruch mittendrin)
            seit = antrag["erstellt"].replace("T", " ")
            if seit[:10] == date.today().isoformat() and mailer.gesendet_seit(seit):
                antrag["versand_gestartet"] = seit; mailer.save_state(state)
        if antrag and antrag.get("versand_gestartet"):
            # Freigabe wurde schon ausgeführt, aber nicht alle Mails gingen raus → Rest nachholen,
            # nur im Stundenlauf (nicht jede Minute) und höchstens NACHHOL_VERSUCHE Mal
            if "--nur-antworten" in flags:
                return
            versuche = antrag.get("nachhol_versuche", 0)
            if antrag["versand_gestartet"][:10] != date.today().isoformat():
                # Rest vom Vortag: aufgeben, heutiges Angebot aber nicht blockieren
                state["angekuendigt"] = sorted(set(state["angekuendigt"]) | set(antrag["eans"]))
                state.pop("antrag"); mailer.save_state(state)
                print(f"Freigabe {antrag['kennung']}: Rest vom Vortag aufgegeben.")
                antrag = None
            elif versuche >= NACHHOL_VERSUCHE:
                mailer.mark_announced(state, set(antrag["eans"]))
                print(f"Freigabe {antrag['kennung']}: Rest nach {versuche} Versuchen aufgegeben.")
                return
        if antrag and antrag.get("versand_gestartet"):
            versuche = antrag.get("nachhol_versuche", 0)
            antrag["nachhol_versuche"] = versuche + 1; mailer.save_state(state)
            by_list = ohne_bereits_gesendete(build(set(antrag["eans"]), freigabe.approved_stock(current),
                                                   mix=antrag.get("mix")), antrag["versand_gestartet"])
            ergebnis = send(by_list, was="Das Angebot (Rest nachgeholt)", bericht_nur_bei_erfolg=True) if by_list else {}
            if not by_list or vollstaendig(ergebnis):
                mailer.mark_announced(state, set(antrag["eans"]))
                print(f"Freigabe {antrag['kennung']}: jetzt vollständig verschickt.")
            else:
                print(f"Freigabe {antrag['kennung']}: noch nicht alle raus – nächster Lauf versucht den Rest.")
            return
        if antrag and antrag.get("version") != freigabe.code_version():
            # Texte/Regeln wurden geändert, seit Marc die Mail gesehen hat → alte Freigabe gilt nicht
            state.pop("antrag"); mailer.save_state(state)
            print(f"Freigabe {antrag['kennung']} ist veraltet (Änderungen seitdem) – neue Freigabe-Mail folgt.")
            antrag = None
        if antrag:
            antwort, zeit = freigabe.check_answer_at(antrag["kennung"])
            if antwort == "ja" and not faellig(antrag, zeit):
                return
            if antwort == "ja":
                eans = set(antrag["eans"])
                if "--vorschau" in flags or test_to:
                    send(build(eans, freigabe.approved_stock(current), mix=antrag.get("mix")))
                    return
                antrag["versand_gestartet"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); mailer.save_state(state)
                ergebnis = send(build(eans, freigabe.approved_stock(current), mix=antrag.get("mix")))  # angesehener Stand
                if vollstaendig(ergebnis):
                    mailer.mark_announced(state, eans)
                    print(f"Freigabe {antrag['kennung']} erhalten – verschickt.")
                else:
                    print(f"Freigabe {antrag['kennung']} erhalten – nicht alle raus, nächster Lauf holt den Rest nach.")
            elif antwort == "mix":
                state.pop("antrag"); mailer.save_state(state)
                print(f"Freigabe {antrag['kennung']}: Marc möchte einen Mix.")
                mix_request(state, "Neu gemischt, wie gewünscht – neue und ältere Artikel")
            elif antwort == "nein":
                mailer.mark_announced(state, set(antrag["eans"]))  # diese Artikel nicht erneut anfragen
                print(f"Freigabe {antrag['kennung']} abgelehnt – verworfen.")
            elif freigabe.expired(antrag):
                state.pop("antrag"); mailer.save_state(state)
                print(f"Freigabe {antrag['kennung']} ohne Antwort verfallen.")
            else:
                print(f"Warte auf Freigabe {antrag['kennung']}.")
            return

        if "--nur-antworten" in flags:
            return  # Minuten-Lauf: neue Freigabe-Mails nur im Stundenlauf
        um = int(os.getenv("ANGEBOT_UM", "9"))  # Marc: Freigabe-Mail im 9-Uhr-Lauf (9:30), Versand nach FREIGABE ab 10:30
        if datetime.now().hour != um and "--force" not in flags:
            print(f"Neues Angebot nur im Lauf zwischen {um} und {um + 1} Uhr – jetzt nichts zu tun.")
            return
        neu_eans = mailer.new_arrivals_to_announce(current, state)
        if state["zuletzt"] == date.today().isoformat() and "--force" not in flags:
            print("Heute wurde schon verschickt – morgen geht's weiter.")
            return
        if not neu_eans:  # keine neue Ware: trotzdem ein Angebot, bunt gemischt aus dem Bestand
            mix_request(state, "Keine neue Ware seit der letzten Mail – hier ein Mix aus dem Bestand")
            return
        by_list = build(neu_eans)
        if "--ohne-freigabe" in flags:
            send(by_list)
            if "--vorschau" not in flags and not test_to:
                mailer.mark_announced(state, neu_eans)
            return
        kennung = freigabe.new_request(state, neu_eans, by_list)
        print(f"Freigabe-Mail {kennung} an {os.getenv('FREIGABE_AN', absender)} geschickt – warte auf Antwort.")
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
