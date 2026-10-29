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
  $PY -m agent.cli mail-neu data/mailinglisten/*.xlsx
}
main "$@"
