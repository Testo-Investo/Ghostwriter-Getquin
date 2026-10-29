#!/usr/bin/env bash
# Stündlicher Lauf: Änderungen holen, Bestand und Listen laden, bei neuer Ware
# Freigabe-Mail an Marc bzw. nach seiner Freigabe Angebote an alle Listen mailen.
# Alles in main(), damit bash das Skript komplett gelesen hat, bevor git pull es ersetzt.
set -euo pipefail
main() {
  cd /opt/ghostwriter
  local PY=.venv/bin/python
  git pull -q --ff-only   # Änderungen aus dem Chat automatisch übernehmen
  $PY -m agent.cli fetch-stock
  $PY -m agent.cli fetch-lists
  # Abwesenheitsnotizen wegsortieren, Rückläufer aus den Listen löschen – danach Listen neu holen
  if $PY -m agent.cli postfach data/mailinglisten/*.xlsx; then $PY -m agent.cli fetch-lists; else echo "Postfach aufräumen fehlgeschlagen"; fi
  $PY -m agent.cli mail-sonder data/mailinglisten/*.xlsx || echo "Sonderangebot fehlgeschlagen"
  $PY -m agent.cli mail-neu data/mailinglisten/*.xlsx
}
main "$@"
