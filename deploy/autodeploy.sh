#!/usr/bin/env bash
# CD "pull-based" de 2B-Notifier: corre en la VM vía cron cada 5 min.
# Si origin/master tiene commits nuevos: pull -> build -> tests dentro de la imagen nueva -> up -d.
# Si los tests fallan: vuelve al commit anterior, deja corriendo el contenedor viejo,
# marca el commit como fallido (no reintenta en bucle) y avisa por Telegram.
set -euo pipefail
export PATH="$PATH:/usr/local/bin:/usr/bin:/bin"   # cron trae un PATH mínimo

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BRANCH="${BRANCH:-master}"
IMAGE="2b-notifier:latest"
FAILED_FILE="$REPO_DIR/.deploy_failed"
cd "$REPO_DIR"

# Evitar dos despliegues simultáneos
exec 9>/tmp/2b-notifier-deploy.lock
flock -n 9 || exit 0

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [autodeploy] $*"; }

notify() {  # aviso directo por Telegram (no depende del contenedor)
  local token chat
  token=$(grep -E '^TELEGRAM_BOT_TOKEN=' .env 2>/dev/null | cut -d= -f2- | tr -d "\"' \r" || true)
  chat=$(grep -E '^TELEGRAM_CHAT_ID=' .env 2>/dev/null | cut -d= -f2- | tr -d "\"' \r" || true)
  [ -n "$token" ] && [ -n "$chat" ] || return 0
  curl -s -o /dev/null --max-time 10 "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${chat}" --data-urlencode "text=$1" || true
}

git fetch -q origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")
[ "$LOCAL" = "$REMOTE" ] && exit 0
if [ -f "$FAILED_FILE" ] && [ "$(cat "$FAILED_FILE")" = "$REMOTE" ]; then
  exit 0  # ya falló este commit; esperar uno nuevo
fi

log "Nuevo commit ${REMOTE:0:7} (actual ${LOCAL:0:7}). Desplegando..."
if ! git merge -q --ff-only "origin/$BRANCH"; then
  log "No se puede hacer fast-forward (¿cambios locales en la VM?). Abortado."
  echo "$REMOTE" > "$FAILED_FILE"
  notify "⚠️ 2B-Notifier: autodeploy abortado en ${REMOTE:0:7}: la VM tiene cambios locales (git status)."
  exit 1
fi

COMPOSE="docker compose"
$COMPOSE version >/dev/null 2>&1 || COMPOSE="docker-compose"

rollback() {
  log "$1 Rollback a ${LOCAL:0:7}; el contenedor actual sigue corriendo."
  git reset -q --hard "$LOCAL"
  echo "$REMOTE" > "$FAILED_FILE"
  notify "❌ 2B-Notifier: deploy de ${REMOTE:0:7} falló ($1). Sigue activa la versión ${LOCAL:0:7}."
  exit 1
}

$COMPOSE build -q || rollback "Build falló."

# Gate de calidad: tests con el código nuevo dentro de la imagen nueva
docker run --rm -v "$REPO_DIR":/src:ro -w /src -e STATE_FILE=/tmp/state.json \
  --entrypoint python "$IMAGE" -m unittest discover -s tests >/tmp/2b-notifier-tests.log 2>&1 \
  || { tail -20 /tmp/2b-notifier-tests.log; rollback "Tests fallaron."; }

$COMPOSE up -d --remove-orphans
rm -f "$FAILED_FILE"
docker image prune -f >/dev/null 2>&1 || true   # disco pequeño: borrar capas viejas
log "Desplegado ${REMOTE:0:7}."
notify "🚀 2B-Notifier desplegado: $(git log -1 --format='%h %s')"
