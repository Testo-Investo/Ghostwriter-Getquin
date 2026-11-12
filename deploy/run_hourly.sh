#!/usr/bin/env bash
# Stündlicher Lauf: Änderungen holen, Bestand und Listen laden, Postfach aufräumen,
# Freigaben prüfen und freigegebene Angebote verschicken. Die Freigabe-Mail für das
# normale Angebot kommt nur im Lauf um 10:05 Uhr (mail-neu, ANGEBOT_UM).
# Alles in main(), damit bash das Skript komplett gelesen hat, bevor git pull es ersetzt.
set -euo pipefail
main() {
  cd /opt/ghostwriter
  local PY=.venv/bin/python
  exec 9>/run/ghostwriter.lock
  flock 9                 # nicht gleichzeitig mit dem Minuten-Lauf (sonst doppelter Versand)
  git pull -q --ff-only   # Änderungen aus dem Chat automatisch übernehmen
  # Zeitpläne aus dem Repo übernehmen, falls sie sich geändert haben
  local unit neu=""
  for unit in ghostwriter.timer ghostwriter-freigabe.service ghostwriter-freigabe.timer; do
    if ! cmp -s "deploy/$unit" "/etc/systemd/system/$unit"; then
      cp "deploy/$unit" "/etc/systemd/system/$unit"
      neu=1
    fi
  done
  if [ -n "$neu" ]; then
    systemctl daemon-reload
    systemctl enable --now ghostwriter-freigabe.timer
    echo "Zeitpläne aktualisiert"
  fi
  $PY -m agent.cli fetch-stock
  $PY -m agent.cli fetch-lists
  # Abwesenheitsnotizen wegsortieren, Rückläufer aus den Listen löschen – danach Listen neu holen
  if $PY -m agent.cli postfach data/mailinglisten/*.xlsx; then $PY -m agent.cli fetch-lists; else echo "Postfach aufräumen fehlgeschlagen"; fi
  $PY -m agent.cli mail-sonder data/mailinglisten/*.xlsx || echo "Sonderangebot fehlgeschlagen"
  $PY -m agent.cli mail-neu data/mailinglisten/*.xlsx
}
main "$@"
