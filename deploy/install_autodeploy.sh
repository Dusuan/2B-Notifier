#!/usr/bin/env bash
# Instala (idempotente) el cron de autodeploy en la VM, para el usuario actual (sin sudo).
# Uso en la VM:  bash deploy/install_autodeploy.sh
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/2b-notifier-deploy.log"
LINE="*/5 * * * * $REPO_DIR/deploy/autodeploy.sh >> $LOG 2>&1"

chmod +x "$REPO_DIR/deploy/autodeploy.sh"
docker info >/dev/null 2>&1 || { echo "Tu usuario no puede usar docker sin sudo (agrégalo al grupo docker)."; exit 1; }

( crontab -l 2>/dev/null | grep -v 'deploy/autodeploy.sh' || true; echo "$LINE" ) | crontab -
echo "Cron instalado:"; crontab -l | grep autodeploy
echo "Log: $LOG"
