#!/usr/bin/env bash
# Einrichtung des Ghostwriter-Agenten auf dem Server (Ubuntu). Als root ausführen:
#   bash /opt/ghostwriter/deploy/install.sh
# Fragt Absender und IONOS-Passwort ab (Eingabe unsichtbar) – nichts davon landet im Chat oder Repo.
set -euo pipefail
APP=/opt/ghostwriter
cd "$APP"

echo "== Pakete installieren"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip > /dev/null

echo "== Python-Umgebung"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

mkdir -p data/mailinglisten config/secrets
chmod 700 config/secrets

if [ ! -f .env ]; then
  echo "== Zugangsdaten (werden nur auf diesem Server gespeichert)"
  read -rp "Absender-Adresse [marc@neobution.com]: " MAIL_FROM
  MAIL_FROM=${MAIL_FROM:-marc@neobution.com}
  read -rp "IONOS-Benutzername [$MAIL_FROM]: " SMTP_USER
  SMTP_USER=${SMTP_USER:-$MAIL_FROM}
  read -rsp "IONOS-Passwort (Eingabe unsichtbar): " SMTP_PASS; echo
  cat > .env <<ENV
MAIL_FROM=$MAIL_FROM
MAIL_NAME=Marc Knieb
IONOS_SMTP_USER=$SMTP_USER
IONOS_SMTP_PASSWORD=$SMTP_PASS
GOOGLE_SERVICE_ACCOUNT_FILE=$APP/config/secrets/google.json
ENV
  chmod 600 .env
fi

echo "== Stündlicher Lauf (systemd)"
cat > /etc/systemd/system/ghostwriter.service <<UNIT
[Unit]
Description=Ghostwriter: Bestand prüfen und bei neuer Ware Angebote mailen
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP
ExecStart=$APP/deploy/run_hourly.sh
UNIT
cp "$APP/deploy/ghostwriter.timer" /etc/systemd/system/ghostwriter.timer  # Zeitplan steht im Repo
timedatectl set-timezone Europe/Berlin
systemctl daemon-reload
echo
echo "Fertig. Der stündliche Lauf ist eingerichtet, aber noch AUS."
echo "Nächste Schritte siehe Chat: Google-Zugang, Listen hochladen, Testversand."
