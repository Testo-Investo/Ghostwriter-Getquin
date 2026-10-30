#!/usr/bin/env bash
# Minuten-Lauf: nur Antworten auf offene Freigabe-Mails bearbeiten (FREIGABE → Versand
# 5 Minuten nach der Antwort, MIX, STOPP). Neue Freigabe-Mails macht nur der Stundenlauf.
set -euo pipefail
cd /opt/ghostwriter
exec 9>/run/ghostwriter.lock
flock -n 9 || exit 0   # Stundenlauf oder ein Versand läuft gerade – nächste Minute wieder
PY=.venv/bin/python
$PY -m agent.cli mail-sonder data/mailinglisten/*.xlsx --nur-antworten
$PY -m agent.cli mail-neu data/mailinglisten/*.xlsx --nur-antworten
