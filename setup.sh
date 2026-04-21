#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_DIR/.env"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[x]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && err "Запусти от root: sudo bash setup.sh"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  VoiceGenWorker setup${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ── 1. Netbird ───────────────────────────────────────────────────────
log "1/4 Установка и подключение Netbird..."

if ! command -v netbird &>/dev/null; then
    curl -fsSL https://pkgs.netbird.io/install.sh | sh
else
    log "  Netbird уже установлен: $(netbird version 2>/dev/null || echo 'unknown')"
fi

read -rp "Адрес Netbird-сервера [netbird.minet.space]: " NETBIRD_SERVER
NETBIRD_SERVER="${NETBIRD_SERVER:-netbird.minet.space}"

while true; do
    read -rp "Netbird Setup Key: " NETBIRD_SETUP_KEY
    [ -n "${NETBIRD_SETUP_KEY}" ] && break
    warn "Setup Key не может быть пустым"
done

netbird up \
    --management-url "https://${NETBIRD_SERVER}" \
    --setup-key "${NETBIRD_SETUP_KEY}"

# Ждём появления интерфейса wt0 (до 30 секунд)
log "  Ожидаем подключения к Netbird..."
NETBIRD_IP=""
for i in $(seq 1 15); do
    NETBIRD_IP=$(ip addr show wt0 2>/dev/null \
        | grep "inet " \
        | awk '{print $2}' \
        | cut -d/ -f1 \
        | head -1)
    [ -n "${NETBIRD_IP}" ] && break
    sleep 2
done

if [ -z "${NETBIRD_IP}" ]; then
    warn "Не удалось получить IP от Netbird (интерфейс wt0 не появился)."
    warn "File server будет слушать на 127.0.0.1 — файлы недоступны с других машин."
    NETBIRD_IP="127.0.0.1"
else
    log "  Этот воркер в Netbird: ${NETBIRD_IP}"
fi

# ── 2. .env ──────────────────────────────────────────────────────────
log "2/4 Настройка окружения..."

ENV_SKIP=0
if [ -f "$ENV_FILE" ]; then
    read -rp ".env уже существует. Перезаписать? [y/N] " answer
    case "$answer" in
        [yY][eE][sS]|[yY]) ENV_SKIP=0 ;;
        *) warn "Оставляю существующий .env."; ENV_SKIP=1 ;;
    esac
fi

if [ "$ENV_SKIP" -eq 0 ]; then
    echo ""
    log "Введи параметры подключения к GenManager (Redis внутри Netbird-сети):"
    read -rp "  GenManager Netbird IP (REDIS_HOST) [100.95.0.0]: " REDIS_HOST
    REDIS_HOST="${REDIS_HOST:-100.95.0.0}"

    read -rp "  REDIS_PORT [6379]: " REDIS_PORT
    REDIS_PORT="${REDIS_PORT:-6379}"

    read -rp "  REDIS_PASSWORD: " REDIS_PASSWORD
    echo

    read -rp "  DEFAULT_GENERATOR (silero|omnivoice) [silero]: " DEFAULT_GENERATOR
    DEFAULT_GENERATOR="${DEFAULT_GENERATOR:-silero}"

    read -rp "  DEFAULT_SPEAKER [eugene]: " DEFAULT_SPEAKER
    DEFAULT_SPEAKER="${DEFAULT_SPEAKER:-eugene}"

    read -rp "  DEFAULT_SAMPLE_RATE [48000]: " DEFAULT_SAMPLE_RATE
    DEFAULT_SAMPLE_RATE="${DEFAULT_SAMPLE_RATE:-48000}"

    read -rp "  FILE_SERVER_PORT [8888]: " FILE_SERVER_PORT
    FILE_SERVER_PORT="${FILE_SERVER_PORT:-8888}"

    cat > "$ENV_FILE" <<EOF
# Redis — подключение к GenManager через Netbird-сеть
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=${REDIS_PORT}
REDIS_PASSWORD=${REDIS_PASSWORD}

CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/1

# TTS
DEFAULT_GENERATOR=${DEFAULT_GENERATOR}
DEFAULT_SPEAKER=${DEFAULT_SPEAKER}
DEFAULT_SAMPLE_RATE=${DEFAULT_SAMPLE_RATE}

# Temp dir
TEMP_DIR=temp

# Netbird — IP этого воркера в Netbird-сети; file-server слушает на этом IP
NETBIRD_IP=${NETBIRD_IP}
FILE_SERVER_PORT=${FILE_SERVER_PORT}
EOF
    chmod 600 "$ENV_FILE"
    log ".env создан."
else
    # Обновляем NETBIRD_IP в существующем .env
    if grep -q "^NETBIRD_IP=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^NETBIRD_IP=.*|NETBIRD_IP=${NETBIRD_IP}|" "$ENV_FILE"
    else
        echo "NETBIRD_IP=${NETBIRD_IP}" >> "$ENV_FILE"
    fi
    log "NETBIRD_IP=${NETBIRD_IP} обновлён в .env"
fi

# Читаем FILE_SERVER_PORT из .env если не задан выше
FILE_SERVER_PORT=$(grep "^FILE_SERVER_PORT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "8888")
FILE_SERVER_PORT="${FILE_SERVER_PORT:-8888}"

# ── 3. Docker ────────────────────────────────────────────────────────
log "3/4 Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
else
    log "  Docker уже установлен"
fi

if ! docker compose version &>/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin 2>/dev/null || true
fi

# ── 4. Firewall + запуск ─────────────────────────────────────────────
log "4/4 Firewall и запуск..."

# Разрешаем доступ к file-server только из Netbird-сети
if command -v ufw &>/dev/null; then
    ufw allow in on wt0 to any port "${FILE_SERVER_PORT}" 2>/dev/null || true
    log "  UFW: порт ${FILE_SERVER_PORT} открыт на wt0"
fi

cd "$REPO_DIR"
docker compose down 2>/dev/null || true
docker compose up -d --build

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  VoiceGenWorker запущен!${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "  Этот воркер (Netbird): ${NETBIRD_IP}"
echo -e "  File server:           http://${NETBIRD_IP}:${FILE_SERVER_PORT}/"
echo -e "  Очередь:               voice"
echo -e "  Логи:                  docker compose logs -f"
echo -e "${GREEN}============================================${NC}"
echo ""
warn "Убедись, что GenManager знает Netbird IP этого воркера: ${NETBIRD_IP}"
