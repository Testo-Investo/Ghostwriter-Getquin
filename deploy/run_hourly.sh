#!/usr/bin/env bash
# Stündlicher Lauf: Bestand holen, bei neuer Ware Angebote an alle Listen mailen.
set -euo pipefail
cd /opt/ghostwriter
PY=.venv/bin/python
$PY -m agent.cli fetch-stock
$PY -m agent.cli mail-neu data/mailinglisten/*.xlsx
